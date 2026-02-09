"""
python3 -m pip install --break-system-packages \
  "google-cloud-vision==3.4.5" \
  "google-api-core<2.18" \
  "protobuf<4.21" \
  "grpcio<1.60"


sudo apt install -y imagemagick

sudo tee /etc/tmpfiles.d/vision.conf <<'EOF'
d /var/tmp/vision 0750 USERNAME USERNAME -
e /var/tmp/vision - - - 7d
EOF

"""

import io
import os
import re
import math
import subprocess
import json

from PIL import Image, ImageDraw
from enum import Enum, auto

# pip3 install google-cloud-vision
# pip3 install --upgrade google-api-python-client

from google.cloud import vision
from datetime import datetime
from ha.mqtt.mqtt import MQTT
from ha.utils.utils import Utils

if os.name == "nt":
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = os.environ.get(
        "GOOGLE_APPLICATION_CREDENTIALS_PATH",
        os.path.abspath(os.path.join(os.path.expanduser("~"), "data", "key.json")),
    )

else:
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = os.environ.get(
        "GOOGLE_APPLICATION_CREDENTIALS_PATH",
        os.path.abspath(os.path.join(os.path.expanduser("~"), "data", "key.json")),
    )
    os.environ["GRPC_DNS_RESOLVER"] = "native"


def change_color(image_path, x, y, width, height, new_color):
    # Open the image
    img = Image.open(image_path)

    img = img.convert("RGBA")

    # Create a drawing object
    draw = ImageDraw.Draw(img)

    # Define the region to change color
    region = (x, y, x + width, y + height)

    # Fill the region with the new color
    draw.rectangle(region, fill=new_color)
    img = img.convert("RGB")

    # Save or display the modified image
    img.save(image_path, format="JPEG")


def get_color(image_path, x, y):
    # Open the image
    img = Image.open(image_path)

    # Get the color at the specified coordinates (x, y)
    color = img.getpixel((x, y))

    return color


class Fields(Enum):
    TIMESTAMP = "timestamp"
    ACTUAL_VALUE = "actual_value"
    TOTAL = "total"
    DAILY_USAGE = "daily_usage"
    MONTHLY_USAGE = "monthly_usage"
    YEARLY_USAGE = "yearly_usage"


class DT_ITEMS(Enum):
    DAY = auto()
    MONTH = auto()
    YEAR = auto()


class Vision:
    client = vision.ImageAnnotatorClient()

    @classmethod
    def get_text(cls, path: str = "change_me.jpg") -> str:
        file_name = os.path.abspath(path)

        with io.open(file_name, "rb") as image_file:
            content = image_file.read()

        image = vision.Image(content=content)

        response = cls.client.text_detection(image=image)

        if response.error.message:
            raise Exception(
                "{}\nFor more info on error messages, check: "
                "https://cloud.google.com/apis/design/errors".format(
                    response.error.message
                )
            )

        text = response.full_text_annotation.text

        return text

    @classmethod
    def create_picture(cls, image_name: str = ""):
        # negative
        # denoise
        full_image_path = os.path.abspath(os.path.join("/var/tmp/vision", image_name))

        cmd = f"rpicam-still -n --vflip --hflip -o - | convert - -negate {full_image_path}"
        print(cmd)
        subprocess.call(
            cmd,
            shell=True,
        )

        image_path = full_image_path
        change_color(
            image_path,
            x=1090,
            y=1460,
            width=90,
            height=24,
            new_color=get_color(image_path, 1000, 1491),
        )  # Red color in RGBA format

        return image_path

    @classmethod
    def read_value_from_img(cls, image_name):
        path = cls.create_picture(image_name)
        return cls.get_text(path)


NAME = f"{Utils.get_host_name()}_{Utils.get_mac_address()}"


