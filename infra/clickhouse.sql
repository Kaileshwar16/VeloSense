CREATE DATABASE IF NOT EXISTS valeosense;
CREATE TABLE IF NOT EXISTS valeosense.telemetry (
    event_id UUID, vehicle_id String, vin String, fleet_id LowCardinality(String),
    timestamp DateTime64(3, 'UTC'), seq UInt64,
    lat Float64, lon Float64, speed_kmh Float32, heading_deg Float32,
    engine_on Bool, fuel_pct Nullable(Float32), soc_pct Nullable(Float32),
    odometer_km Float64, engine_temp_c Float32, dtc Array(String),
    event_type LowCardinality(String), source_oem LowCardinality(String), schema_version UInt8,
    idling_seconds Float64, estimated_fuel_l Float64, estimated_cost Float64,
    detected_types Array(String), late Bool
) ENGINE = ReplacingMergeTree
PARTITION BY toYYYYMM(timestamp)
ORDER BY (vehicle_id, timestamp, event_id)
TTL timestamp + INTERVAL 30 DAY DELETE
SETTINGS index_granularity = 1024;
CREATE TABLE IF NOT EXISTS valeosense.alerts (
    alert_id UUID, event_id UUID, vehicle_id String, fleet_id LowCardinality(String),
    timestamp DateTime64(3, 'UTC'), type LowCardinality(String),
    start_timestamp DateTime64(3, 'UTC'), duration_seconds Float64,
    estimated_fuel_l Float64, estimated_cost Float64, detail String
) ENGINE = ReplacingMergeTree
PARTITION BY toYYYYMM(timestamp)
ORDER BY (vehicle_id, timestamp, alert_id)
TTL timestamp + INTERVAL 30 DAY DELETE;
CREATE VIEW IF NOT EXISTS valeosense.telemetry_read AS SELECT * FROM valeosense.telemetry FINAL;
CREATE VIEW IF NOT EXISTS valeosense.alerts_read AS SELECT * FROM valeosense.alerts FINAL;
