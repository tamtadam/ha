import logging

from homeassistant_api import Client

logger = logging.getLogger(__name__)


class HomeAssistantEntity:
    """Közös Home Assistant entitás alapfunkciók."""

    def __init__(self, rest_client: Client, entity_id: str) -> None:
        """
        Inicializálja a Home Assistant entitást.

        :param rest_client: A bejelentkezett homeassistant_api.Client objektum a REST API-hoz.
        :param entity_id: A Home Assistant entitás teljes azonosítója.
        """
        self.rest_client = rest_client
        self.entity_id = entity_id
        logger.debug("Initializing HomeAssistantEntity for %s", self.entity_id)

    def get_state(self):
        """Friss állapot lekérdezése a Home Assistant API-ból."""
        logger.debug("get_state called for entity %s", self.entity_id)
        state = self.rest_client.get_state(entity_id=self.entity_id)
        logger.debug("get_state for %s returned state=%s", self.entity_id, getattr(state, "state", None))
        return state

    def trigger_service(self, domain: str, service: str, **kwargs):
        """Elküldi a Home Assistant szolgáltatási hívást."""
        logger.debug("Triggering service %s.%s for entity %s with kwargs=%s", domain, service, self.entity_id, kwargs)
        states = self.rest_client.trigger_service(domain, service, **kwargs)
        logger.debug("Service %s.%s for entity %s returned %d state(s)", domain, service, self.entity_id, len(states))
        return states
