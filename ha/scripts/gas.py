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
import base64
import mimetypes
import subprocess
import argparse
import json
import logging
import tempfile

from PIL import Image, ImageDraw
from enum import Enum, auto

# pip3 install google-cloud-vision
# pip3 install --upgrade google-api-python-client

from google import genai
from google.cloud import vision
from datetime import datetime
from ha.publishers.base_sensor_publisher import BaseSensorPublisher
from ha.utils.utils import Utils, SensorConfig

logger = logging.getLogger(__name__)

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


def change_color(image_path: str, x: int, y: int, width: int, height: int, new_color: tuple, target_path: str | None = None) -> str:
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
    img.save(target_path or image_path, format="JPEG")
    return target_path or image_path


def get_color(image_path: str, x: int, y: int) -> tuple:
    img = Image.open(image_path)
    return img.getpixel((x, y))


def crop_region(
    image_path: str,
    left: int,
    top: int,
    right: int,
    bottom: int,
    output_path: str | None = None,
) -> str:
    img = Image.open(image_path)
    box = (left, top, right, bottom)
    cropped = img.crop(box)
    save_path = output_path or image_path
    cropped.save(save_path)
    return save_path


def mask_and_crop_with_imagedraw(
    image_path: str,
    left: int,
    top: int,
    right: int,
    bottom: int,
    output_path: str | None = None,
) -> str:
    """
    ImageDraw-lal maszkot rajzolunk a kivágandó téglalapra, majd a képet
    maszkoljuk és a téglalapra vágjuk. Ez akkor hasznos, ha először a képen
    vizuálisan ki akarod emelni a középső részt.

    Megjegyzés: tényleges kivágásra az Image.crop a legegyszerűbb.
    """
    img = Image.open(image_path).convert("RGB")
    mask = Image.new("L", img.size, 0)
    draw = ImageDraw.Draw(mask)
    draw.rectangle((left, top, right, bottom), fill=255)

    # A maszkolással a téglalapon belüli részt tartjuk meg, a külsejét feketévé tesszük
    black_bg = Image.new("RGB", img.size, (0, 0, 0))
    masked = Image.composite(img, black_bg, mask)

    cropped = masked.crop((left, top, right, bottom))
    save_path = output_path or image_path
    cropped.save(save_path)
    return save_path, cropped.size


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
    vision_client = vision.ImageAnnotatorClient()

    @staticmethod
    def get_gemini_text(
        image_path: str,
        model: str = "gemini-3.1-flash-lite",
    ) -> str:
        mime_type, _ = mimetypes.guess_type(image_path)
        if mime_type is None or not mime_type.startswith("image/"):
            raise ValueError(f"Cannot determine image MIME type from path: {image_path}")

        with open(image_path, "rb") as image_file:
            image_data = base64.b64encode(image_file.read()).decode("ascii")

        with genai.Client() as client:
            interaction = client.interactions.create(
                model=model,
                input=[
                    {
                        "type": "text",
                        "text": "Read the text in this image. Return only the text you can read.",
                    },
                    {
                        "type": "image",
                        "data": image_data,
                        "mime_type": mime_type,
                    },
                ],
            )

        if interaction.output_text is None:
            raise RuntimeError("Gemini returned no text for the image")
        return interaction.output_text

    @staticmethod
    def create_latest_symlink(image_path: str) -> str:
        image_path = os.path.abspath(image_path)
        if not os.path.isfile(image_path):
            raise FileNotFoundError(image_path)

        latest_path = "/var/tmp/vision/latest.jpg"
        latest_dir = os.path.dirname(latest_path)
        os.makedirs(latest_dir, exist_ok=True)
        if os.path.lexists(latest_path) and not os.path.islink(latest_path):
            raise FileExistsError(f"Refusing to replace non-symlink: {latest_path}")

        temp_fd, temp_path = tempfile.mkstemp(prefix=".latest.jpg.", dir=latest_dir)
        os.close(temp_fd)
        os.unlink(temp_path)
        try:
            os.symlink(image_path, temp_path)
            os.replace(temp_path, latest_path)
        finally:
            if os.path.lexists(temp_path):
                os.unlink(temp_path)

        return latest_path

    @classmethod
    def get_text(cls, path: str = "change_me.jpg") -> str:
        file_name = os.path.abspath(path)

        with io.open(file_name, "rb") as image_file:
            content = image_file.read()

        image = vision.Image(content=content)

        response = cls.vision_client.text_detection(image=image)

        if response.error.message:
            raise Exception(
                "{}\nFor more info on error messages, check: https://cloud.google.com/apis/design/errors".format(response.error.message)
            )

        return response.full_text_annotation.text

    @classmethod
    def create_picture(cls, image_name: str = "") -> str:
        # negative
        # denoise
        full_image_path = os.path.abspath(os.path.join("/var/tmp/vision", image_name))

        cmd = f"rpicam-still -n -o - | convert - -negate {full_image_path}"
        print(cmd)
        subprocess.call(
            cmd,
            shell=True,
        )

        image_path = full_image_path
        image_path = change_color(
            image_path,
            x=1090,
            y=1460,
            width=90,
            height=24,
            new_color=get_color(image_path, 1000, 1491),
        )  # Red color in RGBA format
        with Image.open(image_path) as image:
            width, height = image.size

        image_path = crop_region(
            image_path,
            left=round(width * 0.255),
            top=round(height * 0.425),
            right=round(width * 0.75),
            bottom=round(height * 0.52),
            output_path=image_path,
        )
        with Image.open(image_path) as image:
            image.rotate(0.7, resample=Image.BICUBIC, expand=True).save(image_path)

        cls.create_latest_symlink(image_path)
        return image_path

    @classmethod
    def read_value_from_img(cls, image_name: str = None, image_path: str = None) -> float:
        path = image_path or cls.create_picture(image_name)
        return cls.get_text(path)


