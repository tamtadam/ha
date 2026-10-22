from pathlib import Path

import pytest

from ha.apis.light_control import (
    LightControlMachine,
    LightControlSettings,
    LightControlState,
    TransitionDefinition,
)
from ha.apis.light_measurements import (
    AverageFilter,
    ExponentialMovingAverageFilter,
    LuxSampler,
    LuxSeries,
    MedianClipFilter,
    MeasurementSeries,
    MovingAverageLowPassFilter,
    RollingMedianFilter,
    TempSample,
    TempSampler,
    TempSeries,
    LuxStatistics,
    WeightedMovingAverageFilter,
)


def test_series_calculates_average_median_and_slope() -> None:
    series = LuxSeries(max_samples=4)
    series.add(100, timestamp=0)
    series.add(110, timestamp=1)
    series.add(120, timestamp=2)

    result = series.statistics()

    assert result is not None
    assert result.count == 3
    assert result.average_lux == 110
    assert result.median_lux == 110
    assert result.slope_lux_per_second == 10


def test_series_keeps_only_the_most_recent_samples() -> None:
    series = LuxSeries(max_samples=2)
    series.add(10, timestamp=0)
    series.add(20, timestamp=1)
    series.add(30, timestamp=2)

    assert [sample.lux for sample in series.samples] == [20, 30]


def test_series_rebase_replaces_values_and_preserves_timestamps() -> None:
    series = LuxSeries(max_samples=3)
    for timestamp, lux in enumerate((12, 18, 24)):
        series.add(lux, timestamp=float(timestamp))

    series.rebase(20)

    assert [sample.lux for sample in series.samples] == [20, 20, 20]
    assert [sample.timestamp for sample in series.samples] == [0.0, 1.0, 2.0]


def test_series_rejects_invalid_or_out_of_order_samples() -> None:
    series = LuxSeries()
    series.add(10, timestamp=1)

    with pytest.raises(ValueError):
        series.add(float("nan"), timestamp=2)
    with pytest.raises(ValueError):
        series.add(20, timestamp=0)


def test_sampler_reads_source_and_appends_timestamped_sample() -> None:
    series = LuxSeries()
    sampler = LuxSampler(lambda: 42.0, series, clock=lambda: 12.5)

    sample = sampler.sample_once()

    assert sample.lux == 42
    assert sample.timestamp == 12.5
    assert series.samples == (sample,)


def test_temperature_series_reuses_measurement_base() -> None:
    series = TempSeries(max_samples=3)
    sampler = TempSampler(lambda: 21.5, series, clock=lambda: 10.0)

    sample = sampler.sample_once()
    result = series.statistics()

    assert isinstance(series, MeasurementSeries)
    assert isinstance(sample, TempSample)
    assert sample.temperature == 21.5
    assert result is not None
    assert result.average_temperature == 21.5
    assert result.median_temperature == 21.5


def test_series_applies_median_clip_before_calculating_statistics() -> None:
    series = LuxSeries(filters=[MedianClipFilter(window_size=3, max_deviation=10)])
    series.add(100, timestamp=0)
    series.add(102, timestamp=1)
    series.add(500, timestamp=2)

    result = series.statistics()

    assert series.samples[-1].lux == 500
    assert series.filtered_samples[-1].lux == 111
    assert result is not None
    assert result.average_lux == pytest.approx((100 + 102 + 111) / 3)


def test_series_applies_moving_average_low_pass_filter() -> None:
    series = LuxSeries(filters=[MovingAverageLowPassFilter(window_size=3)])
    for timestamp, lux in enumerate((10, 20, 30, 50)):
        series.add(lux, timestamp=timestamp)

    assert [sample.lux for sample in series.filtered_samples] == pytest.approx(
        [10, 15, 20, 100 / 3]
    )


