import argparse
from pathlib import Path

from simulator.vehicle_factory import write_registry

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=Path("data/vehicles.csv"))
    args = parser.parse_args()
    print(f"Generated {write_registry(args.output)} synthetic vehicles (seed=42): {args.output}")
