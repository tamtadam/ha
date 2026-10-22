import argparse
import json
import logging
import re
import subprocess
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

from paho.mqtt import client as mqtt_client

from ha.publishers.base_sensor_publisher import BaseSensorPublisher
from ha.utils.utils import SensorConfig, Utils

logger = logging.getLogger(__name__)

DATA_EXPIRY_SECONDS = 2 * 24 * 60 * 60


@dataclass(frozen=True)
class SystemdService:
    unit: str
    timer: str | None = None


SERVICES = {
    "systemctl_light": SystemdService(unit="ha-light-control-konyha.service"),
    "systemctl_gas": SystemdService(unit="ha-gas-data.service", timer="ha-gas-data.timer"),
    "systemctl_rpi": SystemdService(unit="ha-rpi-data.service", timer="ha-rpi-data.timer"),
}

SERVICE_DETAILS = (
    ("Load State", "load_state"),
    ("Unit File", "unit_file"),
    ("Unit File State", "unit_file_state"),
    ("Unit File Preset", "unit_file_preset"),
    ("Result", "result"),
    ("Exec Main Status", "exec_main_status"),
    ("Invocation ID", "invocation_id"),
    ("Main PID", "main_pid"),
    ("Tasks Current", "tasks_current"),
    ("Tasks Limit", "tasks_max"),
    ("CPU Time (seconds)", "cpu_seconds"),
    ("Control Group", "control_group"),
)


