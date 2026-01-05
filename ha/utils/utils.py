import os
import socket
from datetime import datetime
import psutil

class Utils():
    TIMESTAMP_FORMAT = '%Y-%m-%d %H:%M'

    @staticmethod
    def get_host_name():
        return socket.gethostname() or "rpi"

    def get_mac_address():
        if os.name == 'nt':
            return 'MAC_ADDRESS'

        else:
            mac = list( filter( lambda item: item.family == psutil.AF_LINK and item.address, psutil.net_if_addrs()[ 'wlan0' ] ) )[ 0 ].address
            return mac.replace( ":", "" )

    def detect_model() -> str:
        if os.name == 'nt':
            return 'MODEL'

        else:
            with open('/proc/device-tree/model') as f:
                model = f.read()
            return model.rstrip('\x00')

    @staticmethod
    def get_timestamp():
        return datetime.now()

    @staticmethod
    def get_formatted_timestamp():
        return Utils.get_timestamp().strftime( Utils.TIMESTAMP_FORMAT )