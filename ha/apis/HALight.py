import logging

from homeassistant_api import Client

from ha.apis.HAEntity import HomeAssistantEntity

logger = logging.getLogger(__name__)


class HomeAssistantLight(HomeAssistantEntity):
    def __init__(self, rest_client: Client, entity_id: str) -> None:
        """
        Inicializálja a lámpa objektumot.

        :param rest_client: A bejelentkezett homeassistant_api.Client objektum a REST API-hoz
        :param entity_id: A lámpa teljes azonosítója (pl. 'light.nappali_lampa')
        """
        super().__init__(rest_client=rest_client, entity_id=entity_id)

    # --- GETTEREK (Állapot lekérdezések) ---

    def get_brightness(self) -> float:
        """Visszaadja az aktuális fényerőt százalékban (0-100)."""
        logger.debug("get_brightness called for entity %s", self.entity_id)
        state = self.get_state()
        if state.state == "off":
            logger.debug("get_brightness for %s returned 0 because state is off", self.entity_id)
            return 0.0
        brightness_255 = state.attributes.get("brightness", 0)
        brightness_percent = brightness_255 * 100.0 / 255.0
        logger.debug("get_brightness for %s returned %s%%", self.entity_id, brightness_percent)
        return round(brightness_percent)

    def get_kelvin(self) -> int:
        """Visszaadja az aktuális szinhőmérsékletet Kelvinben. Ha nem támogatott vagy nincs megadva, 0-t ad vissza."""
        logger.debug("get_kelvin called for entity %s", self.entity_id)
        state = self.get_state()
        kelvin = int(state.attributes.get("color_temp_kelvin", 0))
        logger.debug("get_kelvin for %s returned %s", self.entity_id, kelvin)
        return kelvin

    # --- SETTEREK (Tulajdonságok módosítása) ---

    def set_brightness(self, brightness: int, transition: float = 1.0) -> int:
        """
        Beállítja a fényerőt százalékban (0-100 között).
        Ha a fényerő > 0, automatikusan felkapcsolja a lámpát.
        """
        brightness_percent = max(0, min(brightness, 100))
        logger.debug(
            "set_brightness called for entity %s with brightness=%s%% transition=%s",
            self.entity_id,
            brightness_percent,
            transition,
        )

        if brightness_percent == 0:
            logger.debug("set_brightness for %s requested 0, turning off", self.entity_id)
            self.turn_off()
            return 0

        brightness_255 = round(brightness_percent * 255 / 100 + 0.5)
        states = self.trigger_service(
            "light",
            "turn_on",
            entity_id=self.entity_id,
            brightness=brightness_255,
            transition=transition,
        )
        logger.debug("set_brightness for %s completed, returned %d state(s)", self.entity_id, len(states))
        return brightness_percent

    def set_kelvin(self, kelvin: int, transition: float = 1.0) -> None:
        """Beállítja a lámpa színhőmérsékletét Kelvinben (pl. 2700 - 6500)."""
        logger.debug("set_kelvin called for entity %s with kelvin=%s transition=%s", self.entity_id, kelvin, transition)
        states = self.trigger_service(
            "light",
            "turn_on",
            entity_id=self.entity_id,
            kelvin=kelvin,
            transition=transition,
        )
        logger.debug("set_kelvin for %s completed, returned %d state(s)", self.entity_id, len(states))

    # --- VEZÉRLŐ FUNKCIÓK ---

    def turn_on(self, transition: float = 1.0) -> None:
        """Felkapcsolja a lámpát az utolsó ismert állapotára."""
        logger.debug("turn_on called for entity %s transition=%s", self.entity_id, transition)
        states = self.trigger_service("light", "turn_on", entity_id=self.entity_id, transition=transition)
        logger.debug("turn_on for %s completed, returned %d state(s)", self.entity_id, len(states))

    def turn_off(self, transition: float = 1.0) -> None:
        """Lekapcsolja a lámpát."""
        logger.debug("turn_off called for entity %s transition=%s", self.entity_id, transition)
        states = self.trigger_service("light", "turn_off", entity_id=self.entity_id, transition=transition)
        logger.debug("turn_off for %s completed, returned %d state(s)", self.entity_id, len(states))
