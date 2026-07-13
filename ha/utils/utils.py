import os
import socket
from datetime import datetime
import psutil


class Utils:
    TIMESTAMP_FORMAT = "%Y-%m-%d %H:%M"
    HOSTNAME: str = "homeassistant"
    MAC_ADDRESS: str = "E4:5F:01:B4:C5:7C"
    MODEL: str = "Raspberry Pi 4 Model B"

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
                or psutil.net_if_addrs().get("wlan0", None),
            )
        )[0].address
        mac = Utils.MAC_ADDRESS or mac
        return mac.replace(":", "")

    @staticmethod
    def detect_model() -> str:
        if os.name == "nt":
            return Utils.MODEL or "MODEL"

        with open("/proc/device-tree/model") as f:
            model = f.read()
        return Utils.MODEL or model.rstrip("\x00")

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
