from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

import app.main as main_module
from app.config import Settings


def test_shared_supabase_defaults_to_isolated_howlix_schema() -> None:
    settings = Settings(_env_file=None, HOWLIX_DATABASE_URL="sqlite:///:memory:")

    assert settings.database_schema == "howlix"
    assert "https://howlix.wolvesgang.digital" in settings.cors_origins
    assert "api.howlix.wolvesgang.digital" in settings.allowed_hosts


@pytest.mark.parametrize("schema", ["public;drop schema public", "invalid-name", "1howlix"])
def test_database_schema_rejects_unsafe_identifiers(schema: str) -> None:
    with pytest.raises(ValidationError):
        Settings(
            _env_file=None,
            HOWLIX_DATABASE_URL="sqlite:///:memory:",
            HOWLIX_DATABASE_SCHEMA=schema,
        )


def test_production_app_disables_docs_and_rejects_unknown_hosts(monkeypatch) -> None:
    settings = Settings(
        _env_file=None,
        HOWLIX_DATABASE_URL="sqlite:///:memory:",
        HOWLIX_ENVIRONMENT="production",
        HOWLIX_ALLOWED_HOSTS="api.howlix.wolvesgang.digital",
        HOWLIX_CORS_ORIGINS="https://howlix.wolvesgang.digital",
    )
    monkeypatch.setattr(main_module, "get_settings", lambda: settings)
    production_app = main_module.create_app()

    with TestClient(
        production_app, base_url="https://api.howlix.wolvesgang.digital"
    ) as client:
        assert client.get("/health").status_code == 200
        assert client.get("/docs").status_code == 404
        assert client.get("/health", headers={"Host": "untrusted.example"}).status_code == 400
