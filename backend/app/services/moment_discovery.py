from __future__ import annotations

import json
import math
import re
import time
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.config import Settings


ANALYSIS_WEIGHTS = {
    "hook_strength": 0.30,
    "story_payoff": 0.25,
    "emotional_engagement": 0.15,
    "standalone_clarity": 0.15,
    "pacing": 0.10,
    "visual_quality": 0.05,
}
ASSESSED_WEIGHT = sum(
    weight for factor, weight in ANALYSIS_WEIGHTS.items() if factor != "visual_quality"
)
STRICT_STRUCTURED_OUTPUT_MODELS = {
    "openai/gpt-oss-20b",
    "openai/gpt-oss-120b",
    "qwen/qwen3.8-27b",
}


class MomentAnalysisError(RuntimeError):
    pass


class TransientMomentAnalysisError(MomentAnalysisError):
    pass


class PermanentMomentAnalysisError(MomentAnalysisError):
    pass


@dataclass(frozen=True)
class SegmentData:
    start_ms: int
    end_ms: int
    text: str


@dataclass(frozen=True)
class WordData:
    start_ms: int
    end_ms: int
    word: str


@dataclass(frozen=True)
class CandidateWindow:
    candidate_id: str
    start_ms: int
    end_ms: int
    text: str

    @property
    def duration_ms(self) -> int:
        return self.end_ms - self.start_ms


class FactorScores(BaseModel):
    model_config = ConfigDict(extra="forbid")

    hook_strength: float = Field(ge=0, le=100)
    story_payoff: float = Field(ge=0, le=100)
    emotional_engagement: float = Field(ge=0, le=100)
    standalone_clarity: float = Field(ge=0, le=100)
    pacing: float = Field(ge=0, le=100)
    visual_quality: None = None


class _LLMFactorScores(BaseModel):
    model_config = ConfigDict(extra="forbid")

    hook_strength: float = Field(ge=0, le=100)
    story_payoff: float = Field(ge=0, le=100)
    emotional_engagement: float = Field(ge=0, le=100)
    standalone_clarity: float = Field(ge=0, le=100)
    pacing: float = Field(ge=0, le=100)


class _LLMEvaluation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    candidate_id: str = Field(min_length=1, max_length=64)
    suggested_title: str = Field(min_length=1, max_length=200)
    hook_text: str = Field(min_length=1, max_length=500)
    topic: str = Field(min_length=1, max_length=160)
    category: str = Field(min_length=1, max_length=80)
    scores: _LLMFactorScores
    explanation: str = Field(min_length=1, max_length=1200)
    confidence_notes: str = Field(min_length=1, max_length=800)
    needs_context: bool


class _LLMBatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    evaluations: list[_LLMEvaluation]


@dataclass(frozen=True)
class MomentEvaluation:
    candidate_id: str
    suggested_title: str
    hook_text: str
    topic: str
    category: str
    scores: FactorScores
    explanation: str
    confidence_notes: str
    needs_context: bool


@dataclass(frozen=True)
class AnalyzerResult:
    evaluations: tuple[MomentEvaluation, ...]
    usage: dict[str, int] | None = None


class MomentAnalyzer(Protocol):
    name: str
    model: str

    def analyze(
        self,
        candidates: list[CandidateWindow],
        *,
        language: str | None,
        source_duration_ms: int,
    ) -> AnalyzerResult: ...


def score_breakdown(scores: FactorScores) -> tuple[float, dict[str, dict[str, Any]]]:
    weighted = 0.0
    breakdown: dict[str, dict[str, Any]] = {}
    values = scores.model_dump()
    for factor, weight in ANALYSIS_WEIGHTS.items():
        value = values[factor]
        assessed = value is not None
        breakdown[factor] = {"score": value, "weight": weight, "assessed": assessed}
        if assessed:
            weighted += float(value) * weight
    return round(weighted / ASSESSED_WEIGHT, 2), breakdown


def temporal_iou(left: CandidateWindow, right: CandidateWindow) -> float:
    intersection = max(0, min(left.end_ms, right.end_ms) - max(left.start_ms, right.start_ms))
    union = max(left.end_ms, right.end_ms) - min(left.start_ms, right.start_ms)
    return intersection / union if union else 0.0


