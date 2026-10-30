from __future__ import annotations

from types import SimpleNamespace

import pytest
from pydantic import SecretStr

from app.config import get_settings
from app.services.moment_discovery import (
    CandidateWindow,
    FactorScores,
    GroqMomentAnalyzer,
    PermanentMomentAnalysisError,
    SegmentData,
    WordData,
    deduplicate_ranked,
    generate_candidate_windows,
    groq_retry_delay,
    groq_error_is_transient,
    refine_boundaries,
    score_breakdown,
    temporal_iou,
    transcript_similarity,
)


def _segments(count: int = 12) -> list[SegmentData]:
    return [
        SegmentData(
            index * 10_000,
            (index + 1) * 10_000 - 500,
            f"Sentence {index} explains a useful standalone idea.",
        )
        for index in range(count)
    ]


def test_candidate_generation_respects_duration_source_and_long_overlap() -> None:
    candidates = generate_candidate_windows(
        _segments(),
        source_duration_ms=120_000,
        min_duration_ms=20_000,
        max_duration_ms=90_000,
        target_duration_ms=50_000,
        max_candidates=8,
    )
    assert 2 <= len(candidates) <= 8
    assert all(20_000 <= item.duration_ms <= 90_000 for item in candidates)
    assert all(0 <= item.start_ms < item.end_ms <= 120_000 for item in candidates)
    assert len({item.start_ms for item in candidates}) == len(candidates)


def test_short_or_empty_transcript_has_no_forced_candidate() -> None:
    assert generate_candidate_windows(
        [],
        source_duration_ms=60_000,
        min_duration_ms=20_000,
        max_duration_ms=90_000,
        target_duration_ms=50_000,
        max_candidates=10,
    ) == []
    assert generate_candidate_windows(
        [SegmentData(0, 8_000, "बहुत छोटा अंश।")],
        source_duration_ms=8_000,
        min_duration_ms=20_000,
        max_duration_ms=90_000,
        target_duration_ms=50_000,
        max_candidates=10,
    ) == []


def test_weighted_score_normalizes_unassessed_visual_quality() -> None:
    overall, breakdown = score_breakdown(
        FactorScores(
            hook_strength=80,
            story_payoff=70,
            emotional_engagement=60,
            standalone_clarity=90,
            pacing=50,
            visual_quality=None,
        )
    )
    expected = (80 * 0.30 + 70 * 0.25 + 60 * 0.15 + 90 * 0.15 + 50 * 0.10) / 0.95
    assert overall == round(expected, 2)
    assert breakdown["visual_quality"] == {"score": None, "weight": 0.05, "assessed": False}


def test_boundary_refinement_uses_real_words_without_exceeding_limits() -> None:
    candidate = CandidateWindow("one", 10_000, 60_000, "A complete thought.")
    words = [WordData(11_000, 11_500, "A"), WordData(11_600, 58_000, "thought")]
    assert refine_boundaries(
        candidate,
        words,
        source_duration_ms=70_000,
        min_duration_ms=20_000,
        max_duration_ms=90_000,
    ) == (11_000, 58_000)


def test_temporal_and_text_duplicate_detection() -> None:
    first = CandidateWindow("a", 0, 60_000, "A surprising fact with a clear takeaway")
    second = CandidateWindow("b", 5_000, 62_000, "A surprising fact with a clear takeaway.")
    assert temporal_iou(first, second) > 0.8
    assert transcript_similarity(first.text, second.text) > 0.9


def test_deduplication_keeps_topic_diversity() -> None:
    from app.services.moment_discovery import MomentEvaluation

    scores = FactorScores(
        hook_strength=80,
        story_payoff=80,
        emotional_engagement=70,
        standalone_clarity=85,
        pacing=75,
    )
    texts = {
        "a": "A practical framework for planning a difficult project",
        "b": "Why consistent sleep improves memory and concentration",
        "c": "Three questions to ask before accepting career advice",
        "d": "How community gardens change a neighborhood",
    }

    def item(identifier: str, start: int, topic: str, score: float):
        window = CandidateWindow(identifier, start, start + 30_000, texts[identifier])
        evaluation = MomentEvaluation(
            identifier,
            f"Title {identifier}",
            f"Hook {identifier}",
            topic,
            "education",
            scores,
            "Explanation",
            "Confident",
            False,
        )
        return window, evaluation, score, {}

    selected = deduplicate_ranked(
        [item("a", 0, "Topic A", 90), item("b", 40_000, "Topic A", 89), item("c", 80_000, "Topic A", 88), item("d", 120_000, "Topic B", 87)],
        limit=10,
        minimum_score=50,
    )
    assert [item[0].candidate_id for item in selected] == ["a", "b", "d"]


def test_invalid_groq_json_is_rejected_after_bounded_validation() -> None:
    response = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content="not-json"))],
        usage=None,
    )
    client = SimpleNamespace(
        chat=SimpleNamespace(
            completions=SimpleNamespace(create=lambda **_kwargs: response)
        )
    )
    settings = get_settings().model_copy(
        update={
            "groq_api_key": SecretStr("test"),
            "groq_moment_model": "openai/gpt-oss-20b",
            "moment_api_max_retries": 0,
        }
    )
    analyzer = GroqMomentAnalyzer(settings, client=client, sleep=lambda _seconds: None)
    with pytest.raises(PermanentMomentAnalysisError, match="invalid structured"):
        analyzer.analyze(
            [CandidateWindow("candidate-001", 0, 30_000, "A real transcript excerpt.")],
            language="en",
            source_duration_ms=30_000,
        )


def test_groq_rate_limit_delay_honors_provider_guidance() -> None:
    error = SimpleNamespace(
        response=SimpleNamespace(
            headers={},
            text='{"error":{"message":"Please try again in 25.2s."}}',
        )
    )
    assert groq_retry_delay(error, 0) == 25.45


def test_groq_rate_limit_code_is_transient_even_with_413_status() -> None:
    error = SimpleNamespace(
        status_code=413,
        response=SimpleNamespace(
            json=lambda: {"error": {"code": "rate_limit_exceeded", "type": "tokens"}}
        ),
    )
    assert groq_error_is_transient(error) is True
