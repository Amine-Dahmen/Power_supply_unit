import random


class Meter:
    def __init__(
        self,
        meter_type: str,
        unit: str,
        increment_min: float,
        increment_max: float,
        rng: random.Random | None = None,
    ):
        self.meter_type = meter_type
        self.unit = unit
        self.increment_min = increment_min
        self.increment_max = increment_max
        self.cumulative_value = 0.0
        self._rng = rng or random.Random()

    def tick(self) -> float:
        delta = round(self._rng.uniform(self.increment_min, self.increment_max), 3)
        self.cumulative_value = round(self.cumulative_value + delta, 3)
        return self.cumulative_value

    def reset(self):
        self.cumulative_value = 0.0

    @property
    def reading(self) -> dict:
        return {
            "meterType": self.meter_type,
            "value": self.cumulative_value,
            "unit": self.unit,
        }
