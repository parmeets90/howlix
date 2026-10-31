from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
import time
from typing import Callable, Protocol
from urllib.parse import parse_qs, urlsplit, urlunsplit


YOUTUBE_HOSTS = {"youtube.com", "www.youtube.com", "m.youtube.com", "youtu.be"}
VIDEO_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{11}$")


class YouTubeImportError(RuntimeError):
    """A safe, user-facing import failure."""


class YouTubeImportUnavailable(YouTubeImportError):
    pass


class YouTubeImportLimitError(YouTubeImportError):
    pass


class YouTubeImportCancelled(YouTubeImportError):
    pass


@dataclass(frozen=True)
class ValidatedYouTubeUrl:
    source_url: str
    canonical_url: str
    video_id: str


@dataclass(frozen=True)
class DownloadedYouTubeVideo:
    path: Path
    title: str
    channel_name: str | None
    channel_id: str | None
    published_at: str | None
    duration_seconds: float
    extractor: str


class YouTubeDownloader(Protocol):
    def download(
        self,
        validated: ValidatedYouTubeUrl,
        destination: Path,
        *,
        maximum_bytes: int,
        maximum_duration_seconds: int,
        timeout_seconds: int,
        progress: Callable[[int | None, int | None], None],
        cancelled: Callable[[], bool],
    ) -> DownloadedYouTubeVideo: ...


def validate_youtube_url(value: str) -> ValidatedYouTubeUrl:
    raw = value.strip()
    if not raw or len(raw) > 500:
        raise ValueError("Enter one valid YouTube video URL.")
    try:
        parsed = urlsplit(raw)
    except ValueError as exc:
        raise ValueError("Enter one valid YouTube video URL.") from exc
    if parsed.scheme.lower() not in {"http", "https"}:
        raise ValueError("Only http or https YouTube URLs are supported.")
    if parsed.username or parsed.password or parsed.port is not None:
        raise ValueError("YouTube URLs cannot contain credentials or custom ports.")
    host = (parsed.hostname or "").lower().rstrip(".")
    if host not in YOUTUBE_HOSTS:
        raise ValueError("Only youtube.com and youtu.be video URLs are supported.")
    query = parse_qs(parsed.query, keep_blank_values=True)
    if "list" in query:
        raise ValueError("Playlists are not supported. Paste a single video URL.")

    parts = [part for part in parsed.path.split("/") if part]
    video_id: str | None = None
    if host == "youtu.be" and len(parts) == 1:
        video_id = parts[0]
    elif host != "youtu.be" and parsed.path.rstrip("/") == "/watch":
        values = query.get("v", [])
        if len(values) == 1:
            video_id = values[0]
    elif host != "youtu.be" and len(parts) == 2 and parts[0] in {"shorts", "live"}:
        video_id = parts[1]
    if video_id is None or not VIDEO_ID_PATTERN.fullmatch(video_id):
        raise ValueError(
            "Use a single YouTube watch, Shorts, live, or youtu.be video URL."
        )
    canonical = urlunsplit(("https", "www.youtube.com", "/watch", f"v={video_id}", ""))
    return ValidatedYouTubeUrl(raw, canonical, video_id)


