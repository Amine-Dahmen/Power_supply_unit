import random
from src.terminal.meter import Meter


def test_tick_increments_value(meter):
    assert meter.cumulative_value == 0.0
    val1 = meter.tick()
    assert 0.05 <= val1 <= 0.25
    assert meter.cumulative_value == val1

    val2 = meter.tick()
    assert val2 > val1
    assert 0.10 <= val2 <= 0.50
    assert meter.cumulative_value == val2


def test_reading_format(meter):
    meter.tick()
    reading = meter.reading
    assert isinstance(reading, dict)
    assert reading["meterType"] == "electricity"
    assert reading["unit"] == "kWh"
    assert isinstance(reading["value"], float)
    assert reading["value"] > 0


def test_reset_zeros_value(meter):
    meter.tick()
    meter.tick()
    assert meter.cumulative_value > 0
    meter.reset()
    assert meter.cumulative_value == 0.0
    assert meter.reading["value"] == 0.0


def test_seeded_random_reproducible():
    meter_a = Meter("gas", "thermie", 0.1, 0.5, rng=random.Random(12345))
    meter_b = Meter("gas", "thermie", 0.1, 0.5, rng=random.Random(12345))

    values_a = [meter_a.tick() for _ in range(10)]
    values_b = [meter_b.tick() for _ in range(10)]

    assert values_a == values_b
