from __future__ import annotations

import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from app.config import Settings


class TranscriptionError(RuntimeError):
    pass


class TransientTranscriptionError(TranscriptionError):
    pass


class PermanentTranscriptionError(TranscriptionError):
    pass


class EmptyTranscriptError(PermanentTranscriptionError):
    pass


@dataclass(frozen=True)
class TranscriptSegmentData:
    start_ms: int
    end_ms: int
    text: str


@dataclass(frozen=True)
class TranscriptWordData:
    start_ms: int
    end_ms: int
    word: str
    confidence: float | None = None


@dataclass(frozen=True)
class TranscriptionResult:
    text: str
    language: str | None
    segments: tuple[TranscriptSegmentData, ...]
    words: tuple[TranscriptWordData, ...]


class TranscriptionProvider(Protocol):
    name: str
    model: str

    def transcribe(self, audio_path: Path) -> TranscriptionResult: ...


def _response_dict(response: Any) -> dict[str, Any]:
    if isinstance(response, dict):
        return response
    if hasattr(response, "to_dict"):
        return response.to_dict()
    if hasattr(response, "model_dump"):
        return response.model_dump()
    raise PermanentTranscriptionError("The transcription provider returned an unsupported response.")


def _milliseconds(value: Any) -> int:
    try:
        return max(0, round(float(value) * 1000))
    except (TypeError, ValueError) as exc:
        raise PermanentTranscriptionError("The provider returned an invalid timestamp.") from exc


def parse_verbose_transcription(payload: dict[str, Any]) -> TranscriptionResult:
    segments: list[TranscriptSegmentData] = []
    nested_words: list[dict[str, Any]] = []
    for raw in payload.get("segments") or []:
        text = str(raw.get("text") or "").strip()
        if not text:
            continue
        start_ms = _milliseconds(raw.get("start"))
        end_ms = _milliseconds(raw.get("end"))
        if end_ms < start_ms:
            raise PermanentTranscriptionError("A transcript segment has reversed timestamps.")
        segments.append(TranscriptSegmentData(start_ms, end_ms, text))
        nested_words.extend(raw.get("words") or [])

    words: list[TranscriptWordData] = []
    for raw in (payload.get("words") or nested_words):
        word = str(raw.get("word") or raw.get("text") or "").strip()
        if not word:
            continue
        start_ms = _milliseconds(raw.get("start"))
        end_ms = _milliseconds(raw.get("end"))
        if end_ms < start_ms:
            raise PermanentTranscriptionError("A transcript word has reversed timestamps.")
        probability = raw.get("probability", raw.get("confidence"))
        confidence = float(probability) if probability is not None else None
        words.append(TranscriptWordData(start_ms, end_ms, word, confidence))

    text = str(payload.get("text") or "").strip()
    if not text and segments:
        text = " ".join(segment.text for segment in segments)
    if not text and words:
        text = " ".join(word.word for word in words)
    if not text:
        raise EmptyTranscriptError("No speech was detected in this video.")
    return TranscriptionResult(
        text=text,
        language=str(payload.get("language") or "").strip() or None,
        segments=tuple(segments),
        words=tuple(words),
    )


class GroqTranscriptionProvider:
    name = "groq"

    def __init__(self, settings: Settings, client: Any | None = None, sleep=time.sleep) -> None:
        if settings.groq_api_key is None:
            raise PermanentTranscriptionError("GROQ_API_KEY is not configured.")
        if client is None:
            from groq import Groq

            client = Groq(
                api_key=settings.groq_api_key.get_secret_value(),
                max_retries=0,
                timeout=120,
            )
        self.client = client
        self.model = settings.groq_transcription_model
        self.max_retries = settings.transcription_api_max_retries
        self.sleep = sleep

    def transcribe(self, audio_path: Path) -> TranscriptionResult:
        from groq import APIConnectionError, APIStatusError, APITimeoutError

        for attempt in range(self.max_retries + 1):
            try:
                response = self.client.audio.transcriptions.create(
                    file=audio_path,
                    model=self.model,
                    response_format="verbose_json",
                    timestamp_granularities=["segment", "word"],
                    temperature=0.0,
                )
                return parse_verbose_transcription(_response_dict(response))
            except APIStatusError as exc:
                transient = exc.status_code == 429 or 500 <= exc.status_code < 600
                if transient and attempt < self.max_retries:
                    self.sleep(min(2**attempt, 8))
                    continue
                if transient:
                    raise TransientTranscriptionError(
                        "Groq is temporarily unavailable or rate limited the request."
                    ) from exc
                raise PermanentTranscriptionError(
                    "Groq rejected the transcription request. Check the API key and audio input."
                ) from exc
            except (APIConnectionError, APITimeoutError) as exc:
                if attempt < self.max_retries:
                    self.sleep(min(2**attempt, 8))
                    continue
                raise TransientTranscriptionError(
                    "Could not reach Groq after bounded retries."
                ) from exc
        raise TransientTranscriptionError("Groq transcription did not complete.")