def transcript_similarity(left: str, right: str) -> float:
    normalize = lambda value: re.sub(r"\s+", " ", re.sub(r"[^\w\s]", " ", value.casefold())).strip()
    first, second = normalize(left), normalize(right)
    if not first or not second:
        return 0.0
    first_tokens, second_tokens = set(first.split()), set(second.split())
    union = first_tokens | second_tokens
    jaccard = len(first_tokens & second_tokens) / len(union) if union else 0.0
    return max(jaccard, SequenceMatcher(None, first, second).ratio())


def _ends_sentence(text: str) -> bool:
    return bool(re.search(r"[.!?\u0964\u0965]\s*$", text.strip()))


def generate_candidate_windows(
    segments: list[SegmentData],
    *,
    source_duration_ms: int,
    min_duration_ms: int,
    max_duration_ms: int,
    target_duration_ms: int,
    max_candidates: int,
) -> list[CandidateWindow]:
    if source_duration_ms <= 0 or min_duration_ms <= 0 or max_duration_ms < min_duration_ms:
        return []
    cleaned = [
        SegmentData(
            max(0, item.start_ms),
            min(source_duration_ms, item.end_ms),
            item.text.strip(),
        )
        for item in sorted(segments, key=lambda item: (item.start_ms, item.end_ms))
        if item.text.strip() and item.end_ms > item.start_ms and item.start_ms < source_duration_ms
    ]
    cleaned = [item for item in cleaned if item.end_ms > item.start_ms]
    if not cleaned or cleaned[-1].end_ms - cleaned[0].start_ms < min_duration_ms:
        return []

    provisional: list[CandidateWindow] = []
    for start_index, start in enumerate(cleaned):
        if start_index > 0:
            previous = cleaned[start_index - 1]
            natural_start = start.start_ms - previous.end_ms >= 650 or _ends_sentence(previous.text)
            if not natural_start and start_index % 2:
                continue
        best: tuple[float, int] | None = None
        for end_index in range(start_index, len(cleaned)):
            end = cleaned[end_index]
            duration = end.end_ms - start.start_ms
            if duration > max_duration_ms:
                break
            if duration < min_duration_ms:
                continue
            next_start = cleaned[end_index + 1].start_ms if end_index + 1 < len(cleaned) else None
            pause_ms = max(0, next_start - end.end_ms) if next_start is not None else 1000
            natural_end_bonus = (6000 if _ends_sentence(end.text) else 0) + min(pause_ms, 2000) * 3
            quality = -abs(duration - target_duration_ms) + natural_end_bonus
            if best is None or quality > best[0]:
                best = (quality, end_index)
        if best is None:
            continue
        end_index = best[1]
        end = cleaned[end_index]
        text = " ".join(item.text for item in cleaned[start_index : end_index + 1]).strip()
        if not text:
            continue
        candidate = CandidateWindow("pending", start.start_ms, end.end_ms, text)
        if any(temporal_iou(candidate, existing) >= 0.88 for existing in provisional[-4:]):
            continue
        provisional.append(candidate)

    if len(provisional) > max_candidates:
        step = (len(provisional) - 1) / max(max_candidates - 1, 1)
        selected_indexes = sorted({round(index * step) for index in range(max_candidates)})
        provisional = [provisional[index] for index in selected_indexes]
    return [
        CandidateWindow(f"candidate-{index:03d}", item.start_ms, item.end_ms, item.text)
        for index, item in enumerate(provisional, start=1)
    ]


def refine_boundaries(
    candidate: CandidateWindow,
    words: list[WordData],
    *,
    source_duration_ms: int,
    min_duration_ms: int,
    max_duration_ms: int,
) -> tuple[int, int]:
    relevant = [
        word
        for word in words
        if word.word.strip()
        and word.end_ms >= candidate.start_ms
        and word.start_ms <= candidate.end_ms
    ]
    if not relevant:
        return candidate.start_ms, min(candidate.end_ms, source_duration_ms)
    start_ms = max(0, relevant[0].start_ms)
    end_ms = min(source_duration_ms, relevant[-1].end_ms)
    duration = end_ms - start_ms
    if duration < min_duration_ms or duration > max_duration_ms:
        return candidate.start_ms, min(candidate.end_ms, source_duration_ms)
    return start_ms, end_ms


