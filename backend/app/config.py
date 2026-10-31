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

    supabase_url: str | None = Field(default=None, validation_alias="SUPABASE_URL")
    supabase_publishable_key: SecretStr | None = Field(
        default=None,
        validation_alias=AliasChoices("SUPABASE_PUBLISHABLE_KEY", "SUPABASE_ANON_KEY"),
    )
    supabase_jwt_audience: str = Field(
        default="authenticated", validation_alias="SUPABASE_JWT_AUDIENCE"
    )
    supabase_jwt_issuer: str | None = Field(
        default=None, validation_alias="SUPABASE_JWT_ISSUER"
    )
    supabase_jwks_url: str | None = Field(default=None, validation_alias="SUPABASE_JWKS_URL")
    supabase_jwt_verification_mode: Literal["jwks", "auth-server"] = Field(
        default="jwks", validation_alias="SUPABASE_JWT_VERIFICATION_MODE"
    )
    auth_http_timeout_seconds: int = Field(
        default=10, ge=2, le=30, validation_alias="AUTH_HTTP_TIMEOUT_SECONDS"
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
    beta_max_projects_per_user: int = Field(
        default=10, ge=1, le=1000, validation_alias="BETA_MAX_PROJECTS_PER_USER"
    )
    beta_monthly_transcription_minutes: int = Field(
        default=300, ge=0, validation_alias="BETA_MONTHLY_TRANSCRIPTION_MINUTES"
    )
    beta_monthly_analysis_jobs: int = Field(
        default=100, ge=0, validation_alias="BETA_MONTHLY_ANALYSIS_JOBS"
    )
    beta_max_concurrent_renders: int = Field(
        default=1, ge=1, le=4, validation_alias="BETA_MAX_CONCURRENT_RENDERS"
    )
    beta_max_stored_media_mb: int = Field(
        default=10240, ge=1, validation_alias="BETA_MAX_STORED_MEDIA_MB"
    )
    upload_init_rate_limit_per_minute: int = Field(
        default=10, ge=1, validation_alias="UPLOAD_INIT_RATE_LIMIT_PER_MINUTE"
    )
    upload_sign_rate_limit_per_minute: int = Field(
        default=120, ge=1, validation_alias="UPLOAD_SIGN_RATE_LIMIT_PER_MINUTE"
    )
    youtube_import_enabled: bool = Field(
        default=True, validation_alias="YOUTUBE_IMPORT_ENABLED"
    )
    youtube_import_max_bytes: int = Field(
        default=1_073_741_824, ge=1_048_576, validation_alias="YOUTUBE_IMPORT_MAX_BYTES"
    )
    youtube_import_timeout_seconds: int = Field(
        default=900, ge=30, le=7200, validation_alias="YOUTUBE_IMPORT_TIMEOUT_SECONDS"
    )
    youtube_import_max_concurrent_per_user: int = Field(
        default=1, ge=1, le=4, validation_alias="YOUTUBE_IMPORT_MAX_CONCURRENT_PER_USER"
    )
    youtube_import_max_retries: int = Field(
        default=3, ge=1, le=6, validation_alias="YOUTUBE_IMPORT_MAX_RETRIES"
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
    moment_analysis_provider: Literal["groq", "fixture"] = Field(
        default="groq", validation_alias="MOMENT_ANALYSIS_PROVIDER"
    )
    groq_moment_model: str = Field(
        default="openai/gpt-oss-20b", validation_alias="GROQ_MOMENT_MODEL"
    )
    moment_min_duration_seconds: int = Field(
        default=20, ge=5, le=90, validation_alias="MOMENT_MIN_DURATION_SECONDS"
    )
    moment_max_duration_seconds: int = Field(
        default=90, ge=20, le=180, validation_alias="MOMENT_MAX_DURATION_SECONDS"
    )
    moment_target_duration_seconds: int = Field(
        default=55, ge=10, le=120, validation_alias="MOMENT_TARGET_DURATION_SECONDS"
    )
    moment_max_candidates: int = Field(
        default=24, ge=1, le=100, validation_alias="MOMENT_MAX_CANDIDATES"
    )
    moment_max_recommendations: int = Field(
        default=10, ge=1, le=20, validation_alias="MOMENT_MAX_RECOMMENDATIONS"
    )
    moment_min_editorial_score: float = Field(
        default=55.0, ge=0, le=100, validation_alias="MOMENT_MIN_EDITORIAL_SCORE"
    )
    moment_max_input_chars: int = Field(
        default=80_000, ge=1000, le=500_000, validation_alias="MOMENT_MAX_INPUT_CHARS"
    )
    moment_batch_size: int = Field(
        default=12, ge=1, le=30, validation_alias="MOMENT_BATCH_SIZE"
    )
    moment_max_api_requests: int = Field(
        default=3, ge=1, le=10, validation_alias="MOMENT_MAX_API_REQUESTS"
    )
    moment_max_output_tokens: int = Field(
        default=6000, ge=500, le=16000, validation_alias="MOMENT_MAX_OUTPUT_TOKENS"
    )
    moment_api_max_retries: int = Field(
        default=3, ge=0, le=6, validation_alias="MOMENT_API_MAX_RETRIES"
    )
    moment_retry_base_seconds: int = Field(
        default=5, ge=0, le=300, validation_alias="MOMENT_RETRY_BASE_SECONDS"
    )
    moment_analysis_version: str = Field(
        default="1.0", min_length=1, max_length=32, validation_alias="MOMENT_ANALYSIS_VERSION"
    )
    moment_prompt_version: str = Field(
        default="m4-v1", min_length=1, max_length=32, validation_alias="MOMENT_PROMPT_VERSION"
    )
    render_timeout_seconds: int = Field(
        default=1200, ge=60, le=7200, validation_alias="RENDER_TIMEOUT_SECONDS"
    )
    render_cpu_threads: int = Field(
        default=2, ge=1, le=8, validation_alias="RENDER_CPU_THREADS"
    )
    render_prefer_nvenc: bool = Field(
        default=True, validation_alias="RENDER_PREFER_NVENC"
    )
    render_fps_cap: float = Field(
        default=30.0, ge=15, le=60, validation_alias="RENDER_FPS_CAP"
    )
    render_max_output_mb: int = Field(
        default=500, ge=10, le=2048, validation_alias="RENDER_MAX_OUTPUT_MB"
    )
    render_retry_base_seconds: int = Field(
        default=5, ge=0, le=300, validation_alias="RENDER_RETRY_BASE_SECONDS"
    )
    face_sample_frequency_hz: float = Field(
        default=0.5, ge=0.1, le=2.0, validation_alias="FACE_SAMPLE_FREQUENCY_HZ"
    )
    face_max_samples: int = Field(
        default=60, ge=1, le=300, validation_alias="FACE_MAX_SAMPLES"
    )
    caption_fonts_dir: Path | None = Field(
        default=Path("C:/Windows/Fonts"), validation_alias="CAPTION_FONTS_DIR"
    )
    caption_latin_font: str = Field(
        default="Noto Sans", min_length=1, max_length=128, validation_alias="CAPTION_LATIN_FONT"
    )
    caption_complex_font: str = Field(
        default="Nirmala UI", min_length=1, max_length=128, validation_alias="CAPTION_COMPLEX_FONT"
    )
    run_groq_integration_tests: bool = Field(
        default=False, validation_alias="RUN_GROQ_INTEGRATION_TESTS"
    )
    run_moment_groq_integration_tests: bool = Field(
        default=False, validation_alias="RUN_MOMENT_GROQ_INTEGRATION_TESTS"
    )
    run_render_integration_tests: bool = Field(
        default=False, validation_alias="RUN_RENDER_INTEGRATION_TESTS"
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

    @field_validator(
        "processing_temp_dir", "groq_integration_audio_path", "caption_fonts_dir", mode="before"
    )
    @classmethod
    def parse_optional_path(cls, value: object) -> object:
        if value == "":
            return None
        return value

    @model_validator(mode="after")
    def derive_r2_endpoint(self) -> "Settings":
        if not self.r2_endpoint_url and self.r2_account_id:
            self.r2_endpoint_url = f"https://{self.r2_account_id}.r2.cloudflarestorage.com"
        if self.supabase_url:
            self.supabase_url = self.supabase_url.rstrip("/")
            auth_issuer = f"{self.supabase_url}/auth/v1"
            self.supabase_jwt_issuer = self.supabase_jwt_issuer or auth_issuer
            self.supabase_jwks_url = (
                self.supabase_jwks_url or f"{auth_issuer}/.well-known/jwks.json"
            )
        if self.transcription_chunk_overlap_seconds >= self.transcription_chunk_seconds:
            raise ValueError("Transcription chunk overlap must be shorter than each chunk.")
        if self.moment_min_duration_seconds > self.moment_target_duration_seconds:
            raise ValueError("Moment target duration must be at least the minimum duration.")
        if self.moment_target_duration_seconds > self.moment_max_duration_seconds:
            raise ValueError("Moment target duration must not exceed the maximum duration.")
        if self.moment_max_recommendations > self.moment_max_candidates:
            raise ValueError("Moment recommendations cannot exceed generated candidates.")
        if self.moment_batch_size * self.moment_max_api_requests < self.moment_max_candidates:
            raise ValueError("Moment API batch capacity must cover the configured candidate limit.")
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

    @property
    def render_max_output_bytes(self) -> int:
        return self.render_max_output_mb * 1024 * 1024

    @property
    def beta_max_stored_media_bytes(self) -> int:
        return self.beta_max_stored_media_mb * 1024 * 1024

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

