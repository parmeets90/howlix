from __future__ import annotations

import pytest

from app.config import get_settings
from app.services.transcription import GroqTranscriptionProvider


pytestmark = pytest.mark.integration


def test_live_groq_transcription_only_when_explicitly_enabled() -> None:
    settings = get_settings()
    if not settings.run_groq_integration_tests:
        pytest.skip("Set RUN_GROQ_INTEGRATION_TESTS=true to allow a live Groq request.")
    if settings.groq_api_key is None:
        pytest.skip("GROQ_API_KEY is not configured.")
    audio_path = settings.groq_integration_audio_path
    if audio_path is None or not audio_path.is_file():
        pytest.skip("Set GROQ_INTEGRATION_AUDIO_PATH to a small speech-audio fixture.")
    result = GroqTranscriptionProvider(settings).transcribe(audio_path)
    assert result.text.strip()
    assert result.segments or result.words