def test_exponential_moving_average_carries_weight_across_full_sequence() -> None:
    series = LuxSeries(filters=[ExponentialMovingAverageFilter(smoothing_factor=0.5)])
    for timestamp, lux in enumerate((10, 20, 30, 40)):
        series.add(lux, timestamp=float(timestamp))

    assert [sample.lux for sample in series.filtered_samples] == pytest.approx(
        [10, 15, 22.5, 31.25]
    )


def test_weighted_moving_average_updates_incrementally_across_window() -> None:
    series = LuxSeries(filters=[WeightedMovingAverageFilter(window_size=3)])
    for timestamp, lux in enumerate((10, 20, 30, 40, 50)):
        series.add(lux, timestamp=float(timestamp))

    assert [sample.lux for sample in series.filtered_samples] == pytest.approx(
        [10, 50 / 3, 140 / 6, 200 / 6, 260 / 6]
    )


def test_statistics_can_replace_series_filters_with_arithmetic_average() -> None:
    series = LuxSeries(filters=[MovingAverageLowPassFilter(window_size=2)])
    for timestamp, lux in enumerate((10, 20, 30)):
        series.add(lux, timestamp=float(timestamp))

    result = series.statistics(
        window_size_for_target_adjustment=3,
        measurement_filter=AverageFilter(),
    )

    assert result is not None
    assert result.count == 3
    assert result.last_corrected_value == pytest.approx(20)


def test_low_pass_then_rolling_median_rejects_transient_and_keeps_persistent_level() -> None:
    series = LuxSeries(
        max_samples=300,
        filters=(
            MovingAverageLowPassFilter(window_size=10),
            RollingMedianFilter(window_size=300),
        ),
    )
    for timestamp in range(300):
        series.add(100, timestamp=float(timestamp))

    for timestamp in range(300, 330):
        series.add(400, timestamp=float(timestamp))
    assert series.filtered_samples[-1].lux == 100

    for timestamp in range(330, 481):
        series.add(200, timestamp=float(timestamp))
    assert series.filtered_samples[-1].lux == pytest.approx(200)


def test_series_prints_raw_samples_to_jpeg(tmp_path: Path) -> None:
    series = LuxSeries(filters=[MovingAverageLowPassFilter(window_size=2)])
    series.add(100, timestamp=10)
    series.add(140, timestamp=11)

    output_path = series.print_to_jpg(tmp_path / "plots" / "lux.jpg")

    assert output_path.is_file()
    assert output_path.read_bytes().startswith(b"\xff\xd8")


