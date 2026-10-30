import logging

from homeassistant_api import Client

from ha.apis.entity_handlers.HAEntity import HomeAssistantEntity

logger = logging.getLogger(__name__)


class HomeAssistantIlluminance(HomeAssistantEntity):
    """Home Assistant illuminance sensor API."""

    def __init__(self, rest_client: Client, entity_id: str) -> None:
        """
        Inicializálja a megvilágításérzékelő objektumot.

        :param rest_client: A bejelentkezett homeassistant_api.Client objektum a REST API-hoz.
        :param entity_id: A megvilágítás szenzor teljes azonosítója.
        """
        super().__init__(rest_client=rest_client, entity_id=entity_id)

    def get_illuminance(self) -> float:
        """Visszaadja az aktuális megvilágítást luxban."""
        logger.debug("get_illuminance called for entity %s", self.entity_id)
        state = self.get_state()
        if state.state in {"unknown", "unavailable"}:
            raise RuntimeError(f"Illuminance sensor {self.entity_id} is {state.state}")

        try:
            illuminance = float(state.state)
            logger.debug("get_illuminance for %s returned %s lux", self.entity_id, illuminance)
            return illuminance
        except ValueError as error:
            raise ValueError(f"Illuminance sensor {self.entity_id} returned a non-numeric state: {state.state!r}") from error