class Gas(Vision):
    mqtt = MQTT(client_name=NAME)

    topic = "rpi/sensors/gas"
    base_config = {
        "name": "Gas Daily",
        "unique_id": "gas_daily",
        "state_class": "total_increasing",
        "device_class": "gas",
        "unit_of_measurement": "m³",
        "state_topic": "rpi/sensors/gas",
        "platform": "mqtt",
        "value_template": "{{ value_json." + f"{Fields.TOTAL.value}" + " }}",
        "device": {
            "name": "Gas - " + Utils.detect_model(),
            "manufacturer": "RPi",
            "model": Utils.detect_model(),
            "identifiers": [
                "gas",
                Utils.get_mac_address(),
                Utils.detect_model(),
                Utils.get_host_name(),
            ],
        },
    }

    total_config = base_config.copy()
    total_config["name"] = "Gas Total"
    total_config["unique_id"] = "gas_total"
    total_config["value_template"] = "{{ value_json." + f"{Fields.TOTAL.value}" + " }}"

    daily_config = base_config.copy()
    daily_config["name"] = "Gas Daily"
    daily_config["unique_id"] = "gas_daily"
    daily_config["state_class"] = "measurement"
    daily_config["value_template"] = (
        "{{ value_json." + f"{Fields.DAILY_USAGE.value}" + " }}"
    )

    monthly_config = base_config.copy()
    monthly_config["name"] = "Gas Monthly"
    monthly_config["unique_id"] = "gas_monthly"
    monthly_config["state_class"] = "measurement"
    monthly_config["value_template"] = (
        "{{ value_json." + f"{Fields.MONTHLY_USAGE.value}" + " }}"
    )

    yearly_config = base_config.copy()
    yearly_config["name"] = "Gas Yearly"
    yearly_config["unique_id"] = "gas_yearly"
    yearly_config["state_class"] = "measurement"
    yearly_config["value_template"] = (
        "{{ value_json." + f"{Fields.YEARLY_USAGE.value}" + " }}"
    )

    @classmethod
    def read_value_from_img(cls, path):
        text = super().read_value_from_img(path)

        text = text.replace(" ", "")
        text = text.replace(",", "")
        text = text.replace("-", "")
        print(text)

        meter = re.findall("0(\d\d\d\d.?\d\d?\d?.?)m?", text)[0]
        meter = "".join(re.findall("\d", meter))
        print("meter: " + meter)
        meter = re.findall("(\d\d\d\d)(\d\d?\d?)", meter)[0]
        return float(int(meter[0]) + (int(meter[1]) / math.pow(10, len(meter[1]))))

    @classmethod
    def read_value_from_gas_meter(cls) -> float:
        now = Utils.get_timestamp()
        image_name = now.strftime("%Y_%m_%d_%H_%M_%S") + ".jpg"

        return cls.read_value_from_img(image_name)

    @classmethod
    def publish_gas_stats(cls, topic: str = "", data: dict = {}):
        now = Utils.get_timestamp()

        last_value = cls.get_last_value()

        actual_value = cls.read_value_from_gas_meter()
        diff_between_measures = actual_value - last_value.get(Fields.TOTAL.value, "0")

        tolerance = cls.get_tolerance(last_value, diff_between_measures)

        print(f"last:{last_value}, actual:{actual_value}, diff:{diff_between_measures}")

        if not -15 <= diff_between_measures < 15:
            print("Out of tolerance")
            return 0
        daily_usage = (
            diff_between_measures
            if cls.start_a_new_cycle(DT_ITEMS.DAY, last_value)
            else diff_between_measures + last_value.get(Fields.DAILY_USAGE.value, 0)
        )
        monthly_usage = (
            diff_between_measures
            if cls.start_a_new_cycle(DT_ITEMS.MONTH, last_value)
            else diff_between_measures + last_value.get(Fields.MONTHLY_USAGE.value, 0)
        )
        yearly_usage = (
            diff_between_measures
            if cls.start_a_new_cycle(DT_ITEMS.YEAR, last_value)
            else diff_between_measures + last_value.get(Fields.YEARLY_USAGE.value, 0)
        )

        data = {
            Fields.TOTAL.value: actual_value,
            Fields.DAILY_USAGE.value: daily_usage,
            Fields.MONTHLY_USAGE.value: monthly_usage,
            Fields.YEARLY_USAGE.value: yearly_usage,
            Fields.TIMESTAMP.value: now.strftime(Utils.TIMESTAMP_FORMAT),
        }

        print(topic, data)
        cls.mqtt.publish(topic=topic or cls.topic, msg=json.dumps(data))

    @staticmethod
    def get_tolerance(last_value: dict = {}, diff_between_measures: float = 0.0):
        last = datetime.strptime(
            last_value.get(Fields.TIMESTAMP.value), Utils.TIMESTAMP_FORMAT
        )
        now = datetime.now()

        diff = float((now - last).total_seconds() / 3600)

        return diff * 1

    @classmethod
    def get_last_value(cls) -> dict:
        return cls.mqtt.get_last_message(cls.topic)

    @classmethod
    def start_a_new_cycle(cls, dt_item: DT_ITEMS = DT_ITEMS.DAY, last_value: dict = {}):
        last = datetime.strptime(
            last_value.get(Fields.TIMESTAMP.value), Utils.TIMESTAMP_FORMAT
        )
        now = datetime.now()

        if cls.on_the_same_dt_item(dt_item, last, now):
            return False

        else:
            return True

    @classmethod
    def on_the_same_dt_item(
        cls, dt_item: DT_ITEMS, past: datetime, now: datetime
    ) -> bool:
        if dt_item == DT_ITEMS.DAY:
            return past.day == now.day

        elif dt_item == DT_ITEMS.MONTH:
            return past.month == now.month

        elif dt_item == DT_ITEMS.YEAR:
            return past.year == now.year

        return False


Gas.mqtt.connect_mqtt()

# Gas.mqtt.publish( "homeassistant/sensor/gas/total_usage/config", json.dumps( Gas.total_config ) )
# Gas.mqtt.publish( "homeassistant/sensor/gas/daily_usage/config", json.dumps( Gas.daily_config ) )
# Gas.mqtt.publish( "homeassistant/sensor/gas/monthly_usage/config", json.dumps( Gas.monthly_config ) )
# Gas.mqtt.publish( "homeassistant/sensor/gas/yearly_usage/config", json.dumps( Gas.yearly_config ) )

Gas.publish_gas_stats()
Gas.mqtt.disconnect()
