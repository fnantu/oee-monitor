CREATE EXTENSION IF NOT EXISTS timescaledb;

CREATE TABLE IF NOT EXISTS sensor_data (
    time TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    machine_id TEXT NOT NULL,
    temperature DOUBLE PRECISION,
    vibration DOUBLE PRECISION DEFAULT 0,
    pressure DOUBLE PRECISION DEFAULT 0,
    produced_qty INTEGER DEFAULT 0,
    defective_qty INTEGER DEFAULT 0,
    cycle_time DOUBLE PRECISION DEFAULT 0,
    status_code TEXT,
    error_code TEXT DEFAULT '',
    availability DOUBLE PRECISION DEFAULT 0,
    performance DOUBLE PRECISION DEFAULT 0,
    quality DOUBLE PRECISION DEFAULT 0,
    oee DOUBLE PRECISION DEFAULT 0
);

SELECT create_hypertable('sensor_data', 'time', if_not_exists => TRUE);

CREATE INDEX IF NOT EXISTS idx_machine_time ON sensor_data (machine_id, time DESC);

CREATE TABLE IF NOT EXISTS downtime_events (
    id SERIAL PRIMARY KEY,
    machine_id TEXT NOT NULL,
    start_time TIMESTAMPTZ NOT NULL,
    end_time TIMESTAMPTZ,
    reason_code TEXT NOT NULL,
    duration_seconds INTEGER DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_downtime_machine ON downtime_events (machine_id, start_time DESC);