def deduplicate_ranked(
    items: list[tuple[CandidateWindow, MomentEvaluation, float, dict[str, Any]]],
    *,
    limit: int,
    minimum_score: float,
) -> list[tuple[CandidateWindow, MomentEvaluation, float, dict[str, Any]]]:
    selected: list[tuple[CandidateWindow, MomentEvaluation, float, dict[str, Any]]] = []
    topic_counts: dict[str, int] = {}
    for item in sorted(items, key=lambda value: (-value[2], value[0].start_ms)):
        window, evaluation, score, _breakdown = item
        if score < minimum_score:
            continue
        topic_key = re.sub(r"[^\w]+", " ", evaluation.topic.casefold()).strip()
        if topic_key and topic_counts.get(topic_key, 0) >= 2:
            continue
        duplicate = any(
            temporal_iou(window, existing[0]) >= 0.62
            or transcript_similarity(window.text, existing[0].text) >= 0.86
            for existing in selected
        )
        if duplicate:
            continue
        selected.append(item)
        if topic_key:
            topic_counts[topic_key] = topic_counts.get(topic_key, 0) + 1
        if len(selected) >= limit:
            break
    return selected


class DeterministicFixtureAnalyzer:
    name = "fixture"
    model = "deterministic-v1"

    def analyze(
        self,
        candidates: list[CandidateWindow],
        *,
        language: str | None,
        source_duration_ms: int,
    ) -> AnalyzerResult:
        del language, source_duration_ms
        evaluations: list[MomentEvaluation] = []
        hook_terms = ("why", "how", "secret", "surprising", "never", "क्या", "क्यों", "कैसे")
        emotion_terms = ("love", "fear", "lost", "won", "hope", "खुशी", "डर", "जीत", "शहीद")
        for candidate in candidates:
            text = candidate.text.strip()
            lower = text.casefold()
            word_count = len(text.split())
            hook = 58 + (14 if "?" in text else 0) + (10 if any(term in lower for term in hook_terms) else 0)
            story = 58 + (12 if _ends_sentence(text) else 0) + min(12, word_count / 18)
            emotion = 48 + (18 if any(term in lower for term in emotion_terms) else 0)
            clarity = 72 if word_count >= 35 else 55
            pacing = 70 if 35 <= word_count <= 220 else 56
            first_sentence = re.split(r"(?<=[.!?\u0964])\s+", text, maxsplit=1)[0]
            if any(term in lower for term in ("budget", "expense")):
                topic, category = "Personal finance", "advice"
            elif any(term in lower for term in ("sleep", "memory", "study")):
                topic, category = "Sleep and learning", "education"
            elif any(term in lower for term in ("conversation", "disagree", "fair outcome")):
                topic, category = "Communication", "advice"
            elif any(term in lower for term in ("productivity", "task", "focus")):
                topic, category = "Focused productivity", "education"
            elif any(term in lower for term in ("मेहनत", "दिशा", "राह")):
                topic, category = "Direction before speed", "mindset"
            else:
                topic, category = "Standalone insight", "education"
            evaluations.append(
                MomentEvaluation(
                    candidate_id=candidate.candidate_id,
                    suggested_title=(first_sentence[:76].rstrip(" .!?\u0964") or "Recommended moment"),
                    hook_text=first_sentence[:300],
                    topic=topic,
                    category=category,
                    scores=FactorScores(
                        hook_strength=min(100, hook),
                        story_payoff=min(100, story),
                        emotional_engagement=min(100, emotion),
                        standalone_clarity=min(100, clarity),
                        pacing=min(100, pacing),
                        visual_quality=None,
                    ),
                    explanation="The excerpt presents a self-contained idea with a clear opening and conclusion.",
                    confidence_notes="Deterministic offline fixture score; human editorial review is still required.",
                    needs_context=word_count < 35,
                )
            )
        return AnalyzerResult(tuple(evaluations), None)


