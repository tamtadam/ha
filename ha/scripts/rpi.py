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


class RPi:
    mqtt = MQTT(client_name=f"{NAME}")

    topic = f"rpi/{NAME}/hardware"

    base_config = {
        "name": "RPi Core1 Temp",
        "unique_id": f"{Utils.get_host_name()}_core1_temp",
        "state_class": "measurement",
        "state_topic": f"rpi/{NAME}/hardware",
        "platform": "mqtt",
        "unit_of_measurement": "°C",
        "value_template": "{{ value_json."
        + f".{Fields.CPU.value}.{Fields.TEMPERATURE.value}{Fields.CORE_1.value}"
        + " }}",
        "device": {
            "name": Utils.detect_model(),
            "manufacturer": "RPi",
            "model": Utils.detect_model(),
            "identifiers": [Utils.get_mac_address(), Utils.detect_model()],
        },
    }

    core1 = base_config.copy()
    core1["name"] = f"{Utils.get_host_name()} Core1 Temp"
    core1["device_class"] = "temperature"
    core1["unique_id"] = Utils.get_unique_id(
        [Fields.CPU.value, Fields.TEMPERATURE.value, Fields.CORE_1.value]
    )
    core1["object_id"] = Utils.get_unique_id(
        [Fields.CPU.value, Fields.TEMPERATURE.value, Fields.CORE_1.value]
    )
    core1["value_template"] = (
        "{{ value_json."
        + f"{Fields.CPU.value}.{Fields.TEMPERATURE.value}.{Fields.CORE_1.value}"
        + " }}"
    )

    core2 = core1.copy()
    core2["name"] = f"{Utils.get_host_name()} Core2 Temp"
    core2["unique_id"] = Utils.get_unique_id(
        [Fields.CPU.value, Fields.TEMPERATURE.value, Fields.CORE_2.value]
    )
    core2["object_id"] = Utils.get_unique_id(
        [Fields.CPU.value, Fields.TEMPERATURE.value, Fields.CORE_2.value]
    )
    core2["value_template"] = (
        "{{ value_json."
        + f"{Fields.CPU.value}.{Fields.TEMPERATURE.value}.{Fields.CORE_2.value}"
        + " }}"
    )

    core3 = core1.copy()
    core3["name"] = f"{Utils.get_host_name()} Core3 Temp"
    core3["unique_id"] = Utils.get_unique_id(
        [Fields.CPU.value, Fields.TEMPERATURE.value, Fields.CORE_3.value]
    )
    core3["object_id"] = Utils.get_unique_id(
        [Fields.CPU.value, Fields.TEMPERATURE.value, Fields.CORE_3.value]
    )
    core3["value_template"] = (
        "{{ value_json."
        + f"{Fields.CPU.value}.{Fields.TEMPERATURE.value}.{Fields.CORE_3.value}"
        + " }}"
    )

    core4 = core1.copy()
    core4["name"] = f"{Utils.get_host_name()} Core4 Temp"
    core4["unique_id"] = Utils.get_unique_id(
        [Fields.CPU.value, Fields.TEMPERATURE.value, Fields.CORE_4.value]
    )
    core4["object_id"] = Utils.get_unique_id(
        [Fields.CPU.value, Fields.TEMPERATURE.value, Fields.CORE_4.value]
    )
    core4["value_template"] = (
        "{{ value_json."
        + f"{Fields.CPU.value}.{Fields.TEMPERATURE.value}.{Fields.CORE_4.value}"
        + " }}"
    )

    disk_total = base_config.copy()
    disk_total["name"] = f"{Utils.get_host_name()} Disk Total"
    disk_total["unit_of_measurement"] = "GB"
    disk_total["unique_id"] = Utils.get_unique_id(
        [Fields.DISK.value, Fields.TOTAL.value]
    )
    disk_total["object_id"] = Utils.get_unique_id(
        [Fields.DISK.value, Fields.TOTAL.value]
    )
    disk_total["value_template"] = (
        "{{ value_json." + f"{Fields.DISK.value}.{Fields.TOTAL.value}" + " }}"
    )

    disk_available = disk_total.copy()
    disk_available["name"] = f"{Utils.get_host_name()} Disk Available"
    disk_available["unique_id"] = Utils.get_unique_id(
        [Fields.DISK.value, Fields.AVAILABLE.value]
    )
    disk_available["object_id"] = Utils.get_unique_id(
        [Fields.DISK.value, Fields.AVAILABLE.value]
    )
    disk_available["value_template"] = (
        "{{ value_json." + f"{Fields.DISK.value}.{Fields.AVAILABLE.value}" + " }}"
    )

    disk_percent = disk_total.copy()
    disk_percent["name"] = f"{Utils.get_host_name()} Disk Used Percent"
    disk_percent["unique_id"] = Utils.get_unique_id(
        [Fields.DISK.value, Fields.PERCENT.value]
    )
    disk_percent["object_id"] = Utils.get_unique_id(
        [Fields.DISK.value, Fields.PERCENT.value]
    )
    disk_percent["unit_of_measurement"] = "%"
    disk_percent["value_template"] = (
        "{{ value_json." + f"{Fields.DISK.value}.{Fields.PERCENT.value}" + " }}"
    )

    disk_used = disk_total.copy()
    disk_used["name"] = f"{Utils.get_host_name()} Disk Used"
    disk_used["unique_id"] = Utils.get_unique_id([Fields.DISK.value, Fields.USED.value])
    disk_used["object_id"] = Utils.get_unique_id([Fields.DISK.value, Fields.USED.value])
    disk_used["unit_of_measurement"] = "%"
    disk_used["value_template"] = (
        "{{ value_json." + f"{Fields.DISK.value}.{Fields.USED.value}" + " }}"
    )

    memory_total = disk_total.copy()
    memory_total["name"] = f"{Utils.get_host_name()} Memory Total"
    memory_total["unit_of_measurement"] = "GB"
    memory_total["unique_id"] = Utils.get_unique_id(
        [Fields.MEMORY.value, Fields.TOTAL.value]
    )
    memory_total["object_id"] = Utils.get_unique_id(
        [Fields.MEMORY.value, Fields.TOTAL.value]
    )
    memory_total["value_template"] = (
        "{{ value_json." + f"{Fields.MEMORY.value}.{Fields.TOTAL.value}" + " }}"
    )

    memory_available = memory_total.copy()
    memory_available["name"] = f"{Utils.get_host_name()} Memory Available"
    memory_available["unit_of_measurement"] = "GB"
    memory_available["unique_id"] = Utils.get_unique_id(
        [Fields.MEMORY.value, Fields.AVAILABLE.value]
    )
    memory_available["object_id"] = Utils.get_unique_id(
        [Fields.MEMORY.value, Fields.AVAILABLE.value]
    )
    memory_available["value_template"] = (
        "{{ value_json." + f"{Fields.MEMORY.value}.{Fields.AVAILABLE.value}" + " }}"
    )

    memory_used = memory_total.copy()
    memory_used["name"] = f"{Utils.get_host_name()} Memory Used"
    memory_used["unique_id"] = Utils.get_unique_id(
        [Fields.MEMORY.value, Fields.USED.value]
    )
    memory_used["object_id"] = Utils.get_unique_id(
        [Fields.MEMORY.value, Fields.USED.value]
    )
    memory_used["unit_of_measurement"] = "%"
    memory_used["value_template"] = (
        "{{ value_json." + f"{Fields.MEMORY.value}.{Fields.USED.value}" + " }}"
    )

    memory_percent = memory_total.copy()
    memory_percent["name"] = f"{Utils.get_host_name()} Memory Used Percent"
    memory_percent["unique_id"] = Utils.get_unique_id(
        [Fields.MEMORY.value, Fields.PERCENT.value]
    )
    memory_percent["object_id"] = Utils.get_unique_id(
        [Fields.MEMORY.value, Fields.PERCENT.value]
    )
    memory_percent["unit_of_measurement"] = "%"
    memory_percent["value_template"] = (
        "{{ value_json." + f"{Fields.MEMORY.value}.{Fields.PERCENT.value}" + " }}"
    )

    cpu_percent = memory_total.copy()
    cpu_percent["name"] = f"{Utils.get_host_name()} CPU Used Percent"
    cpu_percent["unique_id"] = Utils.get_unique_id(
        [Fields.CPU.value, Fields.PERCENT.value]
    )
    cpu_percent["object_id"] = Utils.get_unique_id(
        [Fields.CPU.value, Fields.PERCENT.value]
    )
    cpu_percent["unit_of_measurement"] = "%"
    cpu_percent["value_template"] = (
        "{{ value_json." + f"{Fields.CPU.value}.{Fields.PERCENT.value}" + " }}"
    )

    load_c_1 = base_config.copy()
    load_c_1["unit_of_measurement"] = "%"
    load_c_1["name"] = f"{Utils.get_host_name()} Load 1min"
    load_c_1["unique_id"] = Utils.get_unique_id([Fields.LOAD.value, Fields.MIN_1.value])
    load_c_1["object_id"] = Utils.get_unique_id([Fields.LOAD.value, Fields.MIN_1.value])
    load_c_1["value_template"] = (
        "{{ value_json." + f"{Fields.LOAD.value}.{Fields.MIN_1.value}" + " }}"
    )

    load_c_5 = load_c_1.copy()
    load_c_5["name"] = f"{Utils.get_host_name()} Load 5min"
    load_c_5["unique_id"] = Utils.get_unique_id([Fields.LOAD.value, Fields.MIN_5.value])
    load_c_5["object_id"] = Utils.get_unique_id([Fields.LOAD.value, Fields.MIN_5.value])
    load_c_5["value_template"] = (
        "{{ value_json." + f"{Fields.LOAD.value}.{Fields.MIN_5.value}" + " }}"
    )

    load_c_15 = load_c_1.copy()
    load_c_15["name"] = f"{Utils.get_host_name()} Load 15min"
    load_c_15["unique_id"] = Utils.get_unique_id(
        [Fields.LOAD.value, Fields.MIN_15.value]
    )
    load_c_15["object_id"] = Utils.get_unique_id(
        [Fields.LOAD.value, Fields.MIN_15.value]
    )
    load_c_15["value_template"] = (
        "{{ value_json." + f"{Fields.LOAD.value}.{Fields.MIN_15.value}" + " }}"
    )

    sd_hc = base_config.copy()
    sd_hc["name"] = f"{Utils.get_host_name()} Write Speed"
    sd_hc["unique_id"] = Utils.get_unique_id(
        [Fields.SD_WRITE_SPEED.value, Fields.TOTAL.value]
    )
    sd_hc["object_id"] = Utils.get_unique_id(
        [Fields.SD_WRITE_SPEED.value, Fields.TOTAL.value]
    )
    sd_hc["unit_of_measurement"] = "MB/s"
    sd_hc["value_template"] = (
        "{{ value_json." + f"{Fields.SD_WRITE_SPEED.value}.{Fields.TOTAL.value}" + " }}"
    )

    @classmethod
    def publish_config(cls):
        for i in [
            RPi.core1,
            RPi.core2,
            RPi.core3,
            RPi.core4,
            RPi.disk_available,
            RPi.disk_total,
            RPi.disk_used,
            RPi.disk_percent,
            RPi.memory_available,
            RPi.memory_total,
            RPi.memory_used,
            RPi.memory_percent,
            RPi.load_c_1,
            RPi.load_c_5,
            RPi.load_c_15,
            RPi.sd_hc,
            RPi.cpu_percent,
        ]:
            print(f"Publishing config for {i['name']}")
            RPi.mqtt.publish(
                f"homeassistant/sensor/{NAME}/{i['unique_id']}/config", json.dumps(i)
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
