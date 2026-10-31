from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Protocol


class TimedWord(Protocol):
    start_ms: int
    end_ms: int
    word: str


class ClipBoundaryError(ValueError):
    pass


@dataclass(frozen=True)
class ClipRange:
    start_ms: int
    end_ms: int

    @property
    def duration_ms(self) -> int:
        return self.end_ms - self.start_ms


@dataclass(frozen=True)
class ClipWord:
    start_ms: int
    end_ms: int
    word: str


def validate_clip_range(
    start_ms: int,
    end_ms: int,
    *,
    source_duration_ms: int,
    minimum_duration_ms: int = 1000,
    maximum_duration_ms: int = 90_000,
) -> ClipRange:
    if source_duration_ms <= 0:
        raise ClipBoundaryError("Source duration is unavailable.")
    if start_ms < 0 or end_ms <= start_ms:
        raise ClipBoundaryError("Clip boundaries are invalid.")
    if end_ms > source_duration_ms:
        raise ClipBoundaryError("Clip end exceeds the source duration.")
    duration_ms = end_ms - start_ms
    if duration_ms < minimum_duration_ms:
        raise ClipBoundaryError("Clip is shorter than the configured minimum.")
    if duration_ms > maximum_duration_ms:
        raise ClipBoundaryError("Clip exceeds the configured maximum.")
    return ClipRange(start_ms, end_ms)


def clip_relative_words(words: Iterable[TimedWord], clip: ClipRange) -> list[ClipWord]:
    relative: list[ClipWord] = []
    for item in sorted(words, key=lambda value: (value.start_ms, value.end_ms)):
        text = item.word.strip()
        if not text or item.end_ms <= clip.start_ms or item.start_ms >= clip.end_ms:
            continue
        start_ms = max(0, item.start_ms - clip.start_ms)
        end_ms = min(clip.duration_ms, item.end_ms - clip.start_ms)
        if end_ms <= start_ms:
            continue
        relative.append(ClipWord(start_ms, end_ms, text))
    return relative
