from __future__ import annotations

import csv
from collections import deque
from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace
from datetime import datetime
import math
from pathlib import Path
import statistics
import time
from typing import Generic, TypeVar

from ha.apis.utils.filters import (
    AverageFilter,
    ExponentialMovingAverageFilter,
    MeasurementFilter,
    MedianClipFilter,
    MovingAverageLowPassFilter,
    RollingMedianFilter,
    SavitzkyGolayFilter,
    WeightedMovingAverageFilter,
    PolyFit
)


@dataclass(frozen=True)
class MeasurementSample:
    timestamp: float
    value: float


@dataclass(frozen=True)
class LuxSample(MeasurementSample):
    @property
    def lux(self) -> float:
        return self.value


@dataclass(frozen=True)
class TempSample(MeasurementSample):
    @property
    def temperature(self) -> float:
        return self.value


@dataclass(frozen=True)
class MeasurementStatistics:
    count: int
    average: float
    median: float
    max_value: float
    slope_per_second: float
    last_corrected_value: float
    last_measured_value: float
    first_measured_value: float
    time_spent_in_seconds: float
    total_slope_in_cycle: float
    first_timestamp: float
    last_timestamp: float

@dataclass(frozen=True)
class LuxStatistics(MeasurementStatistics):
    @property
    def average_lux(self) -> float:
        return self.average

    @property
    def median_lux(self) -> float:
        return self.median

    @property
    def slope_lux_per_second(self) -> float:
        return self.slope_per_second


@dataclass(frozen=True)
class TempStatistics(MeasurementStatistics):
    @property
    def average_temperature(self) -> float:
        return self.average

    @property
    def median_temperature(self) -> float:
        return self.median

    @property
    def slope_temperature_per_second(self) -> float:
        return self.slope_per_second


SampleT = TypeVar("SampleT", bound=MeasurementSample)
StatisticsT = TypeVar("StatisticsT", bound=MeasurementStatistics)


