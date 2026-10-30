from __future__ import annotations

import pytest

from app.config import get_settings
from app.services.moment_discovery import CandidateWindow, GroqMomentAnalyzer


@pytest.mark.integration
def test_live_groq_moment_analysis_only_when_explicitly_enabled() -> None:
    settings = get_settings()
    if not settings.run_moment_groq_integration_tests:
        pytest.skip("Set RUN_MOMENT_GROQ_INTEGRATION_TESTS=true for the paid live Groq check.")
    if settings.groq_api_key is None:
        pytest.skip("GROQ_API_KEY is not configured.")
    result = GroqMomentAnalyzer(settings).analyze(
        [
            CandidateWindow(
                "candidate-001",
                0,
                35_000,
                "What if the usual productivity advice is backwards? Choose one meaningful outcome, finish it, and only then add another task. The payoff is focus rather than a busier calendar.",
            )
        ],
        language="en",
        source_duration_ms=35_000,
    )
    assert len(result.evaluations) == 1
    assert result.evaluations[0].candidate_id == "candidate-001"
