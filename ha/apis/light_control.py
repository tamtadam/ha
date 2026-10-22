from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
import logging
import math
import time

from transitions import Machine

from ha.apis.light_measurements import LuxSampler, MeasurementSeries, MeasurementStatistics

logger = logging.getLogger(__name__)


class LightControlState(Enum):
    DISABLED = "disabled"
    COLLECTING = "collecting"
    TRACKING = "tracking"
    WAITING = "waiting"
    ADJUSTING = "adjusting"


@dataclass(frozen=True)
class LightControlSettings:
    deadzone_lux: float = 12.0
    proportional_gain: float = 0.35
    minimum_brightness_step: float = 2.0
    maximum_brightness_step: float = 5.0
    minimum_adjustment_interval_seconds: float = 20.0
    minimum_samples: int = 5


# Átmenet: HONNAN --[ESEMÉNY | FELTÉTEL]--> HOVÁ.
@dataclass(frozen=True)
class TransitionDefinition:
    trigger: str
    source: LightControlState | tuple[LightControlState, ...]
    destination: LightControlState | None
    conditions: str | None = None
    after: str | None = None

    def __call__(self) -> dict[str, object]:
        transition: dict[str, object] = {
            "trigger": self.trigger,
            "source": list(self.source) if isinstance(self.source, tuple) else self.source,
            "dest": self.destination,
        }
        if self.conditions is not None:
            transition["conditions"] = self.conditions
        if self.after is not None:
            transition["after"] = self.after
        return transition