NAME = f"{Utils.get_host_name()}_{Utils.get_mac_address()}"


class Gas(BaseSensorPublisher, Vision):
    topic = "rpi/sensors/gas"
    base_config = SensorConfig(
        "Gas Daily",
        [Fields.TOTAL],
        unit="m³",
        device_class="gas",
        state_topic=topic,
        state_class="total_increasing",
        device_name="Gas - " + Utils.detect_model(),
        identifiers=[
            "gas",
            Utils.get_mac_address(),
            Utils.detect_model(),
            Utils.get_host_name(),
        ],
        include_host_name=False,
    )

    total_config = SensorConfig(
        "Gas Total",
        [Fields.TOTAL],
        source=base_config,
        state_class="total_increasing",
        include_host_name=False,
        state_topic=topic,
        unique_id=Utils.get_unique_id([Fields.TOTAL.value]),
        default_entity_id="sensor.gas_total",
    )
    daily_config = SensorConfig(
        "Gas Daily",
        [Fields.DAILY_USAGE],
        source=base_config,
        state_class="measurement",
        include_host_name=False,
        state_topic=topic,
        unique_id=Utils.get_unique_id([Fields.DAILY_USAGE.value]),
        default_entity_id="sensor.gas_daily",
    )
    monthly_config = SensorConfig(
        "Gas Monthly",
        [Fields.MONTHLY_USAGE],
        source=base_config,
        state_class="measurement",
        include_host_name=False,
        state_topic=topic,
        unique_id=Utils.get_unique_id([Fields.MONTHLY_USAGE.value]),
        default_entity_id="sensor.gas_monthly",
    )
    yearly_config = SensorConfig(
        "Gas Yearly",
        [Fields.YEARLY_USAGE],
        source=base_config,
        state_class="measurement",
        include_host_name=False,
        state_topic=topic,
        unique_id=Utils.get_unique_id([Fields.YEARLY_USAGE.value]),
        default_entity_id="sensor.gas_yearly",
    )

    sensor_configs = [total_config, daily_config, monthly_config, yearly_config]

    def __init__(self) -> None:
        super().__init__(
            client_name=NAME,
            topic=type(self).topic,
            sensors=type(self).sensor_configs,
        )

    def get_config_topic(self, sensor: SensorConfig) -> str:
        return f"homeassistant/sensor/gas/{sensor.unique_id}/config"

    def publish_data(self, topic: str, data: dict) -> None:
        super().publish_data(topic, data)

    @classmethod
    def read_value_from_img(cls, image_name: str = None, image_path: str = None) -> float:
        text = super().read_value_from_img(image_name=image_name, image_path=image_path)
        print("OCR raw text:", text)
        text = text.replace(" ", "")
        text = text.replace(",", "")
        text = text.replace("-", "")
        logger.info("OCR text: %s", text)

        meter = re.findall(r"0(\d\d\d\d.?\d\d?\d?.?)m?", text)[0]
        meter = "".join(re.findall(r"\d", meter))
        logger.info("Parsed meter: %s", meter)
        meter = re.findall(r"(\d\d\d\d)(\d\d?\d?)", meter)[0]
        return float(int(meter[0]) + (int(meter[1]) / math.pow(10, len(meter[1]))))

    @classmethod
    def read_value_from_gas_meter(cls) -> float:
        now = Utils.get_timestamp()
        image_name = now.strftime("%Y_%m_%d_%H_%M_%S") + ".jpg"

        return cls.read_value_from_img(image_name=image_name)

    def publish_gas_stats(self, topic: str = "", dry_run: bool = False) -> int | None:
        now = Utils.get_timestamp()

        last_value: dict = {}
        try:
            last_value = self.get_last_value()
        except Exception as e:
            logger.warning("Failed to get last value: %s", e)
            last_value = {
                Fields.TOTAL.value: 4505.3,
                Fields.DAILY_USAGE.value: 0.1,
                Fields.MONTHLY_USAGE.value: 0.11,
                Fields.YEARLY_USAGE.value: 226,
                Fields.TIMESTAMP.value: "2026-10-03 18:42",
            }
        actual_value = self.read_value_from_gas_meter()
        diff_between_measures = actual_value - last_value.get(Fields.TOTAL.value, "0")

        logger.debug("last:%s, actual:%s, diff:%s", last_value, actual_value, diff_between_measures)

        if not -15 <= diff_between_measures < 15:
            logger.warning("Gas meter difference is out of tolerance")
            return 0

        daily_usage = (
            diff_between_measures
            if self.start_a_new_cycle(DT_ITEMS.DAY, last_value)
            else diff_between_measures + last_value.get(Fields.DAILY_USAGE.value, 0)
        )
        monthly_usage = (
            diff_between_measures
            if self.start_a_new_cycle(DT_ITEMS.MONTH, last_value)
            else diff_between_measures + last_value.get(Fields.MONTHLY_USAGE.value, 0)
        )
        yearly_usage = (
            diff_between_measures
            if self.start_a_new_cycle(DT_ITEMS.YEAR, last_value)
            else diff_between_measures + last_value.get(Fields.YEARLY_USAGE.value, 0)
        )

        data = {
            Fields.TOTAL.value: actual_value,
            Fields.DAILY_USAGE.value: daily_usage,
            Fields.MONTHLY_USAGE.value: monthly_usage,
            Fields.YEARLY_USAGE.value: yearly_usage,
            Fields.TIMESTAMP.value: now.strftime(Utils.TIMESTAMP_FORMAT),
        }

        if dry_run:
            print(json.dumps(data, indent=2))
        else:
            self.publish_data(topic or self.topic, data)
        return None

    @staticmethod
    def get_tolerance(last_value: dict = {}, _diff_between_measures: float = 0.0) -> float:
        last = datetime.strptime(last_value.get(Fields.TIMESTAMP.value), Utils.TIMESTAMP_FORMAT)
        now = datetime.now()

        diff = float((now - last).total_seconds() / 3600)

        return diff * 1

    def get_last_value(self) -> dict:
        return self.get_last_message(self.topic)

    @classmethod
    def start_a_new_cycle(cls, dt_item: DT_ITEMS = DT_ITEMS.DAY, last_value: dict = {}) -> bool:
        last = datetime.strptime(last_value.get(Fields.TIMESTAMP.value), Utils.TIMESTAMP_FORMAT)
        now = datetime.now()

        if cls.on_the_same_dt_item(dt_item, last, now):
            return False

        return True

    @classmethod
    def on_the_same_dt_item(cls, dt_item: DT_ITEMS, past: datetime, now: datetime) -> bool:
        if dt_item == DT_ITEMS.DAY:
            return past.day == now.day

        if dt_item == DT_ITEMS.MONTH:
            return past.month == now.month

        if dt_item == DT_ITEMS.YEAR:
            return past.year == now.year

        return False


if __name__ == "__main__":
    iamge_path = "/Users/trenyikadam/Downloads/latest (1).jpg"
    test = Vision.get_gemini_text(iamge_path)
    parser = argparse.ArgumentParser(description="Send gas meter data and sensor config to MQTT for Home Assistant.")
    parser.add_argument(
        "--send_config",
        action="store_true",
        default=False,
        help="Publish Home Assistant entity config payloads for gas sensors.",
    )
    parser.add_argument(
        "--send_data",
        action="store_true",
        default=False,
        help="Read the current gas meter value and publish updated statistics.",
    )
    parser.add_argument(
        "--dry_run",
        action="store_true",
        help="Print gas statistics to stdout instead of publishing them; use with --send_data",
    )
    args = parser.parse_args()

    publisher = Gas()
    should_connect = args.send_config or (args.send_data and not args.dry_run)
    if should_connect:
        publisher.connect_mqtt()

    if args.send_config:
        publisher.publish_config()

    if args.send_data:
        publisher.publish_gas_stats(dry_run=args.dry_run)

    if should_connect:
        publisher.disconnect()
