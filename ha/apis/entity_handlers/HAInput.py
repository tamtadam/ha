import logging

from homeassistant_api import Client

from ha.apis.entity_handlers.HAEntity import HomeAssistantEntity

logger = logging.getLogger(__name__)


class HomeAssistantInputNumber(HomeAssistantEntity):
    """Home Assistant input_number helper API."""

    def __init__(self, rest_client: Client, entity_id: str) -> None:
        """Inicializálja a numerikus input helper objektumot."""
        super().__init__(rest_client=rest_client, entity_id=entity_id)

    def get_value(self) -> float:
        """Visszaadja az input_number aktuális értékét."""
        logger.debug("get_value called for input_number %s", self.entity_id)
        state = self.get_state()
        if state.state in {"unknown", "unavailable"}:
            raise RuntimeError(f"Input number {self.entity_id} is {state.state}")

        try:
            value = float(state.state)
        except ValueError as error:
            raise ValueError(f"Input number {self.entity_id} returned a non-numeric state: {state.state!r}") from error

        logger.debug("get_value for input_number %s returned %s", self.entity_id, value)
        return value

    def set_value(self, value: float) -> None:
        """Beállítja az input_number értékét."""
        logger.debug("set_value called for input_number %s with value=%s", self.entity_id, value)
        states = self.trigger_service(
            "input_number",
            "set_value",
            entity_id=self.entity_id,
            value=value,
        )
        logger.debug("set_value for input_number %s returned %d state(s)", self.entity_id, len(states))


class HomeAssistantInputBoolean(HomeAssistantEntity):
    """Home Assistant input_boolean helper API."""

    def __init__(self, rest_client: Client, entity_id: str) -> None:
        """Inicializálja a logikai input helper objektumot."""
        super().__init__(rest_client=rest_client, entity_id=entity_id)

    def get_value(self) -> bool:
        """Visszaadja az input_boolean aktuális értékét (True, ha be van kapcsolva)."""
        logger.debug("get_value called for input_boolean %s", self.entity_id)
        state = self.get_state()
        if state.state in {"unknown", "unavailable"}:
            raise RuntimeError(f"Input boolean {self.entity_id} is {state.state}")
        if state.state not in {"on", "off"}:
            raise ValueError(f"Input boolean {self.entity_id} returned an unexpected state: {state.state!r}")

        value = state.state == "on"
        logger.debug("get_value for input_boolean %s returned %s", self.entity_id, value)
        return value

    def set_value(self, value: bool) -> None:
        """Beállítja az input_boolean értékét."""
        logger.debug("set_value called for input_boolean %s with value=%s", self.entity_id, value)
        if value:
            self.turn_on()
        else:
            self.turn_off()

    def turn_on(self) -> None:
        """Bekapcsolja az input_boolean-t."""
        logger.debug("turn_on called for input_boolean %s", self.entity_id)
        states = self.trigger_service("input_boolean", "turn_on", entity_id=self.entity_id)
        logger.debug("turn_on for input_boolean %s returned %d state(s)", self.entity_id, len(states))

    def turn_off(self) -> None:
        """Kikapcsolja az input_boolean-t."""
        logger.debug("turn_off called for input_boolean %s", self.entity_id)
        states = self.trigger_service("input_boolean", "turn_off", entity_id=self.entity_id)
        logger.debug("turn_off for input_boolean %s returned %d state(s)", self.entity_id, len(states))
