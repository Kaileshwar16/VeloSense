CREATE TABLE IF NOT EXISTS fleets (fleet_id VARCHAR(4) PRIMARY KEY, name TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS vehicles (
    vehicle_id VARCHAR(7) PRIMARY KEY,
    vin VARCHAR(17) UNIQUE NOT NULL,
    fleet_id VARCHAR(4) NOT NULL REFERENCES fleets(fleet_id),
    oem TEXT NOT NULL, model TEXT NOT NULL,
    fuel_type TEXT NOT NULL CHECK (fuel_type IN ('EV', 'ICE')),
    manufacture_year INTEGER NOT NULL,
    home_region TEXT NOT NULL,
    odometer_km DOUBLE PRECISION NOT NULL CHECK (odometer_km >= 0)
);
CREATE INDEX IF NOT EXISTS vehicles_fleet_idx ON vehicles(fleet_id, vehicle_id);
CREATE TABLE IF NOT EXISTS alert_rules (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    fleet_id VARCHAR(4) REFERENCES fleets(fleet_id),
    type TEXT NOT NULL, threshold DOUBLE PRECISION NOT NULL,
    enabled BOOLEAN NOT NULL DEFAULT TRUE
);
