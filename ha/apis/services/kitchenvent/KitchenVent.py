import logging
import os
from dataclasses import dataclass
import time

from homeassistant_api import Client

from ha.apis.entity_handlers.HASwitch import HomeAssistantSwitch
from ha.apis.entity_handlers.HATemperature import HomeAssistantTemperature
from ha.apis.utils.my_stats import MeasurementStatistics, TempSampler, TempSeries
from ha.apis.utils.statehandler import StateHandler
from ha.apis.utils.filters import (
    AverageFilter,
    MedianClipFilter,
    MovingAverageLowPassFilter,
    RollingMedianFilter,
    SavitzkyGolayFilter,
    WeightedMovingAverageFilter,
)

logger = logging.getLogger(__name__)

SUBSTATE_LIGHT_BLUE = "\033[94m"
SUBSTATE_YELLOW = "\033[93m"
ANSI_RESET = "\033[0m"

VENT_SWITCH_ID = "switch.shelly1_32c53d"
TEMPERATURE_SENSOR_ID = "sensor.shellyuni_483fda82c1aa_homerseklet"
SAMPLE_PERIOD_SECONDS = 1.0
TEMPERATURE_WINDOW_SECONDS = 240
TEMPERATURE_CHANGE_THRESHOLD_C = 0.4
TEMPERATURE_OFF_THRESHOLD_C = 0.25
EDGE_AVERAGE_SECONDS = 60


class KitchenVent:
    """A konyhai szellőző kapcsolója és a hozzá tartozó hőmérséklet-szenzor."""

    def __init__(self, rest_client: Client) -> None:
        self.switch = HomeAssistantSwitch(rest_client=rest_client, entity_id=VENT_SWITCH_ID)
        self.temperature_sensor = HomeAssistantTemperature(rest_client=rest_client, entity_id=TEMPERATURE_SENSOR_ID)

    def is_on(self) -> bool:
        return self.switch.is_on()

    def turn_on(self) -> None:
        self.switch.turn_on()

    def turn_off(self) -> None:
        self.switch.turn_off()

    def get_temperature(self) -> float:
        return self.temperature_sensor.get_temperature()


def create_client() -> Client:
    return Client(
        os.environ["HA_REST_URL"],
        os.environ["HA_LLA_TOKEN"],
        global_request_kwargs={"timeout": int(os.getenv("HA_REQUEST_TIMEOUT", "10"))},
    )


@dataclass
class KitchenVentContext:
    vent: KitchenVent
    series: TempSeries
    statistics: MeasurementStatistics | None = None
    statistics_for: callable[[int], MeasurementStatistics] = None
    start_time: float = time.monotonic()
    start_temperature: float  = 0.0

class VentOff(StateHandler):
    on: StateHandler
    context: KitchenVentContext

    def decide(self) -> "StateHandler":
        delta = self.context.statistics.total_slope_in_cycle
        if delta is not None and delta >= TEMPERATURE_CHANGE_THRESHOLD_C :
            return self.on
        return self

    def pre(self) -> None:
        self.context.vent.turn_off()
        logger.info("Vent turned off")


class VentOn(StateHandler):
    off: StateHandler
    context: KitchenVentContext

    def min_on_time_elapsed(self) -> bool:
        return time.monotonic() - self.context.start_time >= EDGE_AVERAGE_SECONDS

    def decide(self) -> "StateHandler":
        if not self.min_on_time_elapsed():
            return self
        if self.context.statistics.last_measured_value < self.context.start_temperature + TEMPERATURE_OFF_THRESHOLD_C:
            return self.off
        return self

    def pre(self) -> None:
        self.context.vent.turn_on()
        self.context.start_time = time.monotonic()
        self.context.start_temperature = self.context.statistics.last_measured_value
        logger.info("Vent turned on")


def run_automation(kitchen_vent: KitchenVent) -> None:
    temperature_series = TempSeries(
        max_samples=TEMPERATURE_WINDOW_SECONDS,
        filters=[
            MedianClipFilter(window_size=TEMPERATURE_WINDOW_SECONDS, max_deviation=0.3),
            MovingAverageLowPassFilter(window_size=TEMPERATURE_WINDOW_SECONDS),
            WeightedMovingAverageFilter(window_size=TEMPERATURE_WINDOW_SECONDS),
            SavitzkyGolayFilter(window_size=TEMPERATURE_WINDOW_SECONDS),
            RollingMedianFilter(window_size=TEMPERATURE_WINDOW_SECONDS),
        ],
    )
    sampler = TempSampler(
        read_temperature=kitchen_vent.get_temperature,
        series=temperature_series
    )
    context = KitchenVentContext(
        vent=kitchen_vent,
        series=temperature_series,
        statistics_for=lambda window: temperature_series.statistics(window, AverageFilter()),
    )
    off = VentOff(context=context)
    on = VentOn(context=context)
    off.on = on
    on.off = off
    state: StateHandler = on if kitchen_vent.is_on() else off

    logger.info(
        "Starting kitchen vent automation; collecting a %d-second temperature window",
        TEMPERATURE_WINDOW_SECONDS,
    )
    while True:
        loop_started_at = time.monotonic()
        try:
            sampler.sample_once()
            context.statistics = temperature_series.statistics(window_size_for_target_adjustment=TEMPERATURE_WINDOW_SECONDS, measurement_filters=[AverageFilter()])

            previous_state = state
            match state:
                case VentOff():
                    next_state: StateHandler = off.decide()
                    if next_state is off:
                        off.apply()
                case VentOn():
                    next_state: StateHandler = on.decide()
                    if next_state is on:
                        on.apply()

            if next_state is not previous_state:
                previous_state.post()
                next_state.pre()
                state = next_state
                logger.info(
                    "Kitchen vent state: %s -> %s (%.1f seconds temperature change: %.2f°C)",
                    type(previous_state).__name__,
                    type(state).__name__,
                    context.statistics.time_spent_in_seconds,
                    context.statistics.total_slope_in_cycle,
                )
            logger.info("Statistics: first: %.1f, last: %.1f, start temp: %.1f, total slope: %.2f slope: %.2f", context.statistics.first_measured_value, context.statistics.last_measured_value, context.start_temperature, context.statistics.total_slope_in_cycle, context.statistics.slope_per_second )
        except Exception as err:
            logger.exception("Kitchen vent control cycle failed: %s", err)

        time.sleep(max(0.0, SAMPLE_PERIOD_SECONDS - (time.monotonic() - loop_started_at)))


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    kitchen_vent = KitchenVent(rest_client=create_client())
    run_automation(kitchen_vent=kitchen_vent)
