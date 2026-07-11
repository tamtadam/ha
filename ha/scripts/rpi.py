import json
import argparse
from ha.mqtt.mqtt import MQTT
from ha.utils.utils import Utils
from ha.utils.my_psutil import Mypsutil, Fields


class MyArgs:
    def __init__(self, parser: argparse.ArgumentParser):
        self.args = parser.parse_args()
        self.send_config = self.args.send_config
        self.send_data = self.args.send_data
        self.model = self.args.model
        self.mac_address = self.args.mac_address
        self.hostname = self.args.hostname

    def __str__(self):
        return f"MyArgs(send_config={self.send_config}, send_data={self.send_data})"


parser = argparse.ArgumentParser(
    description="A script to send RPi hardware data to MQTT broker"
)
parser.add_argument(
    "--send_config", action="store_true", help="Send configuration data", default=False
)
parser.add_argument(
    "--send_data", action="store_true", help="Send hardware data", default=False
)
parser.add_argument("--model", type=str, help="Specify the model", default=None)
parser.add_argument(
    "--mac_address", type=str, help="Specify the MAC address", default=None
)
parser.add_argument("--hostname", type=str, help="Specify the hostname", default=None)
args = MyArgs(parser)

if args.model:
    Utils.MODEL = args.model

if args.mac_address:
    Utils.MAC_ADDRESS = args.mac_address

if args.hostname:
    Utils.HOSTNAME = args.hostname

NAME = Utils.NAME()


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
    _DEVICE = {
        "name": Utils.detect_model(),
        "manufacturer": "RPi",
        "model": Utils.detect_model(),
        "identifiers": [Utils.get_mac_address(), Utils.detect_model()],
    }

    def __init__(
        self,
        name: str,
        fields: list[Fields],
        unit: str | None = None,
        device_class: str | None = None,
        source: "SensorConfig | None" = None,
    ):
        path = ".".join(f.value for f in fields)
        uid = Utils.get_unique_id([f.value for f in fields])
        self.name = f"{Utils.get_host_name()} {name}"
        self.unique_id = uid
        self.object_id = uid
        self.state_class = "measurement"
        self.state_topic = f"rpi/{NAME}/hardware"
        self.platform = "mqtt"
        self.unit_of_measurement = unit if unit is not None else source.unit_of_measurement
        self.value_template = f"{{{{ value_json.{path} }}}}"
        self.device = self._DEVICE
        resolved_dc = device_class if device_class is not None else getattr(source, "device_class", None)
        if resolved_dc is not None:
            self.device_class = resolved_dc

    def as_dict(self) -> dict:
        return {k: v for k, v in self.__dict__.items() if not k.startswith("_")}


class RPi:
    mqtt = MQTT(client_name=f"{NAME}")
    topic = f"rpi/{NAME}/hardware"

    core1 = SensorConfig("Core1 Temp", [Fields.CPU, Fields.TEMPERATURE, Fields.CORE_1], "°C", "temperature")
    core2 = SensorConfig("Core2 Temp", [Fields.CPU, Fields.TEMPERATURE, Fields.CORE_2], source=core1)
    core3 = SensorConfig("Core3 Temp", [Fields.CPU, Fields.TEMPERATURE, Fields.CORE_3], source=core1)
    core4 = SensorConfig("Core4 Temp", [Fields.CPU, Fields.TEMPERATURE, Fields.CORE_4], source=core1)

    disk_total     = SensorConfig("Disk Total",          [Fields.DISK, Fields.TOTAL],     "GB")
    disk_available = SensorConfig("Disk Available",      [Fields.DISK, Fields.AVAILABLE], source=disk_total)
    disk_used      = SensorConfig("Disk Used",           [Fields.DISK, Fields.USED],      "%")
    disk_percent   = SensorConfig("Disk Used Percent",   [Fields.DISK, Fields.PERCENT],   "%")

    memory_total     = SensorConfig("Memory Total",           [Fields.MEMORY, Fields.TOTAL],     "GB")
    memory_available = SensorConfig("Memory Available",       [Fields.MEMORY, Fields.AVAILABLE], source=memory_total)
    memory_used      = SensorConfig("Memory Used",            [Fields.MEMORY, Fields.USED],      "%")
    memory_percent   = SensorConfig("Memory Used Percent",    [Fields.MEMORY, Fields.PERCENT],   "%")

    cpu_percent = SensorConfig("CPU Used Percent", [Fields.CPU, Fields.PERCENT], "%")

    load_c_1  = SensorConfig("Load 1min",  [Fields.LOAD, Fields.MIN_1],  "%")
    load_c_5  = SensorConfig("Load 5min",  [Fields.LOAD, Fields.MIN_5],  source=load_c_1)
    load_c_15 = SensorConfig("Load 15min", [Fields.LOAD, Fields.MIN_15], source=load_c_1)

    sd_hc = SensorConfig("Write Speed", [Fields.SD_WRITE_SPEED, Fields.TOTAL], "MB/s")

    @classmethod
    def publish_config(cls):
        for sensor in [
            cls.core1, cls.core2, cls.core3, cls.core4,
            cls.disk_total, cls.disk_available, cls.disk_used, cls.disk_percent,
            cls.memory_total, cls.memory_available, cls.memory_used, cls.memory_percent,
            cls.cpu_percent,
            cls.load_c_1, cls.load_c_5, cls.load_c_15,
            cls.sd_hc,
        ]:
            data = sensor.as_dict()
            print(f"Publishing config for {data['name']}")
            cls.mqtt.publish(
                f"homeassistant/sensor/{NAME}/{data['unique_id']}/config", json.dumps(data)
            )

    @classmethod
    def publish_data(cls):
        data = Mypsutil.get_all_stat()
        print(cls.topic, data)

        cls.mqtt.publish(topic=cls.topic, msg=json.dumps(data))


if __name__ == "__main__":
    RPi.mqtt.connect_mqtt()

    if args.send_config:
        RPi.publish_config()

    if args.send_data:
        RPi.publish_data()

    RPi.mqtt.disconnect()
