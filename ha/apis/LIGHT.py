import logging
import os
import time
from homeassistant_api import Client
from ha.apis.HAInput import HomeAssistantInputBoolean
from ha.apis.HAInput import HomeAssistantInputNumber
from ha.apis.HALight import HomeAssistantLight
from ha.apis.HALuminance import HomeAssistantIlluminance
from ha.apis.light_control import LightControlMachine, LightControlSettings, LightControlState
from ha.apis.light_measurements import (
    LuxSampler,
    LuxSeries,
    MeasurementStatistics,
    MedianClipFilter,
    MovingAverageLowPassFilter,
    ExponentialMovingAverageFilter,
    WeightedMovingAverageFilter,
    AverageFilter
)
logging.getLogger("transitions").setLevel(logging.WARNING)

# --- LOGOLÁS BEÁLLÍTÁSA ---
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)

# --- ENTITÁS AZONOSÍTÓK ---
LIGHT_ID = "light.konyha_lampak"
LUX_SENSOR_ID = "sensor.0x54ef4410000c20db_illuminance"
LIGHT_TARGET_LUX_ID = "input_number.light_target_lux"

# --- KÖRNYEZETI VÁLTOZÓK ---
HA_LLA_TOKEN = os.environ["HA_LLA_TOKEN"]
REST_URL = os.environ["HA_REST_URL"]
HA_REQUEST_TIMEOUT = int(os.getenv("HA_REQUEST_TIMEOUT", "10"))

SAMPLE_PERIOD_SECONDS = 1
LUX_SAMPLE_PERIOD_SECONDS = 1.0
LIGHT_TRANSITION_TIME = 1.0
NORMAL_FILTER_WINDOW_SIZE = 1000
DEADZONE_LUX = 10
BRIGHTNESS_PERCENT_PER_LUX = 0.5
MINIMUM_BRIGHTNESS_STEP = 1.0
MAXIMUM_BRIGHTNESS_STEP = 1.0
STATE_BOLD_GREEN = "\033[1;32m"
SUBSTATE_LIGHT_BLUE = "\033[94m"
ANSI_RESET = "\033[0m"

# --- KLIENS ÉS OBJEKTUMOK INICIALIZÁLÁSA ---
client = Client(REST_URL, HA_LLA_TOKEN, global_request_kwargs={"timeout": HA_REQUEST_TIMEOUT})

light = HomeAssistantLight(rest_client=client, entity_id=LIGHT_ID)
lux_sensor = HomeAssistantIlluminance(rest_client=client, entity_id=LUX_SENSOR_ID)
lux_corrected_illuminance_sensor = HomeAssistantInputNumber(rest_client=client, entity_id="input_number.light_corrected_illuminance")
light_target_lux = HomeAssistantInputNumber(rest_client=client, entity_id=LIGHT_TARGET_LUX_ID)
light_set_brightness = HomeAssistantInputNumber(rest_client=client, entity_id="input_number.light_set_brightness")
light_enabled = HomeAssistantInputBoolean(rest_client=client, entity_id="input_boolean.light_enabled_automatic")


def apply_proportional_brightness_adjustment(target_lux: float, measured_lux: float, stats: MeasurementStatistics) -> float:
    diff_of_lux = target_lux - measured_lux
    brightness_step = max(
        -MAXIMUM_BRIGHTNESS_STEP,
        min(diff_of_lux * BRIGHTNESS_PERCENT_PER_LUX, MAXIMUM_BRIGHTNESS_STEP),
    )
    if abs(brightness_step) < MINIMUM_BRIGHTNESS_STEP:
        brightness_step = MINIMUM_BRIGHTNESS_STEP if diff_of_lux > 0 else -MINIMUM_BRIGHTNESS_STEP
    current_brightness = light.get_brightness()
    requested_brightness = round(max(0.0, min(100.0, current_brightness + brightness_step)))
    logger.info(
        "%s\tFine-tuning: target=%.1f lx, corrected=%.1f lx, measured=%.1f lx, difference=%+.1f lx, brightness=%.1f%% -> %d%%%s",
        SUBSTATE_LIGHT_BLUE,
        target_lux,
        stats.last_corrected_value,
        stats.last_measured_value,
        diff_of_lux,
        current_brightness,
        requested_brightness,
        ANSI_RESET,
    )
    if requested_brightness != round(current_brightness):
        applied_brightness = light.set_brightness(requested_brightness, transition=LIGHT_TRANSITION_TIME)
        light_set_brightness.set_value(applied_brightness)
        return requested_brightness
    return requested_brightness


def adjust_until_target_reached(
    controller: LightControlMachine,
    target_lux: float,
    series: LuxSeries,
) -> bool:
    controller._sampler.sample_once()
    stats: MeasurementStatistics = series.statistics(
        window_size_for_target_adjustment=10,
        measurement_filter=AverageFilter(),
    )
    measured_lux = stats.last_corrected_value
    if not controller.is_outside_deadzone(sensor_value=measured_lux):
        series.rebase(measured_lux)
        return True
    if not light_enabled.get_value():
        return False

    requested_brightness = apply_proportional_brightness_adjustment(target_lux =target_lux, measured_lux=measured_lux, stats=stats)
    can_adjust_further = 0 < requested_brightness < 100

    if can_adjust_further:
        for _ in range(10):
            time.sleep(1)
            controller._sampler.sample_once()
        adjust_until_target_reached(
            controller=controller,
            target_lux=light_target_lux.get_value(),
            series=series,
        )

    return False


