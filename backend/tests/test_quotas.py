from __future__ import annotations

import pytest

from app.config import get_settings
from app.services.quotas import (
    QuotaExceededError,
    consume_analysis,
    consume_transcription,
    reserve_storage,
)
from tests.conftest import TEST_USER_ID


def test_durable_storage_and_monthly_cost_quotas(testing_session_factory) -> None:
    settings = get_settings().model_copy(
        update={
            "beta_max_stored_media_mb": 1,
            "beta_monthly_transcription_minutes": 1,
            "beta_monthly_analysis_jobs": 1,
        }
    )
    with testing_session_factory() as db:
        reserve_storage(db, TEST_USER_ID, 900_000, settings)
        with pytest.raises(QuotaExceededError, match="Storage limit"):
            reserve_storage(db, TEST_USER_ID, 200_000, settings)

        consume_transcription(db, TEST_USER_ID, 60, settings)
        with pytest.raises(QuotaExceededError, match="transcription limit"):
            consume_transcription(db, TEST_USER_ID, 1, settings)

        consume_analysis(db, TEST_USER_ID, settings)
        with pytest.raises(QuotaExceededError, match="AI analysis limit"):
            consume_analysis(db, TEST_USER_ID, settings)
