from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Protocol

import boto3
from botocore.client import BaseClient
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError

from app.config import Settings, get_settings


class StorageError(RuntimeError):
    """A sanitized object-storage failure safe to surface through API logs."""

    def __init__(self, message: str, code: str | None = None) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class UploadedPart:
    part_number: int
    etag: str
    size: int


@dataclass(frozen=True)
class ObjectHead:
    content_length: int
    content_type: str | None
    etag: str | None


class StorageService(Protocol):
    bucket_name: str

    def create_multipart_upload(
        self, object_key: str, content_type: str, metadata: dict[str, str]
    ) -> str: ...

    def generate_upload_part_url(
        self, object_key: str, upload_id: str, part_number: int, expires_in: int
    ) -> str: ...

    def list_uploaded_parts(self, object_key: str, upload_id: str) -> list[UploadedPart]: ...

    def complete_multipart_upload(
        self, object_key: str, upload_id: str, parts: list[UploadedPart]
    ) -> None: ...

    def abort_multipart_upload(self, object_key: str, upload_id: str) -> None: ...

    def head_object(self, object_key: str) -> ObjectHead: ...

    def generate_get_url(self, object_key: str, expires_in: int) -> str: ...

    def download_object(self, object_key: str, destination: Path) -> None: ...

    def upload_object(
        self, object_key: str, source: Path, content_type: str, metadata: dict[str, str]
    ) -> None: ...

    def delete_object(self, object_key: str) -> None: ...


class R2StorageService:
    def __init__(self, settings: Settings, client: BaseClient | None = None) -> None:
        settings.require_r2()
        self.bucket_name = settings.r2_bucket_name
        self._client = client or boto3.client(
            "s3",
            endpoint_url=settings.r2_endpoint_url,
            aws_access_key_id=settings.r2_access_key_id,
            aws_secret_access_key=settings.r2_secret_access_key.get_secret_value()
            if settings.r2_secret_access_key
            else None,
            region_name=settings.r2_region,
            config=Config(
                signature_version="s3v4",
                retries={"max_attempts": 4, "mode": "standard"},
            ),
        )

    def _call(self, operation: str, **kwargs):
        try:
            return getattr(self._client, operation)(**kwargs)
        except ClientError as exc:
            error = exc.response.get("Error", {})
            code = error.get("Code", "unknown")
            raise StorageError(f"R2 {operation} failed ({code})", str(code)) from exc
        except BotoCoreError as exc:
            raise StorageError(f"R2 {operation} failed") from exc

    def create_multipart_upload(
        self, object_key: str, content_type: str, metadata: dict[str, str]
    ) -> str:
        response = self._call(
            "create_multipart_upload",
            Bucket=self.bucket_name,
            Key=object_key,
            ContentType=content_type,
            Metadata=metadata,
        )
        upload_id = response.get("UploadId")
        if not upload_id:
            raise StorageError("R2 did not return a multipart upload ID")
        return str(upload_id)

    def generate_upload_part_url(
        self, object_key: str, upload_id: str, part_number: int, expires_in: int
    ) -> str:
        try:
            return self._client.generate_presigned_url(
                "upload_part",
                Params={
                    "Bucket": self.bucket_name,
                    "Key": object_key,
                    "UploadId": upload_id,
                    "PartNumber": part_number,
                },
                ExpiresIn=expires_in,
                HttpMethod="PUT",
            )
        except (BotoCoreError, ClientError) as exc:
            raise StorageError("R2 upload-part URL signing failed") from exc

    def list_uploaded_parts(self, object_key: str, upload_id: str) -> list[UploadedPart]:
        parts: list[UploadedPart] = []
        marker = 0
        while True:
            response = self._call(
                "list_parts",
                Bucket=self.bucket_name,
                Key=object_key,
                UploadId=upload_id,
                PartNumberMarker=marker,
            )
            for part in response.get("Parts", []):
                parts.append(
                    UploadedPart(
                        part_number=int(part["PartNumber"]),
                        etag=str(part["ETag"]),
                        size=int(part["Size"]),
                    )
                )
            if not response.get("IsTruncated"):
                break
            marker = int(response.get("NextPartNumberMarker", 0))
        return sorted(parts, key=lambda item: item.part_number)

    def complete_multipart_upload(
        self, object_key: str, upload_id: str, parts: list[UploadedPart]
    ) -> None:
        self._call(
            "complete_multipart_upload",
            Bucket=self.bucket_name,
            Key=object_key,
            UploadId=upload_id,
            MultipartUpload={
                "Parts": [
                    {"PartNumber": part.part_number, "ETag": part.etag} for part in parts
                ]
            },
        )

    def abort_multipart_upload(self, object_key: str, upload_id: str) -> None:
        self._call(
            "abort_multipart_upload",
            Bucket=self.bucket_name,
            Key=object_key,
            UploadId=upload_id,
        )

    def head_object(self, object_key: str) -> ObjectHead:
        response = self._call("head_object", Bucket=self.bucket_name, Key=object_key)
        return ObjectHead(
            content_length=int(response["ContentLength"]),
            content_type=response.get("ContentType"),
            etag=response.get("ETag"),
        )

    def generate_get_url(self, object_key: str, expires_in: int) -> str:
        try:
            return self._client.generate_presigned_url(
                "get_object",
                Params={"Bucket": self.bucket_name, "Key": object_key},
                ExpiresIn=expires_in,
                HttpMethod="GET",
            )
        except (BotoCoreError, ClientError) as exc:
            raise StorageError("R2 download URL signing failed") from exc

    def download_object(self, object_key: str, destination: Path) -> None:
        destination = destination.resolve()
        destination.parent.mkdir(parents=True, exist_ok=True)
        try:
            with destination.open("wb") as output:
                self._client.download_fileobj(self.bucket_name, object_key, output)
        except (OSError, BotoCoreError, ClientError) as exc:
            raise StorageError("R2 object download failed") from exc

    def upload_object(
        self, object_key: str, source: Path, content_type: str, metadata: dict[str, str]
    ) -> None:
        source = source.resolve()
        try:
            with source.open("rb") as input_file:
                self._client.upload_fileobj(
                    input_file,
                    self.bucket_name,
                    object_key,
                    ExtraArgs={"ContentType": content_type, "Metadata": metadata},
                )
        except (OSError, BotoCoreError, ClientError) as exc:
            raise StorageError("R2 object upload failed") from exc

    def delete_object(self, object_key: str) -> None:
        self._call("delete_object", Bucket=self.bucket_name, Key=object_key)


@lru_cache
def get_storage_service() -> StorageService:
    return R2StorageService(get_settings())