tick_counter = 0
if __name__ == "__main__":
    normal_lux_series = LuxSeries(
        max_samples=NORMAL_FILTER_WINDOW_SIZE,
        filters=[
            MedianClipFilter(window_size=400, max_deviation=2.0),
            MovingAverageLowPassFilter(window_size=300),
            WeightedMovingAverageFilter(
                window_size=300
            ),
        ],
    )
    normal_lux_sampler = LuxSampler(lux_sensor.get_illuminance, normal_lux_series)

    controller = LightControlMachine(
        settings=LightControlSettings(
            deadzone_lux=DEADZONE_LUX,
            proportional_gain=BRIGHTNESS_PERCENT_PER_LUX,
            minimum_brightness_step=MINIMUM_BRIGHTNESS_STEP,
            maximum_brightness_step=MAXIMUM_BRIGHTNESS_STEP,
            minimum_adjustment_interval_seconds=120,
            minimum_samples=30,
        ),
        series=normal_lux_series,
        sampler=normal_lux_sampler,
    )
    logger.info("Starting light control state machine for %s based on %s", LIGHT_ID, LUX_SENSOR_ID)
    previous_target_lux = -1
    last_lux_sample_at = float("-inf")
    last_collection_log_count = None
    last_waiting_log_at = None
    measurements = None

    while True:
        loop_started_at = time.monotonic()
        tick_counter += 1
        try:
            current_time = time.monotonic()
            if current_time - last_lux_sample_at >= LUX_SAMPLE_PERIOD_SECONDS:
                last_lux_sample_at = current_time
                normal_lux_sampler.sample_once()
                measurements = normal_lux_series.statistics()
                if measurements is not None:
                    lux_corrected_illuminance_sensor.set_value(int(measurements.last_corrected_value))


            if not light_enabled.get_value():
                controller.disable_automation()
                continue

            controller.enable_automation()

            if measurements is not None and measurements.count >= controller.settings.minimum_samples:
                current_brightness = light.get_brightness()
                current_time = time.monotonic()
                target_lux = light_target_lux.get_value()
                controller._target_lux = target_lux
                if target_lux != previous_target_lux:
                    if previous_target_lux != -1:
                        logger.info(
                            "Target lux changed from %.1f to %.1f",
                            previous_target_lux,
                            target_lux,
                        )
                    target_reached = adjust_until_target_reached(
                        controller=controller,
                        target_lux=target_lux,
                        series=normal_lux_series,
                    )
                    previous_target_lux = target_lux
                else:
                    requested_brightness = controller.observe(
                        measurements=measurements,
                        target_lux=target_lux,
                        current_brightness=current_brightness,
                        now=current_time,
                    )
                    if requested_brightness is not None:
                        if requested_brightness != current_brightness:
                            applied_brightness = light.set_brightness(
                                requested_brightness,
                                transition=LIGHT_TRANSITION_TIME,
                            )
                            light_set_brightness.set_value(applied_brightness)
                            logger.info(
                                "Adjusted brightness to %s%% (median %.1f lux, target %.1f lux)",
                                applied_brightness,
                                measurements.median,
                                target_lux,
                            )
                        controller.mark_adjustment_applied()
                state_display = f"{STATE_BOLD_GREEN}{controller.active_state.name}{ANSI_RESET}"
                logger.info(
                    "State=%s target=%.1f lux measured=%.1f lux filtered=%.1f lux median=%.1f lux slope=%.2f lux/s",
                    state_display,
                    target_lux,
                    measurements.last_measured_value,
                    measurements.last_corrected_value,
                    measurements.median,
                    measurements.slope_per_second,
                )
                last_collection_log_count = None
                if controller.active_state == LightControlState.WAITING:
                    if last_waiting_log_at is None or current_time - last_waiting_log_at >= 5.0:
                        elapsed = controller.adjustment_wait_elapsed_seconds
                        remaining = max(
                            0.0,
                            controller.settings.minimum_adjustment_interval_seconds - elapsed,
                        )
                        logger.info(
                            "%s\tSuspended, waiting %.0fs before next adjustment, difference=%.1f lux, is in dead zone:%s %s",
                            SUBSTATE_LIGHT_BLUE,
                            remaining,
                            abs(target_lux - controller.control_lux),
                            controller.is_inside_deadzone(),
                            ANSI_RESET,
                        )
                        last_waiting_log_at = current_time
                else:
                    last_waiting_log_at = None
            elif measurements is not None and measurements.count != last_collection_log_count:
                logger.info(
                    "%s\tInitializing: collecting lux samples %d/%d; target control has not started (target=%.1f lx, measured=%.1f lx)%s",
                    SUBSTATE_LIGHT_BLUE,
                    measurements.count,
                    controller.settings.minimum_samples,
                    light_target_lux.get_value(),
                    measurements.last_measured_value,
                    ANSI_RESET,
                )
                last_collection_log_count = measurements.count
        except Exception as err:
            logger.exception("Light control cycle failed: %s", err)
            controller.handle_cycle_error()

        time.sleep(max(0.0, SAMPLE_PERIOD_SECONDS - (time.monotonic() - loop_started_at)))
