import json
import argparse
import logging
from ha.mqtt.mqtt import MQTT
from ha.utils.utils import Utils
from ha.utils.my_psutil import Mypsutil, Fields

logger = logging.getLogger(__name__)


def flat_dict(d: dict, parent_key: str = "", sep: str = ".") -> dict:
    items = []
    for k, v in d.items():
        new_key = f"{parent_key}{sep}{k}" if parent_key else k
        if isinstance(v, dict):
            items.extend(flat_dict(v, new_key, sep=sep).items())
        else:
            items.append((new_key, v))
    return dict(items)


class SensorConfig:
    def __init__(
        self,
        name: str,
        fields: list[Fields],
        unit: str | None = None,
        device_class: str | None = None,
        source: "SensorConfig | None" = None,
    ) -> None:
        if unit is None and source is None:
            raise ValueError(f"SensorConfig '{name}': unit or source must be provided")

        model = Utils.detect_model()
        path = ".".join(f.value for f in fields)
        uid = Utils.get_unique_id([f.value for f in fields])

        self.name = f"{Utils.get_host_name()} {name}"
        self.unique_id = uid
        self.object_id = uid
        self.state_class = "measurement"
        self.state_topic = f"rpi/{Utils.NAME()}/hardware"
        self.platform = "mqtt"
        self.unit_of_measurement = unit if unit is not None else source.unit_of_measurement
        self.value_template = f"{{{{ value_json.{path} }}}}"
        self.device = {
            "name": model,
            "manufacturer": "RPi",
            "model": model,
            "identifiers": [Utils.get_mac_address(), model],
        }
        resolved_dc = device_class if device_class is not None else getattr(source, "device_class", None)
        if resolved_dc is not None:
            self.device_class = resolved_dc

    def as_dict(self) -> dict:
        return {k: v for k, v in self.__dict__.items() if not k.startswith("_")}


class RPi:
    @staticmethod
    def make_sensors() -> list[SensorConfig]:
        core1 = SensorConfig("Core1 Temp", [Fields.CPU, Fields.TEMPERATURE, Fields.CORE_1], "°C", "temperature")
        disk_total = SensorConfig("Disk Total", [Fields.DISK, Fields.TOTAL], "GB")
        memory_total = SensorConfig("Memory Total", [Fields.MEMORY, Fields.TOTAL], "GB")
        load_c_1 = SensorConfig("Load 1min", [Fields.LOAD, Fields.MIN_1], "%")
        sd_hc = SensorConfig("Write Speed", [Fields.SD_WRITE_SPEED, Fields.TOTAL], "MB/s")

        return [
            core1,
            SensorConfig("Core2 Temp", [Fields.CPU, Fields.TEMPERATURE, Fields.CORE_2], source=core1),
            SensorConfig("Core3 Temp", [Fields.CPU, Fields.TEMPERATURE, Fields.CORE_3], source=core1),
            SensorConfig("Core4 Temp", [Fields.CPU, Fields.TEMPERATURE, Fields.CORE_4], source=core1),

            disk_total,
            SensorConfig("Disk Available", [Fields.DISK, Fields.AVAILABLE], source=disk_total),
            SensorConfig("Disk Used", [Fields.DISK, Fields.USED], "%"),
            SensorConfig("Disk Used Percent", [Fields.DISK, Fields.PERCENT], "%"),

            memory_total,
            SensorConfig("Memory Available", [Fields.MEMORY, Fields.AVAILABLE], source=memory_total),
            SensorConfig("Memory Used", [Fields.MEMORY, Fields.USED], "%"),
            SensorConfig("Memory Used Percent", [Fields.MEMORY, Fields.PERCENT], "%"),

            SensorConfig("CPU Used Percent", [Fields.CPU, Fields.PERCENT], "%"),

            load_c_1,
            SensorConfig("Load 5min", [Fields.LOAD, Fields.MIN_5], source=load_c_1),
            SensorConfig("Load 15min", [Fields.LOAD, Fields.MIN_15], source=load_c_1),

            sd_hc,
        ]

    @staticmethod
    def publish_config(mqtt: MQTT, sensors: list[SensorConfig]) -> None:
        name = Utils.NAME()
        for sensor in sensors:
            data = sensor.as_dict()
            logger.info("Publishing config for %s", data["name"])
            mqtt.publish(
                f"homeassistant/sensor/{name}/{data['unique_id']}/config",
                json.dumps(data),
            )

    @staticmethod
    def publish_data(mqtt: MQTT) -> None:
        topic = f"rpi/{Utils.NAME()}/hardware"
        data = Mypsutil.get_all_stat()
        logger.debug("%s %s", topic, data)
        mqtt.publish(topic=topic, msg=json.dumps(data))


def main() -> None:
    parser = argparse.ArgumentParser(
        description="A script to send RPi hardware data to MQTT broker"
    )
    parser.add_argument("--send_config", action="store_true", default=False, help="Send configuration data")
    parser.add_argument("--send_data", action="store_true", default=False, help="Send hardware data")
    parser.add_argument("--model", type=str, default=None, help="Specify the model")
    parser.add_argument("--mac_address", type=str, default=None, help="Specify the MAC address")
    parser.add_argument("--hostname", type=str, default=None, help="Specify the hostname")
    args = parser.parse_args()

    if args.model:
        Utils.MODEL = args.model
    if args.mac_address:
        Utils.MAC_ADDRESS = args.mac_address
    if args.hostname:
        Utils.HOSTNAME = args.hostname

    mqtt = MQTT(client_name=Utils.NAME())
    mqtt.connect_mqtt()

    sensors = RPi.make_sensors()

    if args.send_config:
        RPi.publish_config(mqtt, sensors)

    if args.send_data:
        RPi.publish_data(mqtt)

    mqtt.disconnect()


if __name__ == "__main__":
    main()
