from __future__ import annotations

from abc import abstractmethod
from ha.apis.utils.statehandler import StateHandler
from collections.abc import Callable
from dataclasses import dataclass
import logging
import math

from ha.apis.utils.my_stats import MeasurementStatistics

logger = logging.getLogger(__name__)

SUBSTATE_LIGHT_BLUE = "\033[94m"
SUBSTATE_YELLOW = "\033[93m"
ANSI_RESET = "\033[0m"
LIGHT_CHANGE_STEP_INTERVAL_SECONDS = 30.0
TARGET_CHANGE_STEP_INTERVAL_SECONDS = 10.0
TARGET_CHANGE_MAXIMUM_BRIGHTNESS_STEP = 1.0
TARGET_CHANGE_WINDOW_SIZE = 10

@dataclass(frozen=True)
class LightControlSettings:
    deadzone_lux: float = 12.0
    proportional_gain: float = 0.35
    minimum_brightness_step: float = 2.0
    maximum_brightness_step: float = 5.0
    minimum_adjustment_interval_seconds: float = 20.0
    minimum_samples: int = 5


@dataclass
class LightContext:
    """Az állapotok közös adata és a külvilág elérése (callable-ök)."""

    settings: LightControlSettings
    is_enabled: Callable[[], bool]
    get_brightness: Callable[[], float]
    set_brightness: Callable[[int], None]
    turn_off: Callable[[], None]
    statistics_for: Callable[[int], MeasurementStatistics]
    rebase: Callable[[float], None]
    clock: Callable[[], float]
    statistics: MeasurementStatistics | None = None
    target_lux: float = 0.0
    previous_target_lux: float | None = None
    target_changed: bool = False

    @property
    def sample_count(self) -> int:
        return 0 if self.statistics is None else self.statistics.count

    @property
    def control_lux(self) -> float | None:
        return None if self.statistics is None else self.statistics.last_corrected_value

    def update_target(self, *, target_lux: float) -> None:
        if target_lux != self.previous_target_lux:
            if self.previous_target_lux is not None:
                logger.info("Target lux changed from %.1f to %.1f", self.previous_target_lux, target_lux)
            self.previous_target_lux = target_lux
            self.target_changed = True
        self.target_lux = target_lux

    def is_outside_deadzone(self, *, lux: float | None = None) -> bool:
        if lux is None:
            lux = self.control_lux
        if lux is None:
            return False
        difference = abs(self.target_lux - lux)
        return difference > self.settings.deadzone_lux


class Disabled(StateHandler):
    collecting: StateHandler

    def decide(self) -> StateHandler:
        if self.context.is_enabled():
            return self.collecting
        return self

    def apply(self) -> None:
        if self.context.get_brightness() > 0:
            self.context.turn_off()
            logger.info("Automation disabled, light turned off")


class Collecting(StateHandler):
    disabled: StateHandler
    tracking: StateHandler

    def __init__(self, *, context: LightContext) -> None:
        self.context: LightContext = context
        super().__init__(context=context)
        self._last_logged_count: int | None = None

    def pre(self) -> None:
        self._last_logged_count = None

    def decide(self) -> StateHandler:
        if not self.context.is_enabled():
            return self.disabled
        if self.context.sample_count >= self.context.settings.minimum_samples:
            return self.tracking
        return self

    def apply(self) -> None:
        logger.info(
            "%s\tInitializing: collecting lux samples %d/%d (target=%.1f lx, measured=%.1f lx)%s",
            SUBSTATE_LIGHT_BLUE,
            self.context.sample_count,
            self.context.settings.minimum_samples,
            self.context.target_lux,
            self.context.statistics.last_measured_value,
            ANSI_RESET,
        )


class Tracking(StateHandler):
    disabled: StateHandler
    adjusting_for_light_change: StateHandler
    adjusting_for_target_change: StateHandler
    context: LightContext

    def decide(self) -> StateHandler:
        if not self.context.is_enabled():
            return self.disabled
        if self.context.target_changed:
            return self.adjusting_for_target_change
        if self.context.is_outside_deadzone():
            return self.adjusting_for_light_change
        return self

    def apply(self) -> None:
        statistics = self.context.statistics
        logger.info(
            "State=%s target=%.1f lux measured=%.1f lux filtered=%.1f lux median=%.1f lux slope=%.2f lux/s",
            self.name,
            self.context.target_lux,
            statistics.last_measured_value,
            statistics.last_corrected_value,
            statistics.median,
            statistics.slope_per_second,
        )


