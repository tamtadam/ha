import json
from typing import Any

from ha.mqtt.mqtt import MQTT
from ha.utils.utils import SensorConfig, Utils


class BaseSensorPublisher(MQTT):
    def __init__(
        self,
        *args: Any,
        sensors: list[SensorConfig] | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(*args, **kwargs)
        self.sensors = sensors or []

    def get_config_topic(self, sensor: SensorConfig) -> str:
        return f"homeassistant/sensor/{Utils.NAME()}/{sensor.unique_id}/config"

    def publish_config(self) -> None:
        for sensor in self.sensors:
            payload = sensor.as_dict()
            self.publish(self.get_config_topic(sensor), json.dumps(payload))

    def publish_data(self, topic: str, data: dict) -> None:
        self.publish(topic, json.dumps(data))
