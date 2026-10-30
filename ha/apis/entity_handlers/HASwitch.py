import logging

from homeassistant_api import Client

from ha.apis.entity_handlers.HAEntity import HomeAssistantEntity

logger = logging.getLogger(__name__)


class HomeAssistantSwitch(HomeAssistantEntity):
    """Home Assistant kapcsoló (switch) API."""

    def __init__(self, rest_client: Client, entity_id: str) -> None:
        """
        Inicializálja a kapcsoló objektumot.

        :param rest_client: A bejelentkezett homeassistant_api.Client objektum a REST API-hoz.
        :param entity_id: A kapcsoló teljes azonosítója (pl. 'switch.shelly1_32c53d').
        """
        super().__init__(rest_client=rest_client, entity_id=entity_id)

    def is_on(self) -> bool:
        """Visszaadja, hogy a kapcsoló be van-e kapcsolva."""
        logger.debug("is_on called for entity %s", self.entity_id)
        state = self.get_state()
        if state.state in {"unknown", "unavailable"}:
            raise RuntimeError(f"Switch {self.entity_id} is {state.state}")

        is_on = state.state == "on"
        logger.debug("is_on for %s returned %s", self.entity_id, is_on)
        return is_on

    def turn_on(self) -> None:
        """Bekapcsolja a kapcsolót."""
        logger.debug("turn_on called for entity %s", self.entity_id)
        self.trigger_service(domain="switch", service="turn_on", entity_id=self.entity_id)

    def turn_off(self) -> None:
        """Kikapcsolja a kapcsolót."""
        logger.debug("turn_off called for entity %s", self.entity_id)
        self.trigger_service(domain="switch", service="turn_off", entity_id=self.entity_id)
