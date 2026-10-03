from __future__ import annotations

import os
import socket
import subprocess
import sys
from datetime import datetime
from enum import StrEnum

import psutil


class UnitOfTemperature(StrEnum):
    CELSIUS = "°C"


class UnitOfInformation(StrEnum):
    GIGABYTES = "GB"


class UnitOfDataRate(StrEnum):
    MEGABYTES_PER_SECOND = "MB/s"


PERCENTAGE = "%"


class SensorConfig:
    def __init__(
        self,
        name: str,
        fields: list[str | object],
        unit: str | None = None,
        device_class: str | None = None,
        source: "SensorConfig | None" = None,
        *,
        state_topic: str | None = None,
        state_class: str | None = "measurement",
        device_name: str | None = None,
        identifiers: list[str] | None = None,
        include_host_name: bool = True,
    ) -> None:
        if unit is None and source is None:
            raise ValueError(f"SensorConfig '{name}': unit or source must be provided")

        model = Utils.detect_model()
        path = ".".join(str(f.value) if hasattr(f, "value") else str(f) for f in fields)
        uid = Utils.get_unique_id([str(f.value) if hasattr(f, "value") else str(f) for f in fields])

        self.name = f"{Utils.get_host_name()} {name}" if include_host_name else name
        self.unique_id = uid
        self.object_id = uid
        self.state_class = state_class
        self.state_topic = state_topic or f"rpi/{Utils.NAME()}/hardware"
        self.platform = "mqtt"
        self.unit_of_measurement = unit if unit is not None else source.unit_of_measurement
        self.value_template = f"{{{{ value_json.{path} }}}}"
        self.device = {
            "name": device_name or model,
            "manufacturer": "RPi",
            "model": model,
            "identifiers": identifiers or [Utils.get_mac_address(), model],
        }

        resolved_dc = device_class if device_class is not None else getattr(source, "device_class", None)
        if resolved_dc is not None:
            self.device_class = resolved_dc

    def as_dict(self) -> dict:
        return {k: v for k, v in self.__dict__.items() if not k.startswith("_")}


class Utils:
    TIMESTAMP_FORMAT = "%Y-%m-%d %H:%M"
    HOSTNAME: str = None
    MAC_ADDRESS: str = None
    MODEL: str = None

    @staticmethod
    def get_host_name() -> str:
        return Utils.HOSTNAME or socket.gethostname() or "rpi"

    @staticmethod
    def get_mac_address() -> str:
        if os.name == "nt":
            mac = Utils.MAC_ADDRESS or psutil.net_if_addrs()["Wi-Fi"][0].address
            return mac.replace(":", "")
        mac = list(
            filter(
                lambda item: item.family == psutil.AF_LINK and item.address,
                psutil.net_if_addrs().get("eth0", None)
                or psutil.net_if_addrs().get("wlan0", None)
                or psutil.net_if_addrs().get("en0", None),
            )
        )[0].address
        mac = Utils.MAC_ADDRESS or mac
        return mac.replace(":", "")

    @staticmethod
    def detect_model() -> str:
        if Utils.MODEL:
            return Utils.MODEL

        if os.name == "nt":
            return "MODEL"

        if sys.platform == "darwin":
            return subprocess.check_output(
                ["sysctl", "-n", "hw.model"],
                text=True,
            ).strip()

        with open("/proc/device-tree/model") as f:
            model = f.read()
        return model.rstrip("\x00")

    @staticmethod
    def get_timestamp() -> datetime:
        return datetime.now()

    @staticmethod
    def get_formatted_timestamp() -> str:
        return Utils.get_timestamp().strftime(Utils.TIMESTAMP_FORMAT)

    @staticmethod
    def NAME() -> str:
        return f"{Utils.get_host_name()}_{Utils.get_mac_address()}"

    @staticmethod
    def get_unique_id(fields: list[str]) -> str:
        return f"{Utils.get_host_name()}_{'_'.join(fields)}"
