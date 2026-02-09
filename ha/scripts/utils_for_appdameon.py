import appdaemon.plugins.hass.hassapi as hass
from ha.utils.my_psutil import Mypsutil
from ha.utils.utils import Utils

NAME = f"{Utils.get_host_name()}_{Utils.get_mac_address()}"


def get_unique_id(fields: list[str]) -> str:
    return f"{Utils.get_host_name()}_{'_'.join(fields)}"


def flat_dict(d: dict, parent_key: str = "", sep: str = ".") -> dict:
    items = []
    for k, v in d.items():
        new_key = f"{parent_key}{sep}{k}" if parent_key else k
        if isinstance(v, dict):
            items.extend(flat_dict(v, new_key, sep=sep).items())
        else:
            items.append((new_key, v))
    return dict(items)


class SystemMetrics(hass.Hass):
    def initialize(self):
        self.run_every(self.publish_metrics, "now", 600)

    def publish_metrics(self, kwargs):
        data = Mypsutil.get_all_stat()

        for key, value in data.items():
            if isinstance(value, (int, float, str)):
                entity_id = f"sensor.{key}"

                self.set_state(entity_id, state=value)
