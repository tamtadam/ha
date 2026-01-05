import json
import time
import os
from ha.mqtt.mqtt import MQTT

from ha.utils.utils import Utils
from ha.utils.my_psutil import Mypsutil, Fields

NAME = f"{Utils.get_host_name()}_{Utils.get_mac_address()}"

class RPi():
    mqtt = MQTT( client_name = f"{NAME}", broker=os.environ.get("MQTT_BROKER", "1.1.1.1"), port=1883, username=os.environ.get("MQTT_USERNAME", "géza"), password=os.environ.get("MQTT_PASSWORD", "1234") )

    topic = f"rpi/{NAME}/hardware"

    base_config = {
        "name": "RPi Core1 Temp",
        "unique_id": f"{Utils.get_host_name()}_core1_temp",
        "state_class": "measurement",
        "state_topic" : f"rpi/{NAME}/hardware",
        "platform": "mqtt",
        "unit_of_measurement": "°C",
        "value_template": "{{ value_json." + f"{Fields.TEMPERATURE.value}.{Fields.CPU.value}.{Fields.CORE_1.value}" + " }}",
        "device" : {
            "name": Utils.detect_model(),
            "manufacturer": "RPi",
            "model": Utils.detect_model(),
            "identifiers" : [ Utils.get_mac_address(), Utils.detect_model() ]
        }
    }

    core1 = base_config.copy()
    core1[ 'name' ] = f"{Utils.get_host_name()} Core1 Temp"
    core1[ 'device_class' ] = "temperature"
    core1[ 'unique_id' ] = f"{Utils.get_host_name()}_core1_temp"
    core1[ 'value_template' ] = "{{ value_json." + f"{Fields.TEMPERATURE.value}.{Fields.CPU.value}.{Fields.CORE_1.value}" + " }}"

    core2 = core1.copy()
    core2[ 'name' ] = f"{Utils.get_host_name()} Core2 Temp"
    core2[ 'unique_id' ] = f"{Utils.get_host_name()}_core2_temp"
    core2[ 'value_template' ] = "{{ value_json." + f"{Fields.TEMPERATURE.value}.{Fields.CPU.value}.{Fields.CORE_2.value}" + " }}"

    core3 = core1.copy()
    core3[ 'name' ] = f"{Utils.get_host_name()} Core3 Temp"
    core3[ 'unique_id' ] = f"{Utils.get_host_name()}_core3_temp"
    core3[ 'value_template' ] = "{{ value_json." + f"{Fields.TEMPERATURE.value}.{Fields.CPU.value}.{Fields.CORE_3.value}" + " }}"

    core4 = core1.copy()
    core4[ 'name' ] = f"{Utils.get_host_name()} Core4 Temp"
    core4[ 'unique_id' ] = f"{Utils.get_host_name()}_core4_temp"
    core4[ 'value_template' ] = "{{ value_json." + f"{Fields.TEMPERATURE.value}.{Fields.CPU.value}.{Fields.CORE_4.value}" + " }}"

    disk_total = base_config.copy()
    disk_total[ 'name' ] = f"{Utils.get_host_name()} Disk Total"
    disk_total[ "unit_of_measurement" ] = "GB"
    disk_total[ 'unique_id' ] = f"{Utils.get_host_name()}_disk_total"
    disk_total[ 'value_template' ] = "{{ value_json." + f"{Fields.DISK.value}.{Fields.TOTAL.value}" + " }}"

    disk_available = disk_total.copy()
    disk_available[ 'name' ] = f"{Utils.get_host_name()} Disk Available"
    disk_available[ 'unique_id' ] = f"{Utils.get_host_name()}_disk_available"
    disk_available[ 'value_template' ] = "{{ value_json." + f"{Fields.DISK.value}.{Fields.AVAILABLE.value}" + " }}"

    disk_used = disk_total.copy()
    disk_used[ 'name' ] = f"{Utils.get_host_name()} Disk Used"
    disk_used[ 'unique_id' ] = f"{Utils.get_host_name()}_disk_used"
    disk_used[ "unit_of_measurement" ] = "%"
    disk_used[ 'value_template' ] = "{{ value_json." + f"{Fields.DISK.value}.{Fields.USED.value}" + " }}"

    memory_total = disk_total.copy()
    memory_total[ 'name' ] = f"{Utils.get_host_name()} Memory Total"
    memory_total[ "unit_of_measurement" ] = "MB",
    memory_total[ 'unique_id' ] = f"{Utils.get_host_name()}_memory_total"
    memory_total[ 'value_template' ] = "{{ value_json." + f"{Fields.MEMORY.value}.{Fields.TOTAL.value}" + " }}"

    memory_avaialble = memory_total.copy()
    memory_avaialble[ 'name' ] = f"{Utils.get_host_name()} Memory Available"
    memory_avaialble[ 'unique_id' ] = f"{Utils.get_host_name()}_memory_available"
    memory_avaialble[ 'value_template' ] = "{{ value_json." + f"{Fields.MEMORY.value}.{Fields.AVAILABLE.value}" + " }}"

    memory_used = memory_total.copy()
    memory_used[ 'name' ] = f"{Utils.get_host_name()} Memory Used"
    memory_used[ 'unique_id' ] = f"{Utils.get_host_name()}_memory_used"
    memory_used[ "unit_of_measurement" ] = "%"
    memory_used[ 'value_template' ] = "{{ value_json." + f"{Fields.MEMORY.value}.{Fields.USED.value}" + " }}"

    load_c_1 = base_config.copy()
    load_c_1[ "unit_of_measurement" ] = "%"
    load_c_1[ 'name' ] = f"{Utils.get_host_name()} Load 1min"
    load_c_1[ 'unique_id' ] = f"{Utils.get_host_name()}_load_1min"
    load_c_1[ 'value_template' ] = "{{ value_json." + f"{Fields.LOAD.value}.{Fields.MIN_1.value}" + " }}"

    load_c_5 = load_c_1.copy()
    load_c_5[ 'name' ] = f"{Utils.get_host_name()} Load 5min"
    load_c_5[ 'unique_id' ] = f"{Utils.get_host_name()}_load_5min"
    load_c_5[ 'value_template' ] = "{{ value_json." + f"{Fields.LOAD.value}.{Fields.MIN_5.value}" + " }}"

    load_c_15 = load_c_1.copy()
    load_c_15[ 'name' ] = f"{Utils.get_host_name()} Load 15min"
    load_c_15[ 'unique_id' ] = f"{Utils.get_host_name()}_load_15min"
    load_c_15[ 'value_template' ] = "{{ value_json." + f"{Fields.LOAD.value}.{Fields.MIN_15.value}" + " }}"

    @classmethod
    def publish_data( cls ):
        data = Mypsutil.get_all_stat()
        print( cls.topic, data )

        cls.mqtt.publish( topic = cls.topic, msg = json.dumps( data ) )

RPi.mqtt.connect_mqtt()


while (True):
    time.sleep(1)
    print( Mypsutil.get_all_stat() )
    print( RPi.base_config )
    print( RPi )


    for i in [
        RPi.core1,
        RPi.core2,
        RPi.core3,
        RPi.core4,
        RPi.disk_available,
        RPi.disk_total,
        RPi.disk_used,
        RPi.memory_avaialble,
        RPi.memory_total,
        RPi.memory_used,
        RPi.load_c_1,
        RPi.load_c_5,
        RPi.load_c_15 ]:
        RPi.mqtt.publish( f"homeassistant/sensor/{NAME}/{i[ 'unique_id' ]}/config", json.dumps( i ) )

    RPi.publish_data()

RPi.mqtt.disconnect()