def _usage_dict(response: Any) -> dict[str, int] | None:
    usage = getattr(response, "usage", None)
    if usage is None:
        return None
    raw = usage.model_dump() if hasattr(usage, "model_dump") else usage
    if not isinstance(raw, dict):
        return None
    return {
        str(key): int(value)
        for key, value in raw.items()
        if isinstance(value, (int, float)) and not isinstance(value, bool)
    }


def groq_retry_delay(error: Any, attempt: int) -> float:
    delay = float(min(2**attempt, 8))
    response = getattr(error, "response", None)
    headers = getattr(response, "headers", {}) or {}
    retry_after = headers.get("retry-after") if hasattr(headers, "get") else None
    if retry_after is not None:
        try:
            delay = max(delay, float(retry_after))
        except (TypeError, ValueError):
            pass
    text = str(getattr(response, "text", "") or "")
    match = re.search(r"try again in\s+([0-9]+(?:\.[0-9]+)?)s", text, re.IGNORECASE)
    if match:
        delay = max(delay, float(match.group(1)))
    return min(delay + 0.25, 60.0)


def groq_error_label(error: Any) -> str:
    status = getattr(error, "status_code", "unknown")
    response = getattr(error, "response", None)
    code = None
    error_type = None
    if response is not None:
        try:
            payload = response.json()
            detail = payload.get("error", {}) if isinstance(payload, dict) else {}
            code = detail.get("code")
            error_type = detail.get("type")
        except (TypeError, ValueError, AttributeError):
            pass
    suffix = ", ".join(
        value for value in (f"code={code}" if code else None, f"type={error_type}" if error_type else None) if value
    )
    return f"HTTP {status}" + (f", {suffix}" if suffix else "")


def groq_error_is_transient(error: Any) -> bool:
    status = getattr(error, "status_code", 0)
    if status == 429 or 500 <= status < 600:
        return True
    response = getattr(error, "response", None)
    if response is None:
        return False
    try:
        payload = response.json()
        detail = payload.get("error", {}) if isinstance(payload, dict) else {}
        return detail.get("code") == "rate_limit_exceeded"
    except (TypeError, ValueError, AttributeError):
        return False


