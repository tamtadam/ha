from __future__ import annotations

from typing import Any, Dict, Iterable, Tuple

import appdaemon.plugins.hass.hassapi as hass

from ha.utils.my_psutil import Mypsutil, Fields
from ha.utils.utils import Utils


def flat_dict(
    d: dict, parent_key: str = "", sep: str = ".", skippable_keys: set[str] = None
) -> dict:
    if skippable_keys is None:
        skippable_keys = set()
    items: list[Tuple[str, Any]] = []
    for k, v in d.items():
        if k in skippable_keys:
            continue
        new_key = f"{parent_key}{sep}{k}" if parent_key else k
        if isinstance(v, dict):
            items.extend(
                flat_dict(v, new_key, sep=sep, skippable_keys=skippable_keys).items()
            )
        else:
            items.append((new_key, v))
    return dict(items)


class MetricsLogic:
    @staticmethod
    def collect_metrics() -> Dict[str, Any]:
        data = Mypsutil.get_all_stat()

        if any(isinstance(v, dict) for v in data.values()):
            data = flat_dict(
                d=data,
                parent_key=Utils.get_host_name(),
                sep="_",
                skippable_keys={
                    Fields.TIMESTAMP.value,
                    Fields.PROCESSES.value,
                    Fields.NET_IO_COUNTERS.value,
                    Fields.NICE.value,
                    Fields.CPU_TIMES_PERCENT.value,
                    Fields.CONTAINERS.value,
                    Fields.CPU_FREQ.value,
                },
            )
        return data

    @staticmethod
    def to_sensor_states(data: Dict[str, Any]) -> Iterable[Tuple[str, Any]]:
        for key, value in data.items():
            if isinstance(value, (int, float, str)):
                safe_key = str(key).replace(".", "_")
                entity_id = f"sensor.{safe_key}"
                yield entity_id, value


class SystemMetricsApp(hass.Hass):
    def initialize(self):
        self.log(f"SystemMetricsApp started for {Utils.NAME()}")
        self.run_every(self.publish_metrics, "now", 600)

    def publish_metrics(self, kwargs):
        data = MetricsLogic.collect_metrics()
        self.log(f"Collected {len(data)} metrics, publishing...")
        for entity_id, state in MetricsLogic.to_sensor_states(data):
            self.log(f"Publishing {entity_id} = {state}")
            self.set_state(entity_id, state=state)


class TestRunner:
    def run_once(self, limit: int = 50) -> None:
        data = MetricsLogic.collect_metrics()
        pairs = list(MetricsLogic.to_sensor_states(data))

        print(f"Collected keys: {len(data)}")
        print(f"Sensor writes:  {len(pairs)}")
        print("Sample writes:")
        for entity_id, state in pairs[:limit]:
            print(f"  {entity_id} = {state}")


if __name__ == "__main__":
    TestRunner().run_once()
