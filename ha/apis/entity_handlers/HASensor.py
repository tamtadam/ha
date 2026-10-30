import logging

from homeassistant_api import Client, State
from homeassistant_api.errors import EndpointNotFoundError

from ha.apis.entity_handlers.HAEntity import HomeAssistantEntity

logger = logging.getLogger(__name__)


class HomeAssistantSensor(HomeAssistantEntity):
    """Home Assistant sensor API."""

    def __init__(self, rest_client: Client, entity_id: str) -> None:
        """
        Inicializálja a szenzor objektumot.

        :param rest_client: A bejelentkezett homeassistant_api.Client objektum a REST API-hoz.
        :param entity_id: A szenzor teljes azonosítója (pl. 'sensor.konyha_homerseklet').
        """
        super().__init__(rest_client=rest_client, entity_id=entity_id)

    def get_text(self) -> str:
        """Visszaadja a szenzor aktuális állapotát szövegként."""
        logger.debug("get_text called for sensor %s", self.entity_id)
        state = self.get_state()
        if state.state in {"unknown", "unavailable"}:
            raise RuntimeError(f"Sensor {self.entity_id} is {state.state}")

        logger.debug("get_text for sensor %s returned %s", self.entity_id, state.state)
        return state.state

    def get_value(self) -> float:
        """Visszaadja a szenzor aktuális állapotát számként."""
        logger.debug("get_value called for sensor %s", self.entity_id)
        text = self.get_text()
        try:
            value = float(text)
        except ValueError as error:
            raise ValueError(f"Sensor {self.entity_id} returned a non-numeric state: {text!r}") from error

        logger.debug("get_value for sensor %s returned %s", self.entity_id, value)
        return value

    def set_text(self, text: str, attributes: dict | None = None) -> None:
        """
        Írja a szenzor állapotát a REST API-n keresztül.

        Csak a Home Assistant állapotát módosítja, nem tartós: újraindításkor elvész, az integráció pedig felülírja.
        Ha az attributes nincs megadva, a meglévő attribútumok megmaradnak.
        """
        logger.debug("set_text called for sensor %s with text=%s", self.entity_id, text)
        if attributes is None:
            try:
                attributes = self.get_state().attributes
            except EndpointNotFoundError:
                attributes = {}

        self.rest_client.set_state(State(entity_id=self.entity_id, state=text, attributes=attributes))
        logger.debug("set_text for sensor %s completed", self.entity_id)

    def set_value(self, value: float, attributes: dict | None = None) -> None:
        """Írja a szenzor állapotát számként, lásd: set_text."""
        logger.debug("set_value called for sensor %s with value=%s", self.entity_id, value)
        self.set_text(str(value), attributes)