class GroqMomentAnalyzer:
    name = "groq"

    def __init__(self, settings: Settings, client: Any | None = None, sleep=time.sleep) -> None:
        if settings.groq_api_key is None:
            raise PermanentMomentAnalysisError("GROQ_API_KEY is not configured.")
        if client is None:
            from groq import Groq

            client = Groq(
                api_key=settings.groq_api_key.get_secret_value(),
                max_retries=0,
                timeout=120,
            )
        self.client = client
        self.model = settings.groq_moment_model
        self.max_retries = settings.moment_api_max_retries
        self.max_output_tokens = settings.moment_max_output_tokens
        self.sleep = sleep

    def _response_format(self) -> dict[str, Any]:
        if self.model in STRICT_STRUCTURED_OUTPUT_MODELS:
            return {
                "type": "json_schema",
                "json_schema": {
                    "name": "howlix_moment_evaluations",
                    "strict": True,
                    "schema": _LLMBatch.model_json_schema(),
                },
            }
        return {"type": "json_object"}

    def analyze(
        self,
        candidates: list[CandidateWindow],
        *,
        language: str | None,
        source_duration_ms: int,
    ) -> AnalyzerResult:
        from groq import APIConnectionError, APIStatusError, APITimeoutError

        if not candidates:
            return AnalyzerResult(())
        candidate_payload = [
            {
                "candidate_id": item.candidate_id,
                "start_ms": item.start_ms,
                "end_ms": item.end_ms,
                "transcript": item.text,
            }
            for item in candidates
        ]
        system_prompt = (
            "You are a careful short-form video editor. Evaluate only the supplied transcript excerpts. "
            "Never invent spoken content, timestamps, visuals, or unsupported hooks. Loudness, controversy, "
            "and sensational wording are not quality by themselves. Score hook strength, story/payoff, emotional "
            "engagement, standalone clarity, and pacing from 0 to 100. Do not score visual quality. Return JSON "
            "only. Keep hook_text supported verbatim or as a faithful short excerpt from the candidate."
        )
        user_prompt = json.dumps(
            {
                "task": "Evaluate each candidate for YouTube Shorts, Instagram Reels, and TikTok.",
                "language": language,
                "source_duration_ms": source_duration_ms,
                "required_candidate_ids": [item.candidate_id for item in candidates],
                "candidates": candidate_payload,
            },
            ensure_ascii=False,
        )
        expected = {item.candidate_id for item in candidates}
        for attempt in range(self.max_retries + 1):
            try:
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    response_format=self._response_format(),
                    temperature=0.1,
                    max_completion_tokens=self.max_output_tokens,
                )
                content = response.choices[0].message.content or ""
                parsed = _LLMBatch.model_validate(json.loads(content))
                received = [item.candidate_id for item in parsed.evaluations]
                if len(received) != len(set(received)) or not set(received).issubset(expected):
                    raise ValueError("The analyzer returned duplicate or unknown candidate identifiers.")
                evaluations = tuple(
                    MomentEvaluation(
                        candidate_id=item.candidate_id,
                        suggested_title=item.suggested_title.strip(),
                        hook_text=item.hook_text.strip(),
                        topic=item.topic.strip(),
                        category=item.category.strip(),
                        scores=FactorScores(**item.scores.model_dump(), visual_quality=None),
                        explanation=item.explanation.strip(),
                        confidence_notes=item.confidence_notes.strip(),
                        needs_context=item.needs_context,
                    )
                    for item in parsed.evaluations
                )
                return AnalyzerResult(evaluations, _usage_dict(response))
            except (json.JSONDecodeError, ValidationError, ValueError, IndexError, AttributeError) as exc:
                if attempt < self.max_retries:
                    self.sleep(min(2**attempt, 8))
                    continue
                raise PermanentMomentAnalysisError(
                    "Groq returned invalid structured moment-analysis JSON."
                ) from exc
            except APIStatusError as exc:
                transient = groq_error_is_transient(exc)
                if transient and attempt < self.max_retries:
                    self.sleep(groq_retry_delay(exc, attempt))
                    continue
                if transient:
                    raise TransientMomentAnalysisError(
                        "Groq is temporarily unavailable or rate limited moment analysis."
                    ) from exc
                raise PermanentMomentAnalysisError(
                    "Groq rejected the moment-analysis request "
                    f"({groq_error_label(exc)}). Check the configured model and structured-output settings."
                ) from exc
            except (APIConnectionError, APITimeoutError) as exc:
                if attempt < self.max_retries:
                    self.sleep(min(2**attempt, 8))
                    continue
                raise TransientMomentAnalysisError(
                    "Could not reach Groq for moment analysis after bounded retries."
                ) from exc
        raise TransientMomentAnalysisError("Groq moment analysis did not complete.")


def get_moment_analyzer(settings: Settings) -> MomentAnalyzer:
    if settings.moment_analysis_provider == "fixture":
        return DeterministicFixtureAnalyzer()
    return GroqMomentAnalyzer(settings)


def merge_usage(current: dict[str, int] | None, incoming: dict[str, int] | None) -> dict[str, int] | None:
    if not incoming:
        return current
    result = dict(current or {})
    for key, value in incoming.items():
        result[key] = result.get(key, 0) + value
    return result


def bounded_batches(
    candidates: list[CandidateWindow], *, batch_size: int, max_requests: int, max_input_chars: int
) -> list[list[CandidateWindow]]:
    batches: list[list[CandidateWindow]] = []
    current: list[CandidateWindow] = []
    current_chars = 0
    for candidate in candidates:
        candidate_chars = len(candidate.text)
        if candidate_chars > max_input_chars:
            candidate = CandidateWindow(
                candidate.candidate_id,
                candidate.start_ms,
                candidate.end_ms,
                candidate.text[:max_input_chars],
            )
            candidate_chars = max_input_chars
        if current and (len(current) >= batch_size or current_chars + candidate_chars > max_input_chars):
            batches.append(current)
            current, current_chars = [], 0
        current.append(candidate)
        current_chars += candidate_chars
    if current:
        batches.append(current)
    if len(batches) > max_requests:
        raise PermanentMomentAnalysisError("Candidate analysis exceeds the configured API request limit.")
    return batches
