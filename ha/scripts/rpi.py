import argparse
import json
import logging
from ha.publishers.base_sensor_publisher import BaseSensorPublisher
from ha.utils.utils import (
    Utils,
    SensorConfig,
    UnitOfTemperature,
    UnitOfInformation,
    UnitOfDataRate,
    PERCENTAGE,
)
from ha.utils.my_psutil import Mypsutil, Fields

logger = logging.getLogger(__name__)


class RPi(BaseSensorPublisher):
    def __init__(self) -> None:
        super().__init__(client_name=Utils.NAME(), sensors=self.make_sensors())

    @staticmethod
    def make_sensors() -> list[SensorConfig]:
        core1 = SensorConfig("Core1 Temp", [Fields.CPU, Fields.TEMPERATURE, Fields.CORE_1], UnitOfTemperature.CELSIUS, "temperature")
        disk_total = SensorConfig("Disk Total", [Fields.DISK, Fields.TOTAL], UnitOfInformation.GIGABYTES)
        memory_total = SensorConfig("Memory Total", [Fields.MEMORY, Fields.TOTAL], UnitOfInformation.GIGABYTES)
        load_c_1 = SensorConfig("Load 1min", [Fields.LOAD, Fields.MIN_1], PERCENTAGE)
        sd_hc = SensorConfig("Write Speed", [Fields.SD_WRITE_SPEED, Fields.TOTAL], UnitOfDataRate.MEGABYTES_PER_SECOND)

        return [
            core1,
            SensorConfig("Core2 Temp", [Fields.CPU, Fields.TEMPERATURE, Fields.CORE_2], source=core1),
            SensorConfig("Core3 Temp", [Fields.CPU, Fields.TEMPERATURE, Fields.CORE_3], source=core1),
            SensorConfig("Core4 Temp", [Fields.CPU, Fields.TEMPERATURE, Fields.CORE_4], source=core1),
            disk_total,
            SensorConfig("Disk Available", [Fields.DISK, Fields.AVAILABLE], source=disk_total),
            SensorConfig("Disk Used", [Fields.DISK, Fields.USED], PERCENTAGE),
            SensorConfig("Disk Used Percent", [Fields.DISK, Fields.PERCENT], PERCENTAGE),
            memory_total,
            SensorConfig("Memory Available", [Fields.MEMORY, Fields.AVAILABLE], source=memory_total),
            SensorConfig("Memory Used", [Fields.MEMORY, Fields.USED], PERCENTAGE),
            SensorConfig("Memory Used Percent", [Fields.MEMORY, Fields.PERCENT], PERCENTAGE),
            SensorConfig("CPU Used Percent", [Fields.CPU, Fields.PERCENT], PERCENTAGE),
            load_c_1,
            SensorConfig("Load 5min", [Fields.LOAD, Fields.MIN_5], source=load_c_1),
            SensorConfig("Load 15min", [Fields.LOAD, Fields.MIN_15], source=load_c_1),
            sd_hc,
        ]

    def publish_data(self, dry_run: bool = False) -> None:
        topic = f"rpi/{Utils.NAME()}/hardware"
        data = Mypsutil.get_all_stat()
        logger.debug("%s %s", topic, data)
        if dry_run:
            print(json.dumps(data, indent=2))
            return

        super().publish_data(topic, data)


def main() -> None:
    parser = argparse.ArgumentParser(description="A script to send RPi hardware data to MQTT broker")
    parser.add_argument("--send_config", action="store_true", default=False, help="Send configuration data")
    parser.add_argument("--send_data", action="store_true", default=False, help="Send hardware data")
    parser.add_argument(
        "--dry_run",
        action="store_true",
        help="Print hardware data to stdout instead of publishing it; use with --send_data",
    )
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

    publisher = RPi()
    should_connect = args.send_config or (args.send_data and not args.dry_run)
    if should_connect:
        publisher.connect_mqtt()

    if args.send_config:
        publisher.publish_config()

    if args.send_data:
        publisher.publish_data(dry_run=args.dry_run)

    if should_connect:
        publisher.disconnect()


if __name__ == "__main__":
    main()