class YtDlpDownloader:
    def download(
        self,
        validated: ValidatedYouTubeUrl,
        destination: Path,
        *,
        maximum_bytes: int,
        maximum_duration_seconds: int,
        timeout_seconds: int,
        progress: Callable[[int | None, int | None], None],
        cancelled: Callable[[], bool],
    ) -> DownloadedYouTubeVideo:
        try:
            import yt_dlp
        except ImportError as exc:  # pragma: no cover - deployment/configuration failure
            raise YouTubeImportUnavailable(
                "YouTube importing is unavailable on this worker. Use manual upload instead."
            ) from exc

        destination = destination.resolve()
        destination.mkdir(parents=True, exist_ok=True)
        output_template = str(destination / "source.%(ext)s")
        started = time.monotonic()

        def hook(data: dict) -> None:
            if cancelled():
                raise YouTubeImportCancelled("YouTube import was cancelled.")
            if time.monotonic() - started > timeout_seconds:
                raise YouTubeImportLimitError(
                    "YouTube import timed out. Use manual upload instead."
                )
            downloaded = data.get("downloaded_bytes")
            total = data.get("total_bytes") or data.get("total_bytes_estimate")
            if isinstance(downloaded, int) and downloaded > maximum_bytes:
                raise YouTubeImportLimitError(
                    "The YouTube video exceeds this workspace's import size limit."
                )
            progress(downloaded if isinstance(downloaded, int) else None, total if isinstance(total, int) else None)

        options = {
            "allowed_extractors": ["youtube"],
            "format": "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
            "merge_output_format": "mp4",
            "outtmpl": output_template,
            "noplaylist": True,
            "playlist_items": "1",
            "max_filesize": maximum_bytes,
            "socket_timeout": min(30, timeout_seconds),
            "retries": 2,
            "fragment_retries": 2,
            "quiet": True,
            "no_warnings": True,
            "cachedir": False,
            "progress_hooks": [hook],
        }
        try:
            with yt_dlp.YoutubeDL(options) as downloader:
                info = downloader.extract_info(validated.canonical_url, download=False)
                if info.get("_type") == "playlist" or info.get("entries"):
                    raise YouTubeImportUnavailable(
                        "Playlists are not supported. Paste a single video URL."
                    )
                if str(info.get("id", "")) != validated.video_id:
                    raise YouTubeImportUnavailable("The resolved YouTube video did not match the request.")
                webpage = validate_youtube_url(str(info.get("webpage_url") or validated.canonical_url))
                if webpage.video_id != validated.video_id:
                    raise YouTubeImportUnavailable("The YouTube redirect target was rejected.")
                duration = float(info.get("duration") or 0)
                if duration <= 0:
                    raise YouTubeImportUnavailable("YouTube did not provide a usable video duration.")
                if duration > maximum_duration_seconds:
                    raise YouTubeImportLimitError(
                        "The YouTube video exceeds this workspace's duration limit."
                    )
                expected = info.get("filesize") or info.get("filesize_approx")
                if isinstance(expected, (int, float)) and expected > maximum_bytes:
                    raise YouTubeImportLimitError(
                        "The YouTube video exceeds this workspace's import size limit."
                    )
                info = downloader.extract_info(validated.canonical_url, download=True)
                candidates = [path for path in destination.glob("source.*") if path.is_file()]
                if not candidates:
                    requested = info.get("requested_downloads") or []
                    candidates = [Path(item["filepath"]) for item in requested if item.get("filepath")]
                if not candidates:
                    raise YouTubeImportUnavailable(
                        "YouTube did not provide a downloadable media file. Use manual upload instead."
                    )
                path = max(candidates, key=lambda item: item.stat().st_size).resolve()
                size = path.stat().st_size
                if size <= 0 or size > maximum_bytes:
                    raise YouTubeImportLimitError(
                        "The downloaded video exceeds this workspace's import size limit."
                    )
                return DownloadedYouTubeVideo(
                    path=path,
                    title=str(info.get("title") or f"YouTube {validated.video_id}")[:500],
                    channel_name=(str(info["channel"])[:255] if info.get("channel") else None),
                    channel_id=(str(info["channel_id"])[:128] if info.get("channel_id") else None),
                    published_at=(str(info["upload_date"])[:32] if info.get("upload_date") else None),
                    duration_seconds=float(info.get("duration") or duration),
                    extractor=str(info.get("extractor_key") or "Youtube")[:64],
                )
        except (YouTubeImportError, ValueError):
            raise
        except yt_dlp.utils.DownloadError as exc:
            message = str(exc).lower()
            if any(term in message for term in ("private video", "sign in", "age-restricted", "not available", "geo")):
                detail = "This YouTube video is private, restricted, or unavailable. Use a permitted manual upload instead."
            else:
                detail = "YouTube could not provide this video for download. Use manual upload instead."
            raise YouTubeImportUnavailable(detail) from exc
