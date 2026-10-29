from __future__ import annotations

from pathlib import Path

import httpx
from groq import APIStatusError, RateLimitError
from pydantic import SecretStr
import pytest

from app.config import get_settings
from app.services.transcription import (
    GroqTranscriptionProvider,
    PermanentTranscriptionError,
    TranscriptSegmentData,
    TranscriptWordData,
    TranscriptionResult,
    merge_chunk_results,
    parse_verbose_transcription,
)


def test_verbose_json_preserves_word_and_segment_timestamps() -> None:
    result = parse_verbose_transcription(
        {
            "text": "Sat sri akaal",
            "language": "pa",
            "segments": [{"start": 0.1, "end": 1.4, "text": "Sat sri akaal"}],
            "words": [
                {"start": 0.1, "end": 0.4, "word": "Sat", "confidence": 0.9},
                {"start": 0.5, "end": 0.8, "word": "sri"},
                {"start": 0.9, "end": 1.4, "word": "akaal"},
            ],
        }
    )
    assert result.language == "pa"
    assert result.segments[0].start_ms == 100
    assert result.words[-1].end_ms == 1400


def test_chunk_offsets_and_overlap_duplicates_are_merged() -> None:
    first = TranscriptionResult(
        text="hello world",
        language="en",
        segments=(TranscriptSegmentData(0, 10_000, "hello world"),),
        words=(
            TranscriptWordData(0, 500, "hello"),
            TranscriptWordData(9_300, 9_800, "world"),
        ),
    )
    second = TranscriptionResult(
        text="world again",
        language="en",
        segments=(TranscriptSegmentData(0, 5_000, "world again"),),
        words=(
            TranscriptWordData(300, 800, "world"),
            TranscriptWordData(1_100, 1_600, "again"),
        ),
    )
    merged = merge_chunk_results([(0, first), (9_000, second)])
    assert [word.word for word in merged.words] == ["hello", "world", "again"]
    assert merged.words[-1].start_ms == 10_100


class _Transcriptions:
    def __init__(self, outcomes):
        self.outcomes = list(outcomes)
        self.calls = 0

    def create(self, **_kwargs):
        self.calls += 1
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


class _Audio:
    def __init__(self, outcomes):
        self.transcriptions = _Transcriptions(outcomes)


class _Client:
    def __init__(self, outcomes):
        self.audio = _Audio(outcomes)


def _status_error(status: int) -> APIStatusError:
    response = httpx.Response(
        status,
        request=httpx.Request("POST", "https://api.groq.com/openai/v1/audio/transcriptions"),
    )
    if status == 429:
        return RateLimitError("rate limited", response=response, body=None)
    return APIStatusError("request failed", response=response, body=None)


def test_groq_rate_limit_uses_bounded_retry(tmp_path: Path) -> None:
    payload = {"text": "hello", "segments": [], "words": [{"start": 0, "end": 0.5, "word": "hello"}]}
    client = _Client([_status_error(429), payload])
    sleeps: list[int] = []
    settings = get_settings().model_copy(
        update={"groq_api_key": SecretStr("test"), "transcription_api_max_retries": 2}
    )
    provider = GroqTranscriptionProvider(settings, client=client, sleep=sleeps.append)
    assert provider.transcribe(tmp_path / "audio.flac").text == "hello"
    assert client.audio.transcriptions.calls == 2
    assert sleeps == [1]


def test_groq_authentication_failure_is_permanent(tmp_path: Path) -> None:
    settings = get_settings().model_copy(update={"groq_api_key": SecretStr("test")})
    provider = GroqTranscriptionProvider(
        settings, client=_Client([_status_error(401)]), sleep=lambda _seconds: None
    )
    with pytest.raises(PermanentTranscriptionError, match="rejected"):
        provider.transcribe(tmp_path / "audio.flac")