def test_jpeg_trims_reference_samples_to_retained_series(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from matplotlib.figure import Figure

    captured_lines = []

    def capture_figure(figure: Figure, _path: Path, **_kwargs: object) -> None:
        captured_lines.extend(figure.axes[0].get_lines())

    monkeypatch.setattr(Figure, "savefig", capture_figure)
    series = LuxSeries(max_samples=2)
    series.add(20, timestamp=0)
    series.add(30, timestamp=1)
    series.add(40, timestamp=2)

    series.print_to_jpg(
        tmp_path / "reference.jpg",
        reference_samples=[10, 20, 30],
    )

    assert [line.get_label() for line in captured_lines] == [
        "Nyers mérés",
        "Referencia",
    ]
    assert list(captured_lines[0].get_xdata()) == [0, 1]
    reference_line = next(line for line in captured_lines if line.get_label() == "Referencia")
    assert list(reference_line.get_xdata()) == [0, 1]
    assert list(reference_line.get_ydata()) == [20, 30]


def test_jpeg_trend_line_uses_the_full_filtered_series(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from matplotlib.figure import Figure

    captured_lines = []

    def capture_figure(figure: Figure, _path: Path, **_kwargs: object) -> None:
        captured_lines.extend(figure.axes[0].get_lines())

    monkeypatch.setattr(Figure, "savefig", capture_figure)
    series = LuxSeries()
    for timestamp, lux in enumerate((10, 10, 10, 50)):
        series.add(lux, timestamp=float(timestamp))

    series.print_to_jpg(tmp_path / "trend.jpg")

    trend_line = captured_lines[-1]
    assert trend_line.get_label() == "Teljes trend (12.00 ertek/s)"
    assert list(trend_line.get_ydata()) == pytest.approx([2, 14, 26, 38])


def test_light_controller_adjusts_only_after_sustained_lux_error() -> None:
    controller = LightControlMachine(
        settings=LightControlSettings(minimum_adjustment_interval_seconds=3, minimum_samples=2),
        clock=lambda: 0.0,
    )
    controller.enable_automation()

    controller.observe(
        measurements=LuxStatistics(
            count=1,
            average=100,
            median=100,
            slope_per_second=0,
            last_corrected_value=100,
            last_measured_value=100,
        ),
        target_lux=100,
        current_brightness=50,
        now=0,
    )
    assert controller.active_state == LightControlState.COLLECTING
    controller.observe(
        measurements=LuxStatistics(
            count=2,
            average=100,
            median=100,
            slope_per_second=0,
            last_corrected_value=100,
            last_measured_value=100,
        ),
        target_lux=100,
        current_brightness=50,
        now=1,
    )
    assert controller.active_state == LightControlState.TRACKING

    controller.observe(
        measurements=LuxStatistics(
            count=2,
            average=50,
            median=50,
            slope_per_second=0,
            last_corrected_value=50,
            last_measured_value=50,
        ),
        target_lux=100,
        current_brightness=50,
        now=2,
    )
    assert controller.active_state == LightControlState.WAITING
    assert controller.requested_brightness is None
    controller.observe(
        measurements=LuxStatistics(
            count=2,
            average=50,
            median=50,
            slope_per_second=0,
            last_corrected_value=50,
            last_measured_value=50,
        ),
        target_lux=100,
        current_brightness=50,
        now=4,
    )
    assert controller.active_state == LightControlState.WAITING
    assert controller.requested_brightness is None

    requested = controller.observe(
        measurements=LuxStatistics(
            count=2,
            average=50,
            median=50,
            slope_per_second=0,
            last_corrected_value=50,
            last_measured_value=50,
        ),
        target_lux=100,
        current_brightness=50,
        now=5,
    )

    assert requested == 55
    assert controller.active_state == LightControlState.ADJUSTING
    controller.mark_adjustment_applied()
    assert controller.active_state == LightControlState.TRACKING


def test_light_controller_uses_corrected_lux_for_normal_operation() -> None:
    controller = LightControlMachine(
        settings=LightControlSettings(deadzone_lux=5, minimum_samples=30),
        clock=lambda: 1.0,
    )
    controller.enable_automation()
    measurements = LuxStatistics(
        count=300,
        average=50,
        median=30,
        slope_per_second=0,
        last_corrected_value=97,
        last_measured_value=80,
    )

    requested_brightness = controller.observe(
        measurements=measurements,
        target_lux=92,
        current_brightness=49,
        now=1,
    )

    assert requested_brightness is None
    assert controller.active_state == LightControlState.TRACKING


def test_zero_lux_is_used_for_explicit_deadzone_check() -> None:
    controller = LightControlMachine(
        settings=LightControlSettings(deadzone_lux=5, minimum_samples=1),
        clock=lambda: 1.0,
    )
    controller.enable_automation()
    controller.observe(
        measurements=LuxStatistics(
            count=1,
            average=97,
            median=97,
            slope_per_second=0,
            last_corrected_value=97,
            last_measured_value=0,
        ),
        target_lux=97,
        current_brightness=49,
        now=1,
    )

    assert controller.is_outside_deadzone(sensor_value=0)


def test_light_controller_caps_brightness_step_for_large_lux_error() -> None:
    controller = LightControlMachine(
        settings=LightControlSettings(
            deadzone_lux=5,
            maximum_brightness_step=5,
            minimum_samples=1,
            minimum_adjustment_interval_seconds=0,
        ),
        clock=lambda: 1.0,
    )
    controller.enable_automation()

    controller.observe(
        measurements=LuxStatistics(
            count=1,
            average=100,
            median=100,
            slope_per_second=0,
            last_corrected_value=100,
            last_measured_value=100,
        ),
        target_lux=14,
        current_brightness=49,
        now=1,
    )
    requested_brightness = controller.observe(
        measurements=LuxStatistics(
            count=1,
            average=100,
            median=100,
            slope_per_second=0,
            last_corrected_value=100,
            last_measured_value=100,
        ),
        target_lux=14,
        current_brightness=49,
        now=2,
    )

    assert requested_brightness == 44
    assert controller.active_state == LightControlState.ADJUSTING


def test_light_controller_recovers_from_adjustment_exception_without_fault_state() -> None:
    controller = LightControlMachine(
        settings=LightControlSettings(
            minimum_samples=1,
            minimum_adjustment_interval_seconds=0,
        ),
        clock=lambda: 1.0,
    )
    controller.enable_automation()
    measurements = LuxStatistics(
        count=1,
        average=100,
        median=100,
        slope_per_second=0,
        last_corrected_value=100,
        last_measured_value=100,
    )
    controller.observe(
        measurements=measurements,
        target_lux=200,
        current_brightness=50,
        now=1,
    )
    controller.observe(
        measurements=measurements,
        target_lux=200,
        current_brightness=50,
        now=2,
    )
    assert controller.active_state == LightControlState.ADJUSTING

    controller.handle_cycle_error()

    assert controller.active_state == LightControlState.WAITING
    assert not hasattr(LightControlState, "FAULT")
    assert controller._error_started_at is None


def test_light_controller_restarts_wait_when_error_direction_changes() -> None:
    controller = LightControlMachine(
        settings=LightControlSettings(minimum_adjustment_interval_seconds=3, minimum_samples=2),
        clock=lambda: 0.0,
    )
    controller.enable_automation()
    controller.observe(
        measurements=LuxStatistics(
            count=2,
            average=50,
            median=50,
            slope_per_second=0,
            last_corrected_value=50,
            last_measured_value=50,
        ),
        target_lux=50,
        current_brightness=50,
        now=0,
    )
    controller.observe(
        measurements=LuxStatistics(
            count=2,
            average=50,
            median=50,
            slope_per_second=0,
            last_corrected_value=50,
            last_measured_value=50,
        ),
        target_lux=100,
        current_brightness=50,
        now=1,
    )

    controller.observe(
        measurements=LuxStatistics(
            count=2,
            average=50,
            median=50,
            slope_per_second=0,
            last_corrected_value=50,
            last_measured_value=50,
        ),
        target_lux=0,
        current_brightness=50,
        now=3,
    )
    assert controller.active_state == LightControlState.WAITING
    assert controller.observe(
        measurements=LuxStatistics(
            count=2,
            average=50,
            median=50,
            slope_per_second=0,
            last_corrected_value=50,
            last_measured_value=50,
        ),
        target_lux=0,
        current_brightness=50,
        now=5,
    ) is None
    assert controller.observe(
        measurements=LuxStatistics(
            count=2,
            average=50,
            median=50,
            slope_per_second=0,
            last_corrected_value=50,
            last_measured_value=50,
        ),
        target_lux=0,
        current_brightness=50,
        now=6,
    ) == 32


def test_light_controller_logs_state_transitions_at_info_level(
    caplog: pytest.LogCaptureFixture,
) -> None:
    controller = LightControlMachine(LightControlSettings(minimum_samples=2))

    with caplog.at_level("INFO", logger="ha.apis.light_control"):
        controller.enable_automation()

    assert "Light control state: disabled -> collecting (automation enabled)" in caplog.text


def test_transition_definition_is_callable_and_omits_optional_fields() -> None:
    transition = TransitionDefinition(
        trigger="disable",
        source=(LightControlState.COLLECTING, LightControlState.TRACKING),
        destination=LightControlState.DISABLED,
    )

    assert transition() == {
        "trigger": "disable",
        "source": [LightControlState.COLLECTING, LightControlState.TRACKING],
        "dest": LightControlState.DISABLED,
    }