class ServiceStatus(BaseSensorPublisher):
    def __init__(self) -> None:
        super().__init__(client_name=Utils.NAME(), sensors=self.make_sensors(), protocol=mqtt_client.MQTTv5)

    @staticmethod
    def get_device_config_topic() -> str:
        object_id = re.sub(r"[^a-zA-Z0-9_-]", "_", Utils.NAME())
        return f"homeassistant/device/systemctl/{object_id}/config"

    def publish_config(self) -> None:
        if not self.sensors:
            return

        sensor_configs = [sensor.as_dict() for sensor in self.sensors]
        components = {}
        for sensor, config in zip(self.sensors, sensor_configs, strict=True):
            component = {
                key: value
                for key, value in config.items()
                if key not in {"device", "platform", "state_topic"}
            }
            components[sensor.unique_id] = {"platform": "sensor", **component}

        payload = {
            "device": sensor_configs[0]["device"],
            "origin": {"name": "ha-service-status"},
            "components": components,
            "state_topic": self.get_topic(),
        }
        self.publish(topic=self.get_device_config_topic(), msg=json.dumps(obj=payload))

    @staticmethod
    def get_topic() -> str:
        return f"rpi/{Utils.NAME()}/systemctl"

    @staticmethod
    def make_sensors() -> list[SensorConfig]:
        sensors = []
        for name, service in SERVICES.items():
            title = name.replace("_", " ").title().replace("Rpi", "RPI")
            sensors.append(ServiceStatus.make_sensor(label=f"{title} Service", key=f"{name}_status"))
            sensors.extend(
                ServiceStatus.make_sensor(label=f"{title} {label}", key=f"{name}_{key}")
                for label, key in SERVICE_DETAILS
            )
            if service.timer is None:
                sensors.append(
                    ServiceStatus.make_sensor(
                        label=f"{title} Started",
                        key=f"{name}_started",
                        device_class="timestamp",
                    )
                )
            else:
                sensors.append(
                    ServiceStatus.make_sensor(
                        label=f"{title} Last Run",
                        key=f"{name}_last_run",
                        device_class="timestamp",
                    )
                )
                sensors.append(
                    ServiceStatus.make_sensor(
                        label=f"{title} Timer Status",
                        key=f"{name}_timer_status",
                    )
                )
                sensors.append(
                    ServiceStatus.make_sensor(
                        label=f"{title} Next Run",
                        key=f"{name}_next_run",
                        device_class="timestamp",
                    )
                )
        return sensors

    @staticmethod
    def make_sensor(label: str, key: str, device_class: str | None = None) -> SensorConfig:
        return SensorConfig(
            name=label,
            fields=[key],
            device_class=device_class,
            state_topic=ServiceStatus.get_topic(),
            state_class=None,
            unique_id=Utils.get_unique_id(fields=["service", key]),
        )

    @staticmethod
    def show(*, unit: str, properties: Sequence[str]) -> dict[str, str]:
        output = subprocess.run(
            args=["systemctl", "show", unit, f"--property={','.join(properties)}"],
            capture_output=True,
            text=True,
            check=True,
            timeout=10,
        ).stdout
        return dict(line.split("=", 1) for line in output.splitlines() if "=" in line)

    @staticmethod
    def parse_timestamp(value: str) -> str | None:
        if not value or value == "n/a":
            return None
        # `systemctl show` prints local time plus a zone abbreviation ("Sun 2026-10-11 21:50:08 CEST"), so the time is read as local.
        _weekday, date, clock = value.split()[:3]
        return datetime.strptime(f"{date} {clock}", "%Y-%m-%d %H:%M:%S").astimezone().isoformat()

    @staticmethod
    def parse_cpu_seconds(value: str) -> str | None:
        if not value or value == "[not set]":
            return None
        try:
            return f"{int(value) / 1_000_000_000:.3f}"
        except ValueError:
            logger.warning("Unexpected CPUUsageNSec value from systemd: %r", value)
            return None

    def get_data(self) -> dict[str, str | None]:
        data: dict[str, str | None] = {}
        for name, service in SERVICES.items():
            state = self.show(
                unit=service.unit,
                properties=(
                    "LoadState",
                    "ActiveState",
                    "ActiveEnterTimestamp",
                    "FragmentPath",
                    "UnitFileState",
                    "UnitFilePreset",
                    "Result",
                    "ExecMainStatus",
                    "InvocationID",
                    "MainPID",
                    "TasksCurrent",
                    "TasksMax",
                    "CPUUsageNSec",
                    "ControlGroup",
                ),
            )
            data[f"{name}_status"] = "not-installed" if state["LoadState"] == "not-found" else state["ActiveState"]
            data[f"{name}_load_state"] = state.get("LoadState")
            data[f"{name}_unit_file"] = state.get("FragmentPath")
            data[f"{name}_unit_file_state"] = state.get("UnitFileState")
            data[f"{name}_unit_file_preset"] = state.get("UnitFilePreset")
            data[f"{name}_result"] = state.get("Result")
            data[f"{name}_exec_main_status"] = state.get("ExecMainStatus")
            data[f"{name}_invocation_id"] = state.get("InvocationID")
            data[f"{name}_main_pid"] = state.get("MainPID")
            data[f"{name}_tasks_current"] = state.get("TasksCurrent")
            data[f"{name}_tasks_max"] = state.get("TasksMax")
            data[f"{name}_cpu_seconds"] = self.parse_cpu_seconds(value=state.get("CPUUsageNSec", ""))
            data[f"{name}_control_group"] = state.get("ControlGroup")
            if service.timer is None:
                data[f"{name}_started"] = self.parse_timestamp(value=state.get("ActiveEnterTimestamp", ""))
            else:
                timer = self.show(
                    unit=service.timer,
                    properties=("LoadState", "ActiveState", "LastTriggerUSec", "NextElapseUSecRealtime"),
                )
                data[f"{name}_timer_status"] = (
                    "not-installed" if timer.get("LoadState") == "not-found" else timer.get("ActiveState")
                )
                data[f"{name}_last_run"] = self.parse_timestamp(value=timer.get("LastTriggerUSec", ""))
                data[f"{name}_next_run"] = self.parse_timestamp(value=timer.get("NextElapseUSecRealtime", ""))
        return data

    def publish_data(self, dry_run: bool = False) -> None:
        topic = self.get_topic()
        data = self.get_data()
        logger.debug("%s %s", topic, data)
        if dry_run:
            print(json.dumps(obj=data, indent=2))
            return

        self.publish(
            topic=topic,
            msg=json.dumps(obj=data),
            message_expiry=DATA_EXPIRY_SECONDS,
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="A script to send systemd service states to MQTT broker")
    parser.add_argument("--send_config", "--send-config", dest="send_config", action="store_true", help="Send configuration data")
    parser.add_argument("--send_data", "--send-data", dest="send_data", action="store_true", help="Send service states")
    parser.add_argument(
        "--dry_run",
        "--dry-run",
        dest="dry_run",
        action="store_true",
        help="Print service states to stdout instead of publishing them; use with --send_data",
    )
    args = parser.parse_args()

    publisher = ServiceStatus()
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