class LightControlMachine:
    """Decide when persistent lux errors should adjust light brightness."""

    _states = tuple(LightControlState)
    ENABLE_AUTOMATION = TransitionDefinition(
        trigger="enable",
        source=LightControlState.DISABLED,
        destination=LightControlState.COLLECTING,
    )
    DISABLE_AUTOMATION = TransitionDefinition(
        trigger="disable",
        source=_states[1:],
        destination=LightControlState.DISABLED,
    )
    COLLECTING_HAS_ERROR = TransitionDefinition(
        trigger="process_sample",
        source=LightControlState.COLLECTING,
        destination=LightControlState.WAITING,
        conditions="has_ready_error",
    )
    COLLECTING_HAS_DATA = TransitionDefinition(
        trigger="process_sample",
        source=LightControlState.COLLECTING,
        destination=LightControlState.TRACKING,
        conditions="has_ready_data",
    )
    COLLECTING_NEEDS_MORE_DATA = TransitionDefinition(
        trigger="process_sample",
        source=LightControlState.COLLECTING,
        destination=None,
    )
    TRACKING_ERROR_DETECTED = TransitionDefinition(
        trigger="process_sample",
        source=LightControlState.TRACKING,
        destination=LightControlState.WAITING,
        conditions="is_outside_deadzone",
    )
    TRACKING_STAYS_STABLE = TransitionDefinition(
        trigger="process_sample",
        source=LightControlState.TRACKING,
        destination=None,
    )
    WAITING_ERROR_CLEARED = TransitionDefinition(
        trigger="process_sample",
        source=LightControlState.WAITING,
        destination=LightControlState.TRACKING,
        conditions="is_inside_deadzone",
        after="clear_adjustment_timer",
    )
    WAITING_LUX_DIFFERENCE_SUSTAINED = TransitionDefinition(
        trigger="process_sample",
        source=LightControlState.WAITING,
        destination=LightControlState.ADJUSTING,
        conditions="lux_difference_is_sustained",
        after="calculate_brightness",
    )
    WAITING_FOR_SUSTAINED_ERROR = TransitionDefinition(
        trigger="process_sample",
        source=LightControlState.WAITING,
        destination=None,
    )
    ADJUSTMENT_FAILED = TransitionDefinition(
        trigger="adjustment_failed",
        source=LightControlState.ADJUSTING,
        destination=LightControlState.WAITING,
        after="clear_adjustment_timer",
    )
    ADJUSTMENT_APPLIED = TransitionDefinition(
        trigger="adjustment_applied",
        source=LightControlState.ADJUSTING,
        destination=LightControlState.TRACKING,
        after="clear_adjustment_timer",
    )

    _transitions = [
        ENABLE_AUTOMATION,
        DISABLE_AUTOMATION,
        COLLECTING_HAS_ERROR,
        COLLECTING_HAS_DATA,
        COLLECTING_NEEDS_MORE_DATA,
        TRACKING_ERROR_DETECTED,
        TRACKING_STAYS_STABLE,
        WAITING_ERROR_CLEARED,
        WAITING_LUX_DIFFERENCE_SUSTAINED,
        WAITING_FOR_SUSTAINED_ERROR,
        ADJUSTMENT_FAILED,
        ADJUSTMENT_APPLIED,
    ]

    @property
    def active_state(self) -> LightControlState:
        return self.state

    @property
    def control_lux(self) -> float | None:
        if self._statistics is None:
            return None
        return self._statistics.last_corrected_value

    def __init__(
        self,
        settings: LightControlSettings | None = None,
        series: MeasurementSeries | None = None,
        sampler: LuxSampler | None = None,
        *,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.settings = settings or LightControlSettings()
        self._series: MeasurementSeries | None = series
        self._sampler: LuxSampler | None = sampler
        self._clock = clock
        self._statistics: MeasurementStatistics | None = None
        self._target_lux = 0.0
        self._current_brightness = 0.0
        self._observed_at = 0.0
        self._error_started_at: float | None = None
        self._brightness_correction_direction = 0
        self.requested_brightness: int | None = None
        self.machine = Machine(
            model=self,
            states=self._states,
            transitions=[transition() for transition in self._transitions],
            initial=LightControlState.DISABLED,
            auto_transitions=False,
        )

    def enable_automation(self) -> None:
        if self.active_state == LightControlState.DISABLED:
            previous_state = self.active_state
            self.enable()
            self._log_state_transition(previous_state, "automation enabled")

    def disable_automation(self) -> None:
        if self.active_state != LightControlState.DISABLED:
            previous_state = self.active_state
            self.disable()
            self._log_state_transition(previous_state, "automation disabled")

    def handle_cycle_error(self) -> None:
        self.clear_adjustment_timer()
        if self.active_state == LightControlState.ADJUSTING:
            previous_state = self.active_state
            self.adjustment_failed()
            self._log_state_transition(previous_state, "brightness adjustment failed; retrying")

    def observe(
        self,
        measurements: MeasurementStatistics,
        target_lux: float,
        current_brightness: float,
        *,
        now: float | None = None,
    ) -> int | None:
        previous_state = self.active_state
        self._statistics = measurements
        self._target_lux = target_lux
        self._current_brightness = current_brightness
        self._observed_at = self._clock() if now is None else now
        self.requested_brightness = None

        if measurements.count >= self.settings.minimum_samples:
            control_lux = self.control_lux
            if control_lux is not None and self.is_outside_deadzone():
                brightness_correction_direction = (
                    1 if target_lux > control_lux else -1
                )
                if (
                    self._error_started_at is None
                    or brightness_correction_direction != self._brightness_correction_direction
                ):
                    self._error_started_at = self._observed_at
                    self._brightness_correction_direction = brightness_correction_direction
            else:
                self.clear_adjustment_timer()

        if self.active_state in {
            LightControlState.COLLECTING,
            LightControlState.TRACKING,
            LightControlState.WAITING,
        }:
            self.process_sample()
        self._log_state_transition(previous_state, "sample processed")

        return self.requested_brightness

    def mark_adjustment_applied(self) -> None:
        previous_state = self.active_state
        self.adjustment_applied()
        self._log_state_transition(previous_state, "brightness adjustment applied")

    def _log_state_transition(self, previous_state: str, event: str) -> None:
        if self.active_state != previous_state:
            logger.info(
                "Light control state: %s -> %s (%s)",
                previous_state.value,
                self.active_state.value,
                event,
            )

    def has_ready_data(self) -> bool:
        return (
            self._statistics is not None
            and self._statistics.count >= self.settings.minimum_samples
        )

    def has_ready_error(self) -> bool:
        return self.has_ready_data() and self.is_outside_deadzone()

    def is_outside_deadzone(self, sensor_value: float | None = None) -> bool:
        control_lux = sensor_value if sensor_value is not None else self.control_lux
        return (
            control_lux is not None
            and abs(self._target_lux - control_lux) > self.settings.deadzone_lux
        )

    def is_inside_deadzone(self) -> bool:
        return self.has_ready_data() and not self.is_outside_deadzone()

    def lux_difference_is_sustained(self) -> bool:
        return (
            self._error_started_at is not None
            and self._observed_at - self._error_started_at >= self.settings.minimum_adjustment_interval_seconds
        )

    @property
    def adjustment_wait_elapsed_seconds(self) -> float:
        if self._error_started_at is None:
            return 0.0
        return max(0.0, self._observed_at - self._error_started_at)

    def clear_adjustment_timer(self) -> None:
        self._error_started_at = None
        self._brightness_correction_direction = 0

    def calculate_brightness(self) -> None:
        if self._statistics is None or self.control_lux is None:
            return
        measurements: MeasurementStatistics = self._series.statistics(20)
        lux_error = self._target_lux - measurements.last_corrected_value
        step = lux_error * self.settings.proportional_gain
        if abs(step) < self.settings.minimum_brightness_step:
            step = math.copysign(self.settings.minimum_brightness_step, lux_error)
        step = math.copysign(
            min(abs(step), self.settings.maximum_brightness_step),
            step,
        )
        self.requested_brightness = round(
            max(0.0, min(100.0, self._current_brightness + step))
        )
