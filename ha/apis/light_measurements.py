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
from typing import Generic, Protocol, TypeVar


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
    slope_per_second: float
    last_corrected_value: float
    last_measured_value: float


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


class MeasurementFilter(Protocol[SampleT]):
    def apply(self, samples: Sequence[SampleT]) -> tuple[SampleT, ...]: ...


@dataclass(frozen=True)
class MedianClipFilter(Generic[SampleT]):
    """Clip each value to a deviation around the preceding window median."""

    window_size: int = 5
    max_deviation: float = 30.0

    def __post_init__(self) -> None:
        if self.window_size < 1:
            raise ValueError("window_size must be at least 1")
        if not math.isfinite(self.max_deviation) or self.max_deviation <= 0:
            raise ValueError("max_deviation must be finite and greater than 0")

    def apply(self, samples: Sequence[SampleT]) -> tuple[SampleT, ...]:
        filtered: list[SampleT] = []
        baseline = statistics.median([sample.value for sample in samples[-self.window_size:]])
        for sample in samples[-self.window_size:]:
            value = sample.value
            if sample.value < baseline - self.max_deviation:
                value = baseline - self.max_deviation
            elif sample.value > baseline + self.max_deviation:
                value = baseline + self.max_deviation
            filtered_sample = LuxSample(value=value, timestamp=sample.timestamp)
            filtered.append(filtered_sample)
        return tuple(filtered)


@dataclass(frozen=True)
class RollingMedianFilter(Generic[SampleT]):
    """Replace each value with the median of the trailing sample window."""

    window_size: int = 5

    def __post_init__(self) -> None:
        if self.window_size < 1:
            raise ValueError("window_size must be at least 1")

    def apply(self, samples: Sequence[SampleT]) -> tuple[SampleT, ...]:
        filtered: list[SampleT] = []
        median = statistics.fmean([sample.value for sample in samples])
        for sample in samples:
            filtered.append(replace(sample, value=min(median, sample.value)))
        return tuple(filtered)


@dataclass(frozen=True)
class MovingAverageLowPassFilter(Generic[SampleT]):
    """Smooth values with a trailing moving-average window."""

    window_size: int = 5

    def __post_init__(self) -> None:
        if self.window_size < 1:
            raise ValueError("window_size must be at least 1")

    def apply(self, samples: Sequence[SampleT]) -> tuple[SampleT, ...]:
        window: deque[float] = deque(maxlen=self.window_size)
        filtered: list[SampleT] = []
        for sample in samples:
            window.append(sample.value)
            filtered.append(replace(sample, value=statistics.fmean(window)))
        return tuple(filtered)


@dataclass(frozen=True)
class AverageFilter(Generic[SampleT]):
    """Replace sample values with the arithmetic mean of the provided samples."""

    def apply(self, samples: Sequence[SampleT]) -> tuple[SampleT, ...]:
        if not samples:
            return ()

        average = statistics.fmean(sample.value for sample in samples)
        return tuple(replace(sample, value=average) for sample in samples)


@dataclass(frozen=True)
class WeightedMovingAverageFilter(Generic[SampleT]):
    """Smooth samples with linearly increasing weights for newer values."""

    window_size: int = 5

    def __post_init__(self) -> None:
        if self.window_size < 1:
            raise ValueError("window_size must be at least 1")

    def apply(self, samples: Sequence[SampleT]) -> tuple[SampleT, ...]:
        window: deque[SampleT] = deque(maxlen=self.window_size)
        filtered: list[SampleT] = []
        window_total = 0.0
        weighted_total = 0.0
        for sample in samples:
            if len(window) == self.window_size:
                oldest = window.popleft()
                weighted_total -= window_total
                window_total -= oldest.value
            window.append(sample)
            window_total += sample.value
            weighted_total += len(window) * sample.value
            total_weight = len(window) * (len(window) + 1) / 2
            filtered.append(replace(sample, value=weighted_total / total_weight))
        return tuple(filtered)


@dataclass(frozen=True)
class ExponentialMovingAverageFilter(Generic[SampleT]):
    """Smooth the full input sequence recursively, favoring newer samples."""

    smoothing_factor: float = 0.5

    def __post_init__(self) -> None:
        if not math.isfinite(self.smoothing_factor) or not 0 < self.smoothing_factor <= 1:
            raise ValueError("smoothing_factor must be finite and in the interval (0, 1]")

    def apply(self, samples: Sequence[SampleT]) -> tuple[SampleT, ...]:
        filtered: list[SampleT] = []
        average: float | None = None
        for sample in samples:
            average = sample.value if average is None else (
                self.smoothing_factor * sample.value
                + (1 - self.smoothing_factor) * average
            )
            filtered.append(replace(sample, value=average))
        return tuple(filtered)


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
        measurement_filter: MeasurementFilter[SampleT] | None = None,
    ) -> tuple[SampleT, ...]:
        window_size = window_size_for_target_adjustment or len(self.samples)
        samples = self.samples[-window_size:]
        filters = (measurement_filter,) if measurement_filter is not None else self.filters
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
        measurement_filter: MeasurementFilter[SampleT] | None = None,
    ) -> StatisticsT | None:
        samples = self.filtered_samples(
            window_size_for_target_adjustment=window_size_for_target_adjustment,
            measurement_filter=measurement_filter,
        )
        if not samples:
            return None

        average = statistics.fmean(sample.value for sample in samples)
        median = statistics.median(sample.value for sample in samples)
        mean_time = statistics.fmean(sample.timestamp for sample in samples)
        denominator = sum((sample.timestamp - mean_time) ** 2 for sample in samples)
        if denominator == 0:
            slope = 0.0
        else:
            slope = sum(
                (sample.timestamp - mean_time) * (sample.value - average)
                for sample in samples
            ) / denominator

        return self.statistics_type(
            count=len(samples),
            average=average,
            median=median,
            slope_per_second=slope,
            last_corrected_value=samples[-1].value,
            last_measured_value=self.samples[-1].value,
        )

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
                raise ValueError(
                    "reference_samples cannot contain fewer values than the raw samples"
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
    history_path = Path(__file__).with_name("history.csv")
    with history_path.open(newline="", encoding="utf-8") as history_file:
        history = list(csv.DictReader(history_file))

    lux_series = LuxSeries(
        max_samples=max(2, len(history)),
        filters=[
            MedianClipFilter(window_size=400, max_deviation=2.0),
            MovingAverageLowPassFilter(window_size=300),
            WeightedMovingAverageFilter(
                window_size=300
            ),
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
