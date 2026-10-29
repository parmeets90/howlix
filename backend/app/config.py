from __future__ import annotations

from functools import lru_cache
from pathlib import Path
import re
from typing import Literal

from pydantic import AliasChoices, Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=REPOSITORY_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    database_url: str = Field(validation_alias="HOWLIX_DATABASE_URL")
    database_schema: str = Field(default="howlix", validation_alias="HOWLIX_DATABASE_SCHEMA")
    environment: Literal["development", "test", "production"] = Field(
        default="development", validation_alias="HOWLIX_ENVIRONMENT"
    )
    public_app_url: str = Field(
        default="http://localhost:3000", validation_alias="HOWLIX_PUBLIC_APP_URL"
    )
    cors_origins_value: str = Field(
        default="http://localhost:3000,https://howlix.wolvesgang.digital",
        validation_alias="HOWLIX_CORS_ORIGINS",
    )
    allowed_hosts_value: str = Field(
        default="localhost,127.0.0.1,testserver,api.howlix.wolvesgang.digital",
        validation_alias="HOWLIX_ALLOWED_HOSTS",
    )

    r2_account_id: str | None = Field(default=None, validation_alias="R2_ACCOUNT_ID")
    r2_access_key_id: str | None = Field(default=None, validation_alias="R2_ACCESS_KEY_ID")
    r2_secret_access_key: SecretStr | None = Field(
        default=None, validation_alias="R2_SECRET_ACCESS_KEY"
    )
    r2_bucket_name: str = Field(default="howlix-media", validation_alias="R2_BUCKET_NAME")
    r2_endpoint_url: str | None = Field(default=None, validation_alias="R2_ENDPOINT_URL")
    r2_region: str = Field(default="auto", validation_alias="R2_REGION")

    max_upload_size_mb: int = Field(default=1024, ge=1, validation_alias="MAX_UPLOAD_SIZE_MB")
    max_video_duration_seconds: int = Field(
        default=1800, ge=1, validation_alias="MAX_VIDEO_DURATION_SECONDS"
    )
    max_concurrent_jobs: int = Field(default=1, ge=1, le=1, validation_alias="MAX_CONCURRENT_JOBS")
    upload_part_size_mb: int = Field(default=16, ge=5, validation_alias="UPLOAD_PART_SIZE_MB")
    upload_parallel_parts: int = Field(default=2, ge=1, le=8, validation_alias="UPLOAD_PARALLEL_PARTS")
    signed_url_expiry_seconds: int = Field(
        default=900, ge=60, le=604800, validation_alias="SIGNED_URL_EXPIRY_SECONDS"
    )
    upload_session_expiry_hours: int = Field(
        default=24, ge=1, le=168, validation_alias="UPLOAD_SESSION_EXPIRY_HOURS"
    )
    max_project_storage_mb: int = Field(
        default=10240, ge=1, validation_alias="MAX_PROJECT_STORAGE_MB"
    )
    upload_init_rate_limit_per_minute: int = Field(
        default=10, ge=1, validation_alias="UPLOAD_INIT_RATE_LIMIT_PER_MINUTE"
    )
    upload_sign_rate_limit_per_minute: int = Field(
        default=120, ge=1, validation_alias="UPLOAD_SIGN_RATE_LIMIT_PER_MINUTE"
    )

    ffprobe_path: str = Field(default="ffprobe", validation_alias="FFPROBE_PATH")
    ffmpeg_path: str = Field(default="ffmpeg", validation_alias="FFMPEG_PATH")
    ffprobe_timeout_seconds: int = Field(
        default=60, ge=5, le=600, validation_alias="FFPROBE_TIMEOUT_SECONDS"
    )
    worker_poll_seconds: float = Field(default=2.0, ge=0.1, validation_alias="WORKER_POLL_SECONDS")
    job_lease_seconds: int = Field(default=300, ge=30, validation_alias="JOB_LEASE_SECONDS")
    processing_temp_dir: Path | None = Field(default=None, validation_alias="PROCESSING_TEMP_DIR")
    delete_invalid_media: bool = Field(default=True, validation_alias="DELETE_INVALID_MEDIA")
    transcription_provider: Literal["groq", "faster-whisper"] = Field(
        default="groq", validation_alias="TRANSCRIPTION_PROVIDER"
    )
    groq_api_key: SecretStr | None = Field(default=None, validation_alias="GROQ_API_KEY")
    groq_transcription_model: str = Field(
        default="whisper-large-v3-turbo", validation_alias="GROQ_TRANSCRIPTION_MODEL"
    )
    faster_whisper_model: str = Field(
        default="base", validation_alias="FASTER_WHISPER_MODEL"
    )
    transcription_chunk_seconds: int = Field(
        default=600, ge=30, le=1200, validation_alias="TRANSCRIPTION_CHUNK_SECONDS"
    )
    transcription_chunk_overlap_seconds: float = Field(
        default=1.0, ge=0, le=10, validation_alias="TRANSCRIPTION_CHUNK_OVERLAP_SECONDS"
    )
    transcription_max_chunk_mb: int = Field(
        default=24, ge=1, le=24, validation_alias="TRANSCRIPTION_MAX_CHUNK_MB"
    )
    transcription_subprocess_timeout_seconds: int = Field(
        default=300, ge=30, le=1800, validation_alias="TRANSCRIPTION_SUBPROCESS_TIMEOUT_SECONDS"
    )
    transcription_api_max_retries: int = Field(
        default=3, ge=0, le=6, validation_alias="TRANSCRIPTION_API_MAX_RETRIES"
    )
    transcription_retry_base_seconds: int = Field(
        default=5, ge=0, le=300, validation_alias="TRANSCRIPTION_RETRY_BASE_SECONDS"
    )
    run_groq_integration_tests: bool = Field(
        default=False, validation_alias="RUN_GROQ_INTEGRATION_TESTS"
    )
    groq_integration_audio_path: Path | None = Field(
        default=None, validation_alias="GROQ_INTEGRATION_AUDIO_PATH"
    )
    run_r2_integration_tests: bool = Field(
        default=False,
        validation_alias=AliasChoices("RUN_R2_INTEGRATION_TESTS", "HOWLIX_RUN_R2_INTEGRATION_TESTS"),
    )

    @field_validator("database_url")
    @classmethod
    def normalize_database_url(cls, value: str) -> str:
        if value.startswith("postgres://"):
            return value.replace("postgres://", "postgresql+psycopg://", 1)
        if value.startswith("postgresql://"):
            return value.replace("postgresql://", "postgresql+psycopg://", 1)
        return value

    @field_validator("database_schema")
    @classmethod
    def validate_database_schema(cls, value: str) -> str:
        normalized = value.strip().lower()
        if not re.fullmatch(r"[a-z_][a-z0-9_]{0,62}", normalized):
            raise ValueError("HOWLIX_DATABASE_SCHEMA must be a safe PostgreSQL identifier.")
        return normalized

    @field_validator("public_app_url")
    @classmethod
    def normalize_public_app_url(cls, value: str) -> str:
        return value.rstrip("/")

    @field_validator("processing_temp_dir", "groq_integration_audio_path", mode="before")
    @classmethod
    def parse_optional_path(cls, value: object) -> object:
        return None if value == "" else value

    @model_validator(mode="after")
    def derive_r2_endpoint(self) -> "Settings":
        if not self.r2_endpoint_url and self.r2_account_id:
            self.r2_endpoint_url = f"https://{self.r2_account_id}.r2.cloudflarestorage.com"
        if self.transcription_chunk_overlap_seconds >= self.transcription_chunk_seconds:
            raise ValueError("Transcription chunk overlap must be shorter than each chunk.")
        return self

    @property
    def upload_part_size_bytes(self) -> int:
        return self.upload_part_size_mb * 1024 * 1024

    @property
    def cors_origins(self) -> tuple[str, ...]:
        return tuple(
            origin.strip() for origin in self.cors_origins_value.split(",") if origin.strip()
        )

    @property
    def allowed_hosts(self) -> tuple[str, ...]:
        return tuple(host.strip() for host in self.allowed_hosts_value.split(",") if host.strip())

    @property
    def max_upload_size_bytes(self) -> int:
        return self.max_upload_size_mb * 1024 * 1024

    @property
    def max_project_storage_bytes(self) -> int:
        return self.max_project_storage_mb * 1024 * 1024

    @property
    def transcription_max_chunk_bytes(self) -> int:
        return self.transcription_max_chunk_mb * 1024 * 1024

    def require_r2(self) -> "Settings":
        missing = [
            name
            for name, value in (
                ("R2_ACCOUNT_ID", self.r2_account_id),
                ("R2_ACCESS_KEY_ID", self.r2_access_key_id),
                ("R2_SECRET_ACCESS_KEY", self.r2_secret_access_key),
                ("R2_ENDPOINT_URL", self.r2_endpoint_url),
            )
            if not value
        ]
        if missing:
            raise RuntimeError(f"Missing required R2 configuration: {', '.join(missing)}")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()

