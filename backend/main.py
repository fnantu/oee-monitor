import os
import json
import csv
import io
from datetime import datetime, timezone
from contextlib import asynccontextmanager
from typing import Optional

import asyncpg
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Query
from fastapi.responses import StreamingResponse, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field


def parse_date(d: Optional[str]):
    if d is None:
        return None
    try:
        return datetime.strptime(d, "%Y-%m-%dT%H:%M:%S")
    except ValueError:
        pass
    try:
        return datetime.strptime(d, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError:
        pass
    return datetime.strptime(d, "%Y-%m-%d")


DB_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "port": int(os.getenv("DB_PORT", 5432)),
    "user": os.getenv("DB_USER", "oee_user"),
    "password": os.getenv("DB_PASSWORD", "oee_pass"),
    "database": os.getenv("DB_NAME", "oee_db"),
}

TARGET_RATES = {
    "M-01-Torna": 15,
    "M-02-Pres": 20,
    "M-03-CNC": 12,
}

pool: asyncpg.Pool = None


class TelemetryPayload(BaseModel):
    machine_id: str = Field(pattern=r"^M-\d{2}-[A-Za-z]+$")
    temperature: float = Field(ge=0, le=200)
    vibration: float = Field(ge=0, le=100)
    pressure: float = Field(ge=0, le=50)
    produced_qty: int = Field(ge=0)
    defective_qty: int = Field(ge=0)
    cycle_time: float = Field(ge=0)
    status_code: str = Field(pattern=r"^(RUNNING|IDLE|ERROR|DOWN)$")
    error_code: str = ""


class DowntimeStartPayload(BaseModel):
    machine_id: str
    reason_code: str
    time: Optional[datetime] = None


class DowntimeEndPayload(BaseModel):
    machine_id: str
    time: Optional[datetime] = None


def calculate_oee(status_code: str, produced_qty: int, defective_qty: int, machine_id: str) -> dict:
    availability = 100.0 if status_code == "RUNNING" else 0.0
    target = TARGET_RATES.get(machine_id, 10)
    performance = (produced_qty / target) * 100 if target > 0 else 0.0
    performance = min(performance, 100.0)
    quality = ((produced_qty - defective_qty) / produced_qty * 100) if produced_qty > 0 else 0.0
    quality = max(0, min(quality, 100.0))
    oee = (availability * performance * quality) / 10000.0
    return {
        "availability": round(availability, 2),
        "performance": round(performance, 2),
        "quality": round(quality, 2),
        "oee": round(oee, 2),
    }


class ConnectionManager:
    def __init__(self):
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)

    async def broadcast(self, data: dict):
        dead = []
        for conn in self.active_connections:
            try:
                await conn.send_json(data)
            except Exception:
                dead.append(conn)
        for conn in dead:
            self.active_connections.remove(conn)


manager = ConnectionManager()


