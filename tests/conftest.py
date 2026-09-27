from datetime import datetime, timezone

import pytest

from simulator.generator import Generator
from simulator.vehicle_factory import vehicles


@pytest.fixture
def event():
    generator = Generator(list(vehicles(1)), start=datetime(2026, 9, 27, tzinfo=timezone.utc))
    generator.force(0, "NORMAL", 100)
    return generator.tick(0, generator.start)[0]
