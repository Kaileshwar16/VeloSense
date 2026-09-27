"""Deterministic synthetic registry. No owner or driver information."""
import csv
import random
from pathlib import Path

from shared.models import Vehicle

CATALOG = (
    ('Volvo', 'XC40', 'EV'), ('Tata', 'Nexon', 'EV'), ('Hyundai', 'Creta', 'ICE'),
    ('Mahindra', 'Bolero', 'ICE'), ('Toyota', 'Innova', 'ICE'), ('Kia', 'EV6', 'EV'),
)
REGIONS = {'Chennai': (13.0827, 80.2707), 'Bengaluru': (12.9716, 77.5946),
           'Mumbai': (19.0760, 72.8777), 'Delhi': (28.6139, 77.2090)}


def vehicles(count: int = 100000, seed: int = 42):
    if not 1 <= count <= 100000:
        raise ValueError('vehicle count must be 1..100000')
    rng = random.Random(seed)
    for index in range(1, count + 1):
        oem, model, fuel = rng.choice(CATALOG)
        yield Vehicle(vehicle_id=f'V{index:06d}', vin=f'SYN{index:014d}',
                      fleet_id=f'F{rng.randint(1, 100):03d}', oem=oem, model=model,
                      fuel_type=fuel, manufacture_year=rng.randint(2018, 2025),
                      home_region=rng.choice(tuple(REGIONS)),
                      odometer_km=round(rng.uniform(100, 150000), 1))


def write_registry(path: Path, count: int = 100000, seed: int = 42) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=list(Vehicle.model_fields))
        writer.writeheader()
        for vehicle in vehicles(count, seed):
            writer.writerow(vehicle.model_dump())
    return count
