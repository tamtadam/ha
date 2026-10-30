import logging
import os
import time

from homeassistant_api import Client

from ha.apis.entity_handlers.HAInput import HomeAssistantInputBoolean, HomeAssistantInputNumber
from ha.apis.entity_handlers.HALight import HomeAssistantLight
from ha.apis.entity_handlers.HALuminance import HomeAssistantIlluminance
from ha.apis.utils.filters import (
    MedianClipFilter,
    MovingAverageLowPassFilter,
    WeightedMovingAverageFilter,
    PolyFit,
)
from ha.apis.utils.my_stats import (
    LuxSampler,
    LuxSeries,
)
from ha.apis.services.kitchenlight.light_states import (
    AdjustingForLightChange,
    AdjustingForTargetChange,
    Collecting,
    Disabled,
    LightContext,
    StateHandler,
    Tracking,
    LightControlSettings
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)

LIGHT_ID = "light.konyha_lampak"
LUX_SENSOR_ID = "sensor.0x54ef4410000c20db_illuminance"
LIGHT_TARGET_LUX_ID = "input_number.light_target_lux"

HA_LLA_TOKEN = os.environ["HA_LLA_TOKEN"]
REST_URL = os.environ["HA_REST_URL"]
HA_REQUEST_TIMEOUT = int(os.getenv("HA_REQUEST_TIMEOUT", "10"))

SAMPLE_PERIOD_SECONDS = 1
LIGHT_TRANSITION_TIME = 1.0
NORMAL_FILTER_WINDOW_SIZE = 1000

client = Client(REST_URL, HA_LLA_TOKEN, global_request_kwargs={"timeout": HA_REQUEST_TIMEOUT})
light = HomeAssistantLight(rest_client=client, entity_id=LIGHT_ID)
lux_sensor = HomeAssistantIlluminance(rest_client=client, entity_id=LUX_SENSOR_ID)
corrected_lux_entity = HomeAssistantInputNumber(rest_client=client, entity_id="input_number.light_corrected_illuminance")
light_target_lux = HomeAssistantInputNumber(rest_client=client, entity_id=LIGHT_TARGET_LUX_ID)
light_set_brightness = HomeAssistantInputNumber(rest_client=client, entity_id="input_number.light_set_brightness")
light_enabled = HomeAssistantInputBoolean(rest_client=client, entity_id="input_boolean.light_enabled_automatic")


def set_brightness(value: int) -> None:
    applied = light.set_brightness(value, transition=LIGHT_TRANSITION_TIME)
    light_set_brightness.set_value(applied)


def main() -> None:
    series = LuxSeries(
        max_samples=NORMAL_FILTER_WINDOW_SIZE,
        filters=[
#            MedianClipFilter(window_size=400, max_deviation=2.0),
#            MovingAverageLowPassFilter(window_size=300),
#            WeightedMovingAverageFilter(window_size=300),
            PolyFit(window_size=300),
        ],
    )
    sampler = LuxSampler(lux_sensor.get_illuminance, series)

    context = LightContext(
        settings=LightControlSettings(
            deadzone_lux=10,
            proportional_gain=0.5,
            minimum_brightness_step=1.0,
            maximum_brightness_step=1.0,
            minimum_samples=30,
        ),
        is_enabled=light_enabled.get_value,
        get_brightness=light.get_brightness,
        set_brightness=set_brightness,
        turn_off=light.turn_off,
        statistics_for=lambda window: series.statistics(window_size_for_target_adjustment=window, measurement_filters=[PolyFit(window_size=window)]),
        rebase=series.rebase,
        clock=time.monotonic,
    )
    disabled = Disabled(context=context)
    collecting = Collecting(context=context)
    tracking = Tracking(context=context)
    adjusting_for_light_change = AdjustingForLightChange(context=context)
    adjusting_for_target_change = AdjustingForTargetChange(context=context)
    disabled.connect(collecting=collecting)
    collecting.connect(disabled=disabled, tracking=tracking)
    tracking.connect(
        disabled=disabled,
        adjusting_for_light_change=adjusting_for_light_change,
        adjusting_for_target_change=adjusting_for_target_change,
    )
    adjusting_for_light_change.connect(
        disabled=disabled,
        tracking=tracking,
        adjusting_for_target_change=adjusting_for_target_change,
    )
    adjusting_for_target_change.connect(disabled=disabled, tracking=tracking)
    state: StateHandler = disabled

    logger.info("Starting light control (LIGHT2) for %s based on %s", LIGHT_ID, LUX_SENSOR_ID)

    while True:
        loop_started_at = time.monotonic()
        try:
            sampler.sample_once()
            context.statistics = series.statistics()
            if context.statistics is not None:
                corrected_lux_entity.set_value(int(context.statistics.median))

            context.update_target(target_lux=light_target_lux.get_value())

            previous_state = state
            match state:
                case Disabled():
                    next_state = disabled.decide()
                    if next_state is disabled:
                        disabled.apply()
                case Collecting():
                    next_state = collecting.decide()
                    collecting.apply()
                case Tracking():
                    next_state = tracking.decide()
                    if next_state is tracking:
                        tracking.apply()
                case AdjustingForLightChange():
                    next_state = adjusting_for_light_change.decide()
                    if next_state is adjusting_for_light_change:
                        adjusting_for_light_change.apply()
                case AdjustingForTargetChange():
                    next_state = adjusting_for_target_change.decide()
                    if next_state is adjusting_for_target_change:
                        adjusting_for_target_change.apply()

            if next_state is not previous_state:
                previous_state.post()
                next_state.pre()
                state = next_state
                logger.info("Light control state: %s -> %s", previous_state.name, state.name)
        except Exception as err:
            logger.exception("Light control cycle failed: %s", err)

        time.sleep(max(0.0, SAMPLE_PERIOD_SECONDS - (time.monotonic() - loop_started_at)))


if __name__ == "__main__":
    main()