class MeasurementSeries(Generic[SampleT, StatisticsT]):
    """Bounded numeric measurement series with common window statistics."""

    sample_type: type[SampleT] = MeasurementSample  # type: ignore[assignment]
    statistics_type: type[StatisticsT] = MeasurementStatistics  # type: ignore[assignment]

    def __init__(
        self,
        max_samples: int = 60,
        filters: Sequence[MeasurementFilter[SampleT]] = (),
    ) -> None:
        if max_samples < 2:
            raise ValueError("max_samples must be at least 2")
        self._samples: deque[SampleT] = deque(maxlen=max_samples)
        self.filters = tuple(filters)

    @property
    def samples(self) -> tuple[SampleT, ...]:
        return tuple(self._samples)

    def filtered_samples(
        self,
        window_size_for_target_adjustment: int = 0,
        measurement_filters: list[MeasurementFilter[SampleT]] | None = None,
    ) -> tuple[SampleT, ...]:
        window_size = window_size_for_target_adjustment or len(self.samples)
        samples = self.samples[-window_size:]
        if window_size <= 0:
            return ()

        if measurement_filters is None:
            filters = self.filters
        else:
            filters = measurement_filters

        for active_filter in filters:
            samples = active_filter.apply(samples)
        return samples

    def add(self, value: float, timestamp: float | None = None) -> SampleT:
        sample_time = time.monotonic() if timestamp is None else timestamp
        if not math.isfinite(value):
            raise ValueError("measurement value must be finite")
        if not math.isfinite(sample_time):
            raise ValueError("timestamp must be finite")
        if self._samples and sample_time < self._samples[-1].timestamp:
            raise ValueError("sample timestamps must be ordered")

        sample = self.sample_type(timestamp=sample_time, value=value)
        self._samples.append(sample)
        return sample

    def rebase(self, value: float) -> None:
        """Replace stored values with a new baseline while preserving timestamps."""
        if not math.isfinite(value):
            raise ValueError("measurement value must be finite")
        self._samples = deque(
            (replace(sample, value=value) for sample in self._samples),
            maxlen=self._samples.maxlen,
        )

    def statistics(
        self,
        window_size_for_target_adjustment: int = 0,
        measurement_filters: list[MeasurementFilter[SampleT]] | None = None,
    ) -> StatisticsT | None:
        samples = self.filtered_samples(
            window_size_for_target_adjustment=window_size_for_target_adjustment,
            measurement_filters=measurement_filters,
        )
        if not samples:
            return None

        average = statistics.fmean(sample.value for sample in samples)
        median = statistics.median(sample.value for sample in samples)
        max_value = max(sample.value for sample in samples)
        spend_time_in_seconds = self.samples[-1].timestamp - self.samples[0].timestamp if self.samples else 0.0
        slope = PolyFit().meredekseg(self.samples[-len(samples):])

        return self.statistics_type(
            count=len(samples),
            average=average,
            median=median,
            slope_per_second=slope,
            last_corrected_value=median,
            last_measured_value=self.samples[-1].value,
            first_measured_value=self.samples[0].value,
            time_spent_in_seconds=spend_time_in_seconds,
            total_slope_in_cycle = self.samples[-1].value - self.samples[0].value,
            max_value=max_value,
            first_timestamp=self.samples[0].timestamp,
            last_timestamp=self.samples[-1].timestamp,
        )
    def draw_line_from_start_to_end_by_slop(self, start_value: float, end_value: float, slope_in_the_frame: float, first_timestamp: float, last_timestamp: float, sample_amount: int, time_step: int = 1) -> list[MeasurementSample]:
        """Generate a line from start to end value based on the given slope."""
        spend_time_in_seconds = last_timestamp - first_timestamp
        if sample_amount == 1:
            return [MeasurementSample(timestamp=first_timestamp, value=start_value)]
        time_step = time_step if time_step is not None else spend_time_in_seconds / (sample_amount - 1)
        return [MeasurementSample(timestamp=first_timestamp + t * time_step, value=start_value + (slope_in_the_frame/sample_amount) * t) for t in range(sample_amount)]

    def print_to_jpg(
        self,
        path: str | Path,
        reference_samples: Sequence[float] | None = None,
    ) -> Path:
        """Save raw and reference samples as a JPEG plot."""
        try:
            from matplotlib.figure import Figure
        except ImportError as exc:
            raise RuntimeError("A grafikon mentéséhez telepítsd a matplotlib csomagot.") from exc

        output_path = Path(path).expanduser()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        raw_samples = self.samples
        if reference_samples is not None:
            if len(reference_samples) < len(raw_samples):
                print(
                    ValueError(
                        "reference_samples cannot contain fewer values than the raw samples"
                    )
                )
            if len(reference_samples) > len(raw_samples):
                reference_samples = (
                    reference_samples[-len(raw_samples):] if raw_samples else ()
                )
        sample_indices = range(len(raw_samples))

        figure = Figure(figsize=(12, 6))
        axes = figure.subplots()
        axes.plot(
            sample_indices,
            [sample.value for sample in raw_samples],
            label="Nyers mérés",
            alpha=0.35,
            linewidth=0.8,
            drawstyle="steps-post",
        )
        if reference_samples:
            axes.plot(
                sample_indices,
                reference_samples,
                label="Referencia",
                color="tab:green",
                linewidth=1.2,
                alpha=0.8,
                linestyle="--",
            )

        axes.legend()
        axes.set_xlabel("Minta sorszáma")
        axes.set_ylabel("Fényerő (lux)")
        axes.grid(True, alpha=0.3)
        figure.tight_layout()
        figure.savefig(output_path, format="jpg", dpi=150)
        return output_path


class LuxSeries(MeasurementSeries[LuxSample, LuxStatistics]):
    sample_type = LuxSample
    statistics_type = LuxStatistics


class TempSeries(MeasurementSeries[TempSample, TempStatistics]):
    sample_type = TempSample
    statistics_type = TempStatistics