class Adjusting(StateHandler):
    """Közös lépéslogika: a fényerőt addig állítja, amíg a mért érték a holtzónába nem ér."""

    disabled: StateHandler
    tracking: StateHandler
    step_interval_seconds: float
    description: str
    context: LightContext

    def __init__(self, *, context: LightContext) -> None:
        super().__init__(context=context)
        self._finished = False
        self._trigger_counter: int = int(self.step_interval_seconds)

    def maximum_step(self) -> float:
        return self.context.settings.maximum_brightness_step

    @abstractmethod
    def measured_lux(self) -> float:
        """A korrekcióhoz használt mért érték (az állapot saját ablakával)."""

    def on_deadzone_reached(self, *, measured_lux: float) -> None:
        """Akkor fut, amikor a mért érték a holtzónába ért."""

    def pre(self) -> None:
        self._finished = False
        self._trigger_counter = int(self.step_interval_seconds)

    def decide(self) -> StateHandler:
        if not self.context.is_enabled():
            return self.disabled
        if self._finished:
            return self.tracking
        return self

    def apply(self) -> None:
        """Egy iteráció: a célt addig közelíti, amíg el nem éri vagy a fényerő határára nem ér."""
        context = self.context
        settings = context.settings
        if self._trigger_counter > 0:
            logger.info(
                "%s%s Waiting%s for the light and sensor to settle, next step in %s",
                SUBSTATE_YELLOW,
                self.name,
                ANSI_RESET,
                self._trigger_counter,
            )
            self._trigger_counter -= 1
            return

        measured_lux = self.measured_lux()
        if not context.is_outside_deadzone(lux=measured_lux):
            self.on_deadzone_reached(measured_lux=measured_lux)
            self._finished = True
            return

        lux_error = context.target_lux - measured_lux
        step = lux_error * settings.proportional_gain
        if abs(step) < settings.minimum_brightness_step:
            step = math.copysign(settings.minimum_brightness_step, lux_error)
        step = math.copysign(min(abs(step), self.maximum_step()), step)
        current_brightness = context.get_brightness()
        requested = round(max(0.0, min(100.0, current_brightness + step)))
        self._trigger_counter = int(self.step_interval_seconds)

        # A 0%-os kérés kikapcsolja a lámpát, ezzel az átállítás véget ér.
        if requested == current_brightness:
            self._finished = True
            return
        context.set_brightness(requested)
        logger.info(
            "%s\tFine-tuning (%s): brightness %.0f%% -> %d%% (measured %.1f lux, target %.1f lux)%s",
            SUBSTATE_LIGHT_BLUE,
            self.description,
            current_brightness,
            requested,
            measured_lux,
            context.target_lux,
            ANSI_RESET,
        )
        if not 0 < requested < 100:
            self._finished = True


class AdjustingForLightChange(Adjusting):
    """Fényváltozás után: lassú, óvatos korrekció."""

    adjusting_for_target_change: StateHandler
    step_interval_seconds = LIGHT_CHANGE_STEP_INTERVAL_SECONDS
    description = "light change"

    def measured_lux(self) -> float:
        return self.context.statistics.last_corrected_value

    def decide(self) -> StateHandler:
        if self.context.is_enabled() and self.context.target_changed:
            return self.adjusting_for_target_change
        return super().decide()


class AdjustingForTargetChange(Adjusting):
    """Célváltás után: várakozás nélkül, gyorsabban közelít."""

    step_interval_seconds = TARGET_CHANGE_STEP_INTERVAL_SECONDS
    description = "target change"

    def measured_lux(self) -> float:
        return self.context.statistics_for(window = TARGET_CHANGE_WINDOW_SIZE).last_corrected_value

    def on_deadzone_reached(self, *, measured_lux: float) -> None:
        # A lassú szűrők felzárkóztatása a gyorsan mért értékhez.
        self.context.rebase(measured_lux)

    def maximum_step(self) -> float:
        return max(super().maximum_step(), TARGET_CHANGE_MAXIMUM_BRIGHTNESS_STEP)

    def pre(self) -> None:
        super().pre()
        self.context.target_changed = False

    def decide(self) -> StateHandler:
        # Újabb célváltás közben is tovább közelítünk, az apply az élő célt használja.
        self.context.target_changed = False
        return super().decide()
