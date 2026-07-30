import asyncio
import os
import random
from datetime import datetime, timezone

import httpx

BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8000")

MACHINES = [
    {"machine_id": "M-01-Torna", "label": "Torna", "target": 15,
     "temp": (65, 90), "vib": (0.5, 3.5), "pres": (4.0, 8.0), "cycle": (0.8, 2.5)},
    {"machine_id": "M-02-Pres",  "label": "Pres",  "target": 20,
     "temp": (55, 80), "vib": (1.0, 5.0), "pres": (6.0, 12.0), "cycle": (0.5, 1.5)},
    {"machine_id": "M-03-CNC",   "label": "CNC",   "target": 12,
     "temp": (70, 95), "vib": (0.3, 2.0), "pres": (3.0, 6.0), "cycle": (1.2, 3.0)},
]

ERROR_CODES = {
    "E01": "Takım Aşınması",
    "E02": "Aşırı Isınma",
    "E03": "Titreşim Anomalisi",
    "E04": "Basınç Düşüklüğü",
    "E05": "Hammadde Yok",
    "E06": "Bakım Zamanı",
    "M01": "Planlı Duruş",
}

STATUS_SET = ["RUNNING", "RUNNING", "RUNNING", "IDLE", "ERROR", "DOWN"]
STATUS_WEIGHTS = [0.65, 0.10, 0.10, 0.07, 0.05, 0.03]


def random_walk(current, target, step=0.5):
    if current < target:
        return min(current + random.uniform(0, step), target)
    return max(current - random.uniform(0, step), target)


class MachineSim:
    def __init__(self, cfg):
        self.cfg = cfg
        self.status = "RUNNING"
        self.temp = cfg["temp"][0] + random.random() * 10
        self.vib = cfg["vib"][0] + random.random() * 0.5
        self.pres = cfg["pres"][0] + random.random() * 1.0
        self.prev_status = "RUNNING"

    def tick(self):
        self.prev_status = self.status
        self.status = random.choices(STATUS_SET, weights=STATUS_WEIGHTS, k=1)[0]
        self.temp = random_walk(self.temp, sum(self.cfg["temp"]) / 2, 1.5)
        self.vib = random_walk(self.vib, sum(self.cfg["vib"]) / 2, 0.3)
        self.pres = random_walk(self.pres, sum(self.cfg["pres"]) / 2, 0.5)

    def get_telemetry(self):
        is_running = self.status == "RUNNING"
        produced = random.randint(0, self.cfg["target"]) if is_running else 0
        defective = random.randint(0, max(1, produced // 4)) if produced > 0 else 0
        return {
            "machine_id": self.cfg["machine_id"],
            "temperature": round(self.temp, 1),
            "vibration": round(self.vib, 2),
            "pressure": round(self.pres, 2),
            "produced_qty": produced,
            "defective_qty": defective,
            "cycle_time": round(random.uniform(self.cfg["cycle"][0], self.cfg["cycle"][1]), 2),
            "status_code": self.status,
            "error_code": random.choice(list(ERROR_CODES.keys())) if self.status in ("ERROR", "DOWN") else "",
        }

    def should_start_downtime(self):
        return self.prev_status in ("RUNNING", "IDLE") and self.status in ("ERROR", "DOWN")

    def should_end_downtime(self):
        return self.prev_status in ("ERROR", "DOWN") and self.status in ("RUNNING", "IDLE")


async def run():
    print(f"[Simulator] Backend URL: {BACKEND_URL}")
    machines = [MachineSim(m) for m in MACHINES]
    async with httpx.AsyncClient(timeout=5) as client:
        while True:
            now = datetime.now(timezone.utc)
            for sim in machines:
                sim.tick()
                payload = sim.get_telemetry()
                try:
                    resp = await client.post(f"{BACKEND_URL}/api/telemetry", json=payload)
                    if resp.status_code == 200:
                        data = resp.json()
                        ts = now.strftime("%H:%M:%S")
                        print(f"[{ts}] {data['machine_id']} | OEE:{data['oee']:>5.1f}% "
                              f"{data['status']:>7} | T:{payload['temperature']}°C "
                              f"V:{payload['vibration']} P:{payload['pressure']} "
                              f"K:{payload['produced_qty']}/{payload['defective_qty']}")
                    else:
                        print(f"[ERROR] {sim.cfg['machine_id']} HTTP {resp.status_code}")
                except Exception as e:
                    print(f"[ERROR] {sim.cfg['machine_id']} {e}")

                if sim.should_start_downtime():
                    reason = payload["error_code"] or "E05"
                    dt = {"machine_id": sim.cfg["machine_id"], "reason_code": reason}
                    try:
                        await client.post(f"{BACKEND_URL}/api/downtime/start", json=dt)
                        print(f"[DOWN] {sim.cfg['machine_id']} başladı: {ERROR_CODES.get(reason, reason)}")
                    except Exception as e:
                        print(f"[ERROR] downtime/start {e}")

                if sim.should_end_downtime():
                    dt = {"machine_id": sim.cfg["machine_id"]}
                    try:
                        resp = await client.post(f"{BACKEND_URL}/api/downtime/end", json=dt)
                        if resp.status_code == 200:
                            dur = resp.json().get("duration_seconds", 0)
                            print(f"[UP]   {sim.cfg['machine_id']} bitti ({dur}s) \u2705")
                    except Exception as e:
                        print(f"[ERROR] downtime/end {e}")

            await asyncio.sleep(1)


if __name__ == "__main__":
    asyncio.run(run())