class MeasurementSampler(Generic[SampleT, StatisticsT]):
    """Read numeric measurements from a callable and append timestamped samples."""

    def __init__(
        self,
        read_value: Callable[[], float],
        series: MeasurementSeries[SampleT, StatisticsT],
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._read_value = read_value
        self.series = series
        self._clock = clock

    def sample_once(self) -> SampleT:
        return self.series.add(self._read_value(), timestamp=self._clock())


class LuxSampler(MeasurementSampler[LuxSample, LuxStatistics]):
    def __init__(
        self,
        read_lux: Callable[[], float],
        series: LuxSeries | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        super().__init__(read_lux, series or LuxSeries(), clock)


class TempSampler(MeasurementSampler[TempSample, TempStatistics]):
    def __init__(
        self,
        read_temperature: Callable[[], float],
        series: TempSeries | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        super().__init__(read_temperature, series or TempSeries(), clock)


if __name__ == "__main__":
    from datetime import datetime, timedelta
    history_path = Path("/Users/trenyikadam/Documents/dev/ha/ha/apis/services/kitchenvent/history.csv")
    with history_path.open(newline="", encoding="utf-8") as history_file:
        history = list(csv.DictReader(history_file))
    TEMPERATURE_WINDOW_SECONDS = 120
    temperature_series = TempSeries(
        max_samples=24*60*60,
        filters=[
            PolyFit(window_size=TEMPERATURE_WINDOW_SECONDS),
        ],
    )
    history_by_timestamp = {}
    for row in history:
        timestamp = datetime.fromisoformat(
            row["last_changed"].replace("Z", "+00:00")
        ).timestamp()
        history_by_timestamp[int(timestamp)] = row


    start_dt = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    SECONDS_IN_DAY = 24 * 60 * 60
    current_state = None
    reference_samples = []
    max_value = 0
    stat_round_table_cnt = 0
    for s in range(SECONDS_IN_DAY):
        current_dt = start_dt + timedelta(seconds=s, days=-1)
        timestamp = current_dt.timestamp()
        if int(timestamp) in history_by_timestamp:
            row = history_by_timestamp[int(timestamp)]
            current_state = float(row["state"])
        if current_state is not None:

            result = temperature_series.statistics()
            if result:
                reference_samples.append(result.median)

            temperature_series.add(current_state, timestamp=timestamp)

            if result and stat_round_table_cnt % 100 == 0:
                print(f"Timestamp: {datetime.fromtimestamp(timestamp)}, Current state: {current_state}, slope_per_second: {result.slope_per_second}, total_slope_in_cycle: {result.total_slope_in_cycle}")
            stat_round_table_cnt += 1
    output_path = temperature_series.print_to_jpg(
        "temperature_series.jpg",
        reference_samples=reference_samples + [v.value for v in temperature_series.samples[-400:]],
    )
    lux_series = LuxSeries(
        max_samples=max(2, len(history)),
        filters=[
            MedianClipFilter(window_size=TEMPERATURE_WINDOW_SECONDS, max_deviation=0.5),
            RollingMedianFilter(window_size=TEMPERATURE_WINDOW_SECONDS),
            MovingAverageLowPassFilter(window_size=TEMPERATURE_WINDOW_SECONDS),
            WeightedMovingAverageFilter(
                window_size=TEMPERATURE_WINDOW_SECONDS
            ),
            SavitzkyGolayFilter(window_size=TEMPERATURE_WINDOW_SECONDS                                                                                                                                                                                                                                                                                                                                                                                                              ),
        ],
    )
    reference_samples = []
    cnt = 0
    for row in history:
        timestamp = datetime.fromisoformat(
            row["last_changed"].replace("Z", "+00:00")
        ).timestamp()
        lux_series.add(float(row["state"]), timestamp=timestamp)
        result = lux_series.statistics()

        reference_samples.append(result.last_corrected_value)
        cnt += 1
        if cnt % 1000 == 0:
            print(f"Processed {cnt} samples")
    result = lux_series.statistics()

    if result is not None:
        print(f"Samples: {result.count}")
        print(f"Average lux: {result.average_lux:.1f}")
        print(f"Median lux: {result.median_lux:.1f}")
        print(f"Lux slope: {result.slope_lux_per_second:.2f} lux/s")

    output_path = lux_series.print_to_jpg(
        "lux_measurements.jpg",
        reference_samples=reference_samples,
    )
    print(f"Plot saved to: {output_path}")
