from __future__ import annotations

from collections import deque
from collections.abc import Sequence
from dataclasses import dataclass, replace
import math
import statistics
import numpy as np
from typing import Generic, Protocol, TypeVar



class FilterSample(Protocol):
    value: float


SampleT = TypeVar("SampleT", bound=FilterSample)


class MeasurementFilter(Protocol[SampleT]):
    def apply(self, samples: Sequence[SampleT]) -> tuple[SampleT, ...]: ...

from scipy.signal import savgol_filter

class SavitzkyGolayFilter:
    def __init__(self, window_size: int, polyorder: int = 2):
        self.window_size = window_size
        self.polyorder = polyorder

    def apply(self, samples: tuple[SampleT, ...]) -> tuple[SampleT, ...]:

        if not samples:
            return samples
        # A Savitzky-Golay ablakméretének kötelezően páratlannak kell lennie
        w_size = self.window_size
        if w_size % 2 == 0:
            w_size += 1
        # Ha még nincs elég minta a szűréshez, vagy az ablakméret kisebb/egyenlő, mint a polinom foka,
        # akkor a szűrő hibát dobna. Ekkor szűrés nélkül (vagy fallback-ként) adjuk vissza az adatot.
        if len(samples) <= self.polyorder or len(samples) < w_size:
            return samples

        # Kivesszük az értékeket, átengedjük a Savitzky-Golay szűrőn
        values = [s.value for s in samples]
        filtered_values = savgol_filter(values, window_length=w_size, polyorder=self.polyorder)
        
        # Visszacsomagoljuk az eredeti mintatípusba a megtartott időbélyegekkel
        return tuple(
            replace(sample, value=float(f_val))
            for sample, f_val in zip(samples, filtered_values)
        )

@dataclass(frozen=True)
class PolyFit(Generic[SampleT]):
    """Fit a polynomial to the samples and replace values with the fitted curve."""
    window_size: int = 5

    def apply(self, samples: Sequence[SampleT]) -> tuple[SampleT, ...]:
        from ha.apis.utils.my_stats import MeasurementSample
        if not samples:
            return tuple(samples)
        samples = samples[-self.window_size:]
        x = np.array([v.timestamp for v in samples])
        y = np.array([v.value for v in samples])
        try:
            meredekseg, tengelymetszet = np.polyfit(x, y, 1)
            y_egyenes = meredekseg * x + tengelymetszet
        except:
            return tuple(samples)

        # 6. Az eredmények visszacsomagolása MeasurementSample objektumokba
        egyenes_adatok = [
            MeasurementSample(timestamp=ts, value=val)
            for ts, val in zip(x, y_egyenes, strict=False)
        ]
        return tuple(egyenes_adatok)

    def meredekseg(self, samples: Sequence[SampleT]) -> float:
        if not samples:
            return 0.0
        x = np.array([v.timestamp for v in samples])
        y = np.array([v.value for v in samples])
        try:
            meredekseg, _ = np.polyfit(x, y, 1)
            return meredekseg
        except:
            return 0.0
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
        trailing_samples = samples[-self.window_size:]
        baseline = statistics.median(sample.value for sample in trailing_samples)
        for sample in trailing_samples:
            value = min(
                max(sample.value, baseline - self.max_deviation),
                baseline + self.max_deviation,
            )
            filtered.append(replace(sample, value=value))
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
        median = statistics.fmean(sample.value for sample in samples)
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