class FasterWhisperTranscriptionProvider:
    name = "faster-whisper"

    def __init__(self, settings: Settings, model_instance: Any | None = None) -> None:
        self.model = settings.faster_whisper_model
        if model_instance is None:
            try:
                from faster_whisper import WhisperModel
            except ImportError as exc:
                raise PermanentTranscriptionError(
                    "The optional faster-whisper dependency is not installed."
                ) from exc
            model_instance = WhisperModel(self.model, device="cpu", compute_type="int8")
        self.model_instance = model_instance

    def transcribe(self, audio_path: Path) -> TranscriptionResult:
        try:
            raw_segments, info = self.model_instance.transcribe(
                str(audio_path),
                beam_size=5,
                word_timestamps=True,
                vad_filter=True,
                task="transcribe",
            )
            segments: list[TranscriptSegmentData] = []
            words: list[TranscriptWordData] = []
            for raw in raw_segments:
                text = str(raw.text or "").strip()
                if text:
                    segments.append(
                        TranscriptSegmentData(
                            _milliseconds(raw.start), _milliseconds(raw.end), text
                        )
                    )
                for item in raw.words or []:
                    word = str(item.word or "").strip()
                    if word:
                        words.append(
                            TranscriptWordData(
                                _milliseconds(item.start),
                                _milliseconds(item.end),
                                word,
                                float(item.probability)
                                if item.probability is not None
                                else None,
                            )
                        )
        except TranscriptionError:
            raise
        except Exception as exc:
            raise TransientTranscriptionError("Local transcription failed.") from exc
        text = " ".join(segment.text for segment in segments).strip()
        if not text:
            raise EmptyTranscriptError("No speech was detected in this video.")
        return TranscriptionResult(
            text=text,
            language=str(getattr(info, "language", "") or "").strip() or None,
            segments=tuple(segments),
            words=tuple(words),
        )


def _normalized(value: str) -> str:
    return re.sub(r"[^\w]+", "", value.casefold())


def merge_chunk_results(
    chunks: list[tuple[int, TranscriptionResult]],
) -> TranscriptionResult:
    merged_segments: list[TranscriptSegmentData] = []
    merged_words: list[TranscriptWordData] = []
    languages: list[str] = []

    for offset_ms, result in chunks:
        if result.language:
            languages.append(result.language)
        for segment in result.segments:
            absolute = TranscriptSegmentData(
                start_ms=offset_ms + segment.start_ms,
                end_ms=offset_ms + segment.end_ms,
                text=segment.text.strip(),
            )
            if (
                merged_segments
                and _normalized(absolute.text) == _normalized(merged_segments[-1].text)
                and absolute.start_ms <= merged_segments[-1].end_ms + 1000
            ):
                continue
            merged_segments.append(absolute)

        for word in result.words:
            absolute = TranscriptWordData(
                start_ms=offset_ms + word.start_ms,
                end_ms=offset_ms + word.end_ms,
                word=word.word.strip(),
                confidence=word.confidence,
            )
            duplicate = any(
                _normalized(candidate.word) == _normalized(absolute.word)
                and abs(candidate.start_ms - absolute.start_ms) <= 1000
                and abs(candidate.end_ms - absolute.end_ms) <= 1000
                for candidate in merged_words[-8:]
            )
            if not duplicate:
                merged_words.append(absolute)

    merged_segments.sort(key=lambda item: (item.start_ms, item.end_ms))
    merged_words.sort(key=lambda item: (item.start_ms, item.end_ms))
    text = " ".join(segment.text for segment in merged_segments).strip()
    if not text:
        text = " ".join(word.word for word in merged_words).strip()
    if not text:
        raise EmptyTranscriptError("No speech was detected in this video.")
    return TranscriptionResult(
        text=text,
        language=languages[0] if languages else None,
        segments=tuple(merged_segments),
        words=tuple(merged_words),
    )


def get_transcription_provider(settings: Settings) -> TranscriptionProvider:
    if settings.transcription_provider == "faster-whisper":
        return FasterWhisperTranscriptionProvider(settings)
    return GroqTranscriptionProvider(settings)