async def migrate_db(conn):
    for col in ["vibration", "pressure", "defective_qty", "cycle_time", "error_code", "availability", "performance", "quality", "oee"]:
        try:
            await conn.execute(f"ALTER TABLE sensor_data ADD COLUMN IF NOT EXISTS {col} DOUBLE PRECISION DEFAULT 0")
        except Exception:
            pass
    try:
        await conn.execute("ALTER TABLE sensor_data ALTER COLUMN defective_qty TYPE INTEGER USING defective_qty::integer")
    except Exception:
        pass
    try:
        await conn.execute("ALTER TABLE sensor_data ALTER COLUMN error_code TYPE TEXT USING error_code::text")
    except Exception:
        pass
    try:
        await conn.execute("ALTER TABLE sensor_data ALTER COLUMN vibration TYPE DOUBLE PRECISION USING vibration::double precision")
    except Exception:
        pass
    try:
        await conn.execute("ALTER TABLE sensor_data ALTER COLUMN pressure TYPE DOUBLE PRECISION USING pressure::double precision")
    except Exception:
        pass
    try:
        await conn.execute("ALTER TABLE sensor_data ALTER COLUMN cycle_time TYPE DOUBLE PRECISION USING cycle_time::double precision")
    except Exception:
        pass
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS downtime_events (
            id SERIAL PRIMARY KEY,
            machine_id TEXT NOT NULL,
            start_time TIMESTAMPTZ NOT NULL,
            end_time TIMESTAMPTZ,
            reason_code TEXT NOT NULL,
            duration_seconds INTEGER DEFAULT 0
        )
    """)
    try:
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_downtime_machine ON downtime_events (machine_id, start_time DESC)")
    except Exception:
        pass


@asynccontextmanager
async def lifespan(app: FastAPI):
    global pool
    pool = await asyncpg.create_pool(**DB_CONFIG, min_size=2, max_size=10)
    async with pool.acquire() as conn:
        await migrate_db(conn)
    yield
    if pool:
        await pool.close()


app = FastAPI(title="OEE Telemetry API", version="2.2.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health():
    return {"status": "ok", "service": "oee-backend", "version": "2.2.0"}


@app.post("/api/telemetry")
async def post_telemetry(payload: TelemetryPayload):
    oee_result = calculate_oee(payload.status_code, payload.produced_qty, payload.defective_qty, payload.machine_id)
    now = datetime.now(timezone.utc)
    async with pool.acquire() as conn:
        await conn.execute(
            """INSERT INTO sensor_data
               (time, machine_id, temperature, vibration, pressure, produced_qty, defective_qty,
                cycle_time, status_code, error_code, availability, performance, quality, oee)
               VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14)""",
            now, payload.machine_id, payload.temperature, payload.vibration, payload.pressure,
            payload.produced_qty, payload.defective_qty, payload.cycle_time,
            payload.status_code, payload.error_code,
            oee_result["availability"], oee_result["performance"],
            oee_result["quality"], oee_result["oee"],
        )
    broadcast_data = {
        "machine_id": payload.machine_id,
        "temperature": payload.temperature,
        "vibration": payload.vibration,
        "pressure": payload.pressure,
        "cycle_time": payload.cycle_time,
        "produced_qty": payload.produced_qty,
        "defective_qty": payload.defective_qty,
        "oee": oee_result["oee"],
        "availability": oee_result["availability"],
        "performance": oee_result["performance"],
        "quality": oee_result["quality"],
        "status": payload.status_code,
        "error_code": payload.error_code,
        "time": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    await manager.broadcast(broadcast_data)
    return broadcast_data


@app.post("/api/downtime/start")
async def downtime_start(payload: DowntimeStartPayload):
    now = payload.time or datetime.now(timezone.utc)
    async with pool.acquire() as conn:
        await conn.execute(
            """INSERT INTO downtime_events (machine_id, start_time, reason_code)
               VALUES ($1, $2, $3)""",
            payload.machine_id, now, payload.reason_code,
        )
    return {"status": "downtime_started", "machine_id": payload.machine_id, "reason_code": payload.reason_code, "time": now.isoformat()}


@app.post("/api/downtime/end")
async def downtime_end(payload: DowntimeEndPayload):
    now = payload.time or datetime.now(timezone.utc)
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """UPDATE downtime_events
               SET end_time = $2,
                   duration_seconds = EXTRACT(EPOCH FROM ($2 - start_time))::INTEGER
               WHERE machine_id = $1 AND end_time IS NULL
               RETURNING id, start_time, reason_code, duration_seconds""",
            payload.machine_id, now,
        )
    if not row:
        raise HTTPException(status_code=404, detail=f"No open downtime event for {payload.machine_id}")
    return {
        "status": "downtime_ended",
        "machine_id": payload.machine_id,
        "event_id": row["id"],
        "reason_code": row["reason_code"],
        "start_time": row["start_time"].isoformat(),
        "end_time": now.isoformat(),
        "duration_seconds": row["duration_seconds"],
    }


@app.get("/api/telemetry/history")
async def get_history(
    machine_id: str = Query(...),
    from_date: Optional[str] = Query(None, alias="from"),
    to_date: Optional[str] = Query(None, alias="to"),
    limit: int = Query(100, le=10000),
):
    conditions = ["machine_id = $1"]
    params = [machine_id]
    idx = 2
    if from_date:
        conditions.append(f"time >= ${idx}")
        params.append(parse_date(from_date))
        idx += 1
    if to_date:
        conditions.append(f"time <= ${idx}")
        params.append(parse_date(to_date))
        idx += 1
    query = f"""SELECT time, machine_id, temperature, vibration, pressure,
                       produced_qty, defective_qty, cycle_time, status_code, error_code,
                       availability, performance, quality, oee
                FROM sensor_data
                WHERE {' AND '.join(conditions)}
                ORDER BY time DESC
                LIMIT ${idx}"""
    params.append(limit)
    async with pool.acquire() as conn:
        rows = await conn.fetch(query, *params)
    return [dict(r) for r in rows]


@app.get("/api/reports/oee/hourly")
async def get_oee_hourly(
    machine_id: str = Query(...),
    report_date: str = Query(..., alias="date"),
):
    d = parse_date(report_date)
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """SELECT
                   time_bucket('1 hour', time) AS hour,
                   ROUND(AVG(oee)::numeric, 2) AS avg_oee,
                   ROUND(AVG(availability)::numeric, 2) AS avg_availability,
                   ROUND(AVG(performance)::numeric, 2) AS avg_performance,
                   ROUND(AVG(quality)::numeric, 2) AS avg_quality,
                   SUM(produced_qty) AS total_production,
                   SUM(defective_qty) AS total_defective,
                   COUNT(*) FILTER (WHERE status_code != 'RUNNING') AS error_count
               FROM sensor_data
               WHERE machine_id = $1 AND time::date = $2
               GROUP BY hour
               ORDER BY hour""",
            machine_id, d,
        )
    return [dict(r) for r in rows]


@app.get("/api/reports/oee/daily")
async def get_oee_daily(
    machine_id: str = Query(...),
    from_date: str = Query(..., alias="from"),
    to_date: str = Query(..., alias="to"),
):
    f = parse_date(from_date)
    t = parse_date(to_date)
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """SELECT
                   time::date AS day,
                   ROUND(AVG(oee)::numeric, 2) AS avg_oee,
                   ROUND(MAX(oee)::numeric, 2) AS max_oee,
                   ROUND(MIN(oee)::numeric, 2) AS min_oee,
                   ROUND(AVG(availability)::numeric, 2) AS avg_availability,
                   ROUND(AVG(performance)::numeric, 2) AS avg_performance,
                   ROUND(AVG(quality)::numeric, 2) AS avg_quality,
                   SUM(produced_qty) AS total_production,
                   SUM(defective_qty) AS total_defective
               FROM sensor_data
               WHERE machine_id = $1 AND time::date >= $2 AND time::date <= $3
               GROUP BY day
               ORDER BY day""",
            machine_id, f, t,
        )
    return [dict(r) for r in rows]


@app.get("/api/reports/downtime")
async def get_downtime(
    machine_id: str = Query(...),
    from_date: Optional[str] = Query(None, alias="from"),
    to_date: Optional[str] = Query(None, alias="to"),
):
    conditions = ["machine_id = $1"]
    params = [machine_id]
    idx = 2
    if from_date:
        conditions.append(f"start_time >= ${idx}")
        params.append(parse_date(from_date))
        idx += 1
    if to_date:
        conditions.append(f"start_time <= ${idx}")
        params.append(parse_date(to_date))
        idx += 1
    query = f"""SELECT id, machine_id, start_time, end_time, reason_code, duration_seconds
                FROM downtime_events
                WHERE {' AND '.join(conditions)}
                ORDER BY start_time DESC
                LIMIT 1000"""
    async with pool.acquire() as conn:
        rows = await conn.fetch(query, *params)
    total_seconds = sum(r["duration_seconds"] or 0 for r in rows)
    events_by_reason = {}
    for r in rows:
        rc = r["reason_code"]
        events_by_reason[rc] = events_by_reason.get(rc, 0) + 1
    return {
        "total_events": len(rows),
        "total_downtime_seconds": total_seconds,
        "events_by_reason": events_by_reason,
        "events": [dict(r) for r in rows],
    }


@app.get("/api/reports/production")
async def get_production(
    machine_id: str = Query(...),
    from_date: Optional[str] = Query(None, alias="from"),
    to_date: Optional[str] = Query(None, alias="to"),
):
    conditions = ["machine_id = $1"]
    params = [machine_id]
    idx = 2
    if from_date:
        conditions.append(f"time::date >= ${idx}")
        params.append(parse_date(from_date))
        idx += 1
    if to_date:
        conditions.append(f"time::date <= ${idx}")
        params.append(parse_date(to_date))
        idx += 1
    query = f"""SELECT
                   COUNT(*) AS total_readings,
                   SUM(produced_qty) AS total_produced,
                   SUM(defective_qty) AS total_defective,
                   ROUND(AVG(cycle_time)::numeric, 3) AS avg_cycle_time,
                   ROUND(AVG(temperature)::numeric, 1) AS avg_temperature,
                   ROUND(MIN(temperature)::numeric, 1) AS min_temperature,
                   ROUND(MAX(temperature)::numeric, 1) AS max_temperature,
                   ROUND(AVG(vibration)::numeric, 2) AS avg_vibration,
                   ROUND(AVG(pressure)::numeric, 2) AS avg_pressure
                FROM sensor_data
                WHERE {' AND '.join(conditions)}"""
    async with pool.acquire() as conn:
        row = await conn.fetchrow(query, *params)
    return dict(row)


@app.get("/api/reports/summary")
async def get_summary(
    from_date: Optional[str] = Query(None, alias="from"),
    to_date: Optional[str] = Query(None, alias="to"),
):
    conditions = []
    params = []
    idx = 1
    if from_date:
        conditions.append(f"time::date >= ${idx}")
        params.append(parse_date(from_date))
        idx += 1
    if to_date:
        conditions.append(f"time::date <= ${idx}")
        params.append(parse_date(to_date))
        idx += 1
    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    query = f"""SELECT
                   machine_id,
                   ROUND(AVG(oee)::numeric, 2) AS avg_oee,
                   ROUND(AVG(availability)::numeric, 2) AS avg_availability,
                   ROUND(AVG(performance)::numeric, 2) AS avg_performance,
                   ROUND(AVG(quality)::numeric, 2) AS avg_quality,
                   SUM(produced_qty) AS total_production,
                   SUM(defective_qty) AS total_defective,
                   COUNT(*) AS total_readings
                FROM sensor_data
                {where}
                GROUP BY machine_id
                ORDER BY machine_id"""
    async with pool.acquire() as conn:
        rows = await conn.fetch(query, *params)
    return [dict(r) for r in rows]


@app.get("/api/reports/export")
async def export_data(
    format: str = Query("csv", regex="^(csv|json)$"),
    machine_id: Optional[str] = None,
    from_date: Optional[str] = Query(None, alias="from"),
    to_date: Optional[str] = Query(None, alias="to"),
):
    conditions = []
    params = []
    idx = 1
    if machine_id:
        conditions.append(f"machine_id = ${idx}")
        params.append(machine_id)
        idx += 1
    if from_date:
        conditions.append(f"time::date >= ${idx}")
        params.append(parse_date(from_date))
        idx += 1
    if to_date:
        conditions.append(f"time::date <= ${idx}")
        params.append(parse_date(to_date))
        idx += 1
    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    query = f"""SELECT time, machine_id, temperature, vibration, pressure,
                       produced_qty, defective_qty, cycle_time, status_code, error_code,
                       availability, performance, quality, oee
                FROM sensor_data {where}
                ORDER BY time DESC LIMIT 10000"""
    async with pool.acquire() as conn:
        rows = await conn.fetch(query, *params)
    if format == "json":
        data = [dict(r, time=r["time"].isoformat()) for r in rows]
        return Response(content=json.dumps(data, ensure_ascii=False), media_type="application/json", headers={"Content-Disposition": "attachment; filename=oee_export.json"})
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["time", "machine_id", "temperature", "vibration", "pressure", "produced_qty", "defective_qty", "cycle_time", "status_code", "error_code", "availability", "performance", "quality", "oee"])
    for r in rows:
        writer.writerow([r["time"].isoformat(), r["machine_id"], r["temperature"], r["vibration"], r["pressure"], r["produced_qty"], r["defective_qty"], r["cycle_time"], r["status_code"], r["error_code"], r["availability"], r["performance"], r["quality"], r["oee"]])
    output.seek(0)
    return StreamingResponse(iter([output.getvalue()]), media_type="text/csv", headers={"Content-Disposition": "attachment; filename=oee_export.csv"})


@app.get("/api/reports/timeseries")
async def get_timeseries(
    machine_ids: str = Query(...),
    metrics: str = Query("oee"),
    granularity: str = Query("1h", regex="^(1m|5m|15m|1h|4h|1d)$"),
    from_date: str = Query(..., alias="from"),
    to_date: str = Query(..., alias="to"),
):
    allowed_machines = {"M-01-Torna", "M-02-Pres", "M-03-CNC"}
    machine_list = [m.strip() for m in machine_ids.split(",") if m.strip() in allowed_machines]
    if not machine_list:
        machine_list = list(allowed_machines)
    metric_list = [m.strip() for m in metrics.split(",")]
    allowed_metrics = {"oee", "availability", "performance", "quality", "temperature", "vibration", "pressure", "produced_qty", "defective_qty", "cycle_time"}
    metric_list = [m for m in metric_list if m in allowed_metrics] or ["oee"]

    select_parts = [f"time_bucket('{granularity}', time) AS bucket"]
    for mid in machine_list:
        for met in metric_list:
            alias = f"{mid}_{met}"
            if met in ("temperature",):
                select_parts.append(f"ROUND(AVG({met}) FILTER (WHERE machine_id = '{mid}')::numeric, 1) AS \"{alias}_avg\"")
            elif met in ("vibration", "pressure", "cycle_time"):
                select_parts.append(f"ROUND(AVG({met}) FILTER (WHERE machine_id = '{mid}')::numeric, 2) AS \"{alias}_avg\"")
            elif met in ("produced_qty", "defective_qty"):
                select_parts.append(f"SUM({met}) FILTER (WHERE machine_id = '{mid}') AS \"{alias}_sum\"")
            else:
                select_parts.append(f"ROUND(AVG({met}) FILTER (WHERE machine_id = '{mid}')::numeric, 2) AS \"{alias}_avg\"")
    select_sql = ",\n                   ".join(select_parts)

    f = parse_date(from_date)
    t = parse_date(to_date)
    query = f"""SELECT {select_sql}
                FROM sensor_data
                WHERE time::date >= $1::date AND time::date <= $2::date
                AND machine_id = ANY($3::text[])
                GROUP BY bucket
                ORDER BY bucket"""
    async with pool.acquire() as conn:
        rows = await conn.fetch(query, f, t, machine_list)
    return [dict(r) for r in rows]


@app.get("/api/reports/stats")
async def get_stats(
    machine_ids: str = Query(...),
    from_date: Optional[str] = Query(None, alias="from"),
    to_date: Optional[str] = Query(None, alias="to"),
):
    machine_list = [m.strip() for m in machine_ids.split(",")]
    conditions = ["machine_id = ANY($1::text[])"]
    params = [machine_list]
    idx = 2

    f, t = None, None
    if from_date:
        f = parse_date(from_date)
        conditions.append(f"sd.time::date >= ${idx}")
        params.append(f)
        idx += 1
    if to_date:
        t = parse_date(to_date)
        conditions.append(f"sd.time::date <= ${idx}")
        params.append(t)
        idx += 1
    sensor_where = " AND ".join(conditions)

    sensor_query = f"""SELECT
        sd.machine_id,
        ROUND(AVG(sd.oee)::numeric, 2) AS avg_oee,
        ROUND(MAX(sd.oee)::numeric, 2) AS max_oee,
        ROUND(MIN(sd.oee)::numeric, 2) AS min_oee,
        ROUND(AVG(sd.availability)::numeric, 2) AS avg_availability,
        ROUND(AVG(sd.performance)::numeric, 2) AS avg_performance,
        ROUND(AVG(sd.quality)::numeric, 2) AS avg_quality,
        ROUND(AVG(sd.temperature)::numeric, 1) AS avg_temperature,
        ROUND(AVG(sd.vibration)::numeric, 2) AS avg_vibration,
        ROUND(AVG(sd.pressure)::numeric, 2) AS avg_pressure,
        SUM(sd.produced_qty) AS total_production,
        SUM(sd.defective_qty) AS total_defective,
        ROUND(
            (COUNT(*) FILTER (WHERE sd.status_code = 'RUNNING')::numeric /
             NULLIF(COUNT(*), 0)::numeric) * 100, 1
        ) AS uptime_pct,
        COUNT(*) AS total_readings
    FROM sensor_data sd
    WHERE {sensor_where}
    GROUP BY sd.machine_id
    ORDER BY sd.machine_id"""

    dt_conditions = ["machine_id = ANY($1::text[])"]
    dt_params = [machine_list]
    dt_idx = 2
    if f:
        dt_conditions.append(f"date(start_time) >= ${dt_idx}")
        dt_params.append(f)
        dt_idx += 1
    if t:
        dt_conditions.append(f"date(start_time) <= ${dt_idx}")
        dt_params.append(t)
        dt_idx += 1
    dt_where = " AND ".join(dt_conditions)
    dt_query = f"""SELECT
        machine_id,
        COUNT(*) AS downtime_count,
        COALESCE(SUM(COALESCE(duration_seconds, 0)), 0) AS total_downtime_seconds
    FROM downtime_events
    WHERE {dt_where}
    GROUP BY machine_id"""

    async with pool.acquire() as conn:
        sensor_rows = await conn.fetch(sensor_query, *params)
        dt_rows = await conn.fetch(dt_query, *dt_params)

    dt_map = {r["machine_id"]: r for r in dt_rows}
    result = []
    for r in sensor_rows:
        mid = r["machine_id"]
        dt = dt_map.get(mid, {})
        dc = dt.get("downtime_count", 0) or 0
        tds = dt.get("total_downtime_seconds", 0) or 0
        reading_count = r["total_readings"] or 0
        result.append({
            "machine_id": mid,
            "avg_oee": r["avg_oee"],
            "max_oee": r["max_oee"],
            "min_oee": r["min_oee"],
            "avg_availability": r["avg_availability"],
            "avg_performance": r["avg_performance"],
            "avg_quality": r["avg_quality"],
            "avg_temperature": r["avg_temperature"],
            "avg_vibration": r["avg_vibration"],
            "avg_pressure": r["avg_pressure"],
            "total_production": r["total_production"] or 0,
            "total_defective": r["total_defective"] or 0,
            "uptime_pct": r["uptime_pct"] or 0,
            "total_readings": reading_count,
            "downtime_count": dc,
            "total_downtime_seconds": tds,
            "mtbf_seconds": round(reading_count / dc, 1) if dc > 0 else None,
        })
    return result


@app.get("/api/reports/top-errors")
async def get_top_errors(
    machine_ids: Optional[str] = Query(None),
    from_date: Optional[str] = Query(None, alias="from"),
    to_date: Optional[str] = Query(None, alias="to"),
    limit: int = Query(10, le=50),
):
    conditions = []
    params = []
    idx = 1
    if machine_ids:
        mlist = [m.strip() for m in machine_ids.split(",")]
        conditions.append(f"machine_id = ANY(${idx}::text[])")
        params.append(mlist)
        idx += 1
    if from_date:
        f = parse_date(from_date)
        conditions.append(f"date(start_time) >= ${idx}")
        params.append(f)
        idx += 1
    if to_date:
        t = parse_date(to_date)
        conditions.append(f"date(start_time) <= ${idx}")
        params.append(t)
        idx += 1
    where_clause = ("WHERE " + " AND ".join(conditions)) if conditions else ""
    query = f"""SELECT reason_code, COUNT(*) AS event_count,
                       COALESCE(SUM(COALESCE(duration_seconds, 0)), 0) AS total_seconds
                FROM downtime_events {where_clause}
                GROUP BY reason_code
                ORDER BY event_count DESC LIMIT ${idx}"""
    params.append(limit)
    async with pool.acquire() as conn:
        rows = await conn.fetch(query, *params)
    return [dict(r) for r in rows]


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)
