import logging

from homeassistant_api import Client

from ha.apis.entity_handlers.HAEntity import HomeAssistantEntity

logger = logging.getLogger(__name__)


class HomeAssistantTemperature(HomeAssistantEntity):
    """Home Assistant hőmérséklet-szenzor API."""

    def __init__(self, rest_client: Client, entity_id: str) -> None:
        """
        Inicializálja a hőmérséklet-szenzor objektumot.

        :param rest_client: A bejelentkezett homeassistant_api.Client objektum a REST API-hoz.
        :param entity_id: A szenzor teljes azonosítója (pl. 'sensor.shellyuni_483fda82c1aa_homerseklet').
        """
        super().__init__(rest_client=rest_client, entity_id=entity_id)

    def get_temperature(self) -> float:
        """Visszaadja az aktuális hőmérsékletet a szenzor mértékegységében (általában °C)."""
        logger.debug("get_temperature called for entity %s", self.entity_id)
        state = self.get_state()
        if state.state in {"unknown", "unavailable"}:
            raise RuntimeError(f"Temperature sensor {self.entity_id} is {state.state}")

        try:
            temperature = float(state.state)
        except ValueError as error:
            raise ValueError(f"Temperature sensor {self.entity_id} returned a non-numeric state: {state.state!r}") from error

        logger.debug("get_temperature for %s returned %s", self.entity_id, temperature)
        return temperature
