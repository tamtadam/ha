import json
import os
import sys
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import websocket

ENTITY_ID_PREFIX_RENAMES = {
    "rpicamera_rpicamera_": "rpicamera_",
    "raspberry_pi_zero_w_rev_1_1_rpicamera_rpicamera_systemctl_": "rpicamera_systemctl_",
    "raspberry_pi_zero_w_rev_1_1_gas_": "",
    "raspberry_pi_zero_w_rev_1_1_rpicamera_": "rpicamera_",
    "raspberry_pi_zero_w_rev_1_1_rpizerogas_rpizerogas_": "rpizerogas_",
    "raspberry_pi_3_model_b_rev_1_2_pihole_pihole_systemctl_": "pihole_systemctl_",
    "raspberry_pi_4_model_b_pihole_": "rpihole_",
    "pihole_pihole_": "pihole_",
    "raspberry_pi_zero_w_rev_1_1_rpizerogas_" : "rpizerogas_",
    "rpihole_": "pihole_"
}


def get_websocket_url() -> str:
    configured_url = os.environ.get("HA_WEBSOCKET_URL")
    if not configured_url:
        raise RuntimeError("The HA_WEBSOCKET_URL environment variable is required")

    parsed_url = urlsplit(configured_url)
    scheme = {"http": "ws", "https": "wss", "ws": "ws", "wss": "wss"}.get(parsed_url.scheme)
    if scheme is None:
        raise ValueError(f"Unsupported HA_WEBSOCKET_URL scheme: {parsed_url.scheme!r}")

    path = parsed_url.path.rstrip("/")
    if not path.endswith("/websocket"):
        path = f"{path.removesuffix('/api')}/api/websocket"
    return urlunsplit((scheme, parsed_url.netloc, path, parsed_url.query, parsed_url.fragment))


def get_renamed_entity_id(entity_id: str) -> str | None:
    domain, separator, object_id = entity_id.partition(".")
    domain_prefix = f"{domain}." if separator else ""
    if not separator:
        object_id = entity_id

    for old_prefix, new_prefix in ENTITY_ID_PREFIX_RENAMES.items():
        if object_id.startswith(old_prefix):
            return f"{domain_prefix}{new_prefix}{object_id[len(old_prefix):]}"
    return None


class HomeAssistantWebSocket:
    def __init__(self, url: str, token: str) -> None:
        self.connection = websocket.create_connection(url, timeout=10)
        message = self.receive()
        if message.get("type") != "auth_required":
            raise RuntimeError(f"Unexpected Home Assistant WebSocket response: {message}")

        self.connection.send(json.dumps({"type": "auth", "access_token": token}))
        message = self.receive()
        if message.get("type") != "auth_ok":
            raise RuntimeError(f"Home Assistant authentication failed: {message}")
        self.request_id = 0

    def receive(self) -> dict[str, Any]:
        message = json.loads(self.connection.recv())
        if not isinstance(message, dict):
            raise RuntimeError(f"Unexpected Home Assistant WebSocket response: {message}")
        return message

    def call(self, command: str, **params: Any) -> Any:
        self.request_id += 1
        request_id = self.request_id
        self.connection.send(json.dumps({"id": request_id, "type": command, **params}))

        while True:
            message = self.receive()
            if message.get("id") != request_id:
                continue
            if not message.get("success"):
                raise RuntimeError(f"Home Assistant rejected {command}: {message}")
            return message.get("result")

    def close(self) -> None:
        self.connection.close()


def main() -> int:
    token = os.environ.get("HA_LLA_TOKEN")
    if not token:
        print("The HA_LLA_TOKEN environment variable is required", file=sys.stderr)
        return 2

    websocket_client = HomeAssistantWebSocket(url=get_websocket_url(), token=token)
    try:
        entities = websocket_client.call("config/entity_registry/list")
        if not isinstance(entities, list):
            raise RuntimeError("Home Assistant returned an invalid entity registry")

        changes = []
        for entity in entities:
            entity_id = entity.get("entity_id")
            if not isinstance(entity_id, str):
                continue
            rename = get_renamed_entity_id(entity_id)
            if rename is None:
                continue
            changes.append((entity_id, rename))

        if not changes:
            print("No matching entity IDs found.")
            return 0

        old_ids = {old for old, _ in changes}
        occupied_ids = {entity["entity_id"] for entity in entities if isinstance(entity, dict)} - old_ids
        collisions = [new for _, new in changes if new in occupied_ids]
        if collisions:
            raise RuntimeError(f"Target entity IDs already exist: {collisions}")

        for old, new in changes:
            print(f"{old} -> {new}")

        if input("Rename these entities? Type 'yes' to continue: ").strip().lower() != "yes":
            print("No changes made.")
            return 0

        for old, new in changes:
            websocket_client.call(
                "config/entity_registry/update",
                entity_id=old,
                new_entity_id=new,
            )
        print(f"Renamed {len(changes)} entities.")
        return 0
    finally:
        websocket_client.close()


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, RuntimeError, ValueError, websocket.WebSocketException) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
