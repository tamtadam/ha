from typing import Any

from paho.mqtt import client as mqtt_client
import paho.mqtt.subscribe as subscribe
import json
import os


class MQTT:
    def __init__(
        self,
        broker: str = os.environ.get("MQTT_BROKER", "1.1.1.1"),
        port: int = 1883,
        client_name: str = "python-mqtt",
        username: str = os.environ.get("MQTT_USERNAME", "geza"),
        password: str = os.environ.get("MQTT_PASSWORD", "1234"),
        topic: str = None,
    ) -> None:
        self.broker = broker
        self.port = port
        self.client_name = client_name
        self.password = password
        self.client_id = None
        self.username = username
        self.topic = topic

    @property
    def topic(self) -> str | None:
        return self._topic

    @topic.setter
    def topic(self, topic: str) -> None:
        self._topic = topic

    @property
    def client(self) -> mqtt_client.Client:
        return self._client

    @client.setter
    def client(self, client: mqtt_client.Client) -> None:
        self._client = client

    @property
    def username(self) -> str:
        return self._username

    @username.setter
    def username(self, username: str) -> None:
        self._username = username

    @property
    def broker(self) -> str:
        return self._broker

    @broker.setter
    def broker(self, broker: str) -> None:
        self._broker = broker

    @property
    def port(self) -> int:
        return self._port

    @port.setter
    def port(self, port: int) -> None:
        self._port = port

    @property
    def client_name(self) -> str:
        return self._client_name

    @client_name.setter
    def client_name(self, client_name: str) -> None:
        self._client_name = client_name

    @property
    def password(self) -> str:
        return self._password

    @password.setter
    def password(self, password: str) -> None:
        self._password = password

    @property
    def client_id(self) -> str | None:
        return self._client_id

    @client_id.setter
    def client_id(self, _client_name: str | None) -> None:
        self._client_id = f"{self.client_name}"

    def disconnect(self) -> None:
        self.client.disconnect()

    def connect_mqtt(self) -> mqtt_client.Client:
        def on_connect(_client: mqtt_client.Client, _userdata: Any, _flags: dict, rc: int) -> None:
            if rc == 0:
                print("Connected to MQTT Broker!")
            else:
                print("Failed to connect, return code %d\n", rc)

        self.client = mqtt_client.Client(
            callback_api_version=mqtt_client.CallbackAPIVersion.VERSION2
        )
        self.client.username_pw_set(self.username, self.password)
        self.client.on_connect = on_connect
        self.client.connect(self.broker, self.port)

        return self.client

    def publish(self, topic: str, msg: str, retain: bool = True) -> None:
        msg_count = 0
        result = self.client.publish(topic, msg, retain=retain)

        # result: [0, 1]
        status = result[0]

        if status == 0:
            print(f"Send `{msg}` to topic `{topic}`")
        else:
            print(f"Failed to send message to topic {topic}")

        msg_count += 1

    def subscribe(self, topic: str = "") -> None:
        def on_message(_client: mqtt_client.Client, _userdata: Any, msg: mqtt_client.MQTTMessage) -> None:
            print(f"Received `{msg.payload.decode()}` from `{msg.topic}` topic")

        self.client.subscribe(topic or self.topic)
        self.client.on_message = on_message

    def get_last_message(self, topic: str = "") -> dict:
        data = subscribe.simple(
            topics=topic or self.topic,
            hostname=self.broker,
            port=self.port,
            client_id=self.client_id + "_",
            auth={"username": self.username, "password": self.password},
            clean_session=False,
        )
        return data and json.loads(data.payload.decode())
