from __future__ import annotations

from collections.abc import Generator
import os
from pathlib import Path

os.environ.setdefault("HOWLIX_DATABASE_URL", "sqlite:///:memory:")

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.database import Base, get_db
from app.main import app
from app.rate_limit import upload_rate_limiter
from app.services.storage import (
    ObjectHead,
    StorageError,
    UploadedPart,
    get_storage_service,
)


class MockStorageService:
    bucket_name = "howlix-media-test"

    def __init__(self) -> None:
        self.upload_counter = 0
        self.parts: dict[str, list[UploadedPart]] = {}
        self.keys_by_upload: dict[str, str] = {}
        self.object_sizes: dict[str, int] = {}
        self.download_payloads: dict[str, bytes] = {}
        self.aborted: list[str] = []
        self.deleted: list[str] = []
        self.completed: list[str] = []
        self.uploaded_objects: list[str] = []
        self.fail_on: set[str] = set()
        self.forced_head_size: int | None = None

    def _fail(self, operation: str) -> None:
        if operation in self.fail_on:
            raise StorageError(f"Mock {operation} failure", "MockFailure")

    def create_multipart_upload(
        self, object_key: str, content_type: str, metadata: dict[str, str]
    ) -> str:
        self._fail("create")
        self.upload_counter += 1
        upload_id = f"upload-{self.upload_counter}"
        self.parts[upload_id] = []
        self.keys_by_upload[upload_id] = object_key
        return upload_id

    def generate_upload_part_url(
        self, object_key: str, upload_id: str, part_number: int, expires_in: int
    ) -> str:
        self._fail("sign")
        return f"https://r2.test/{object_key}?uploadId={upload_id}&partNumber={part_number}"

    def list_uploaded_parts(self, object_key: str, upload_id: str) -> list[UploadedPart]:
        self._fail("list")
        return list(self.parts.get(upload_id, []))

    def complete_multipart_upload(
        self, object_key: str, upload_id: str, parts: list[UploadedPart]
    ) -> None:
        self._fail("complete")
        self.completed.append(upload_id)
        self.object_sizes[object_key] = sum(part.size for part in parts)

    def abort_multipart_upload(self, object_key: str, upload_id: str) -> None:
        self._fail("abort")
        self.aborted.append(upload_id)

    def head_object(self, object_key: str) -> ObjectHead:
        self._fail("head")
        size = (
            self.forced_head_size
            if self.forced_head_size is not None
            else self.object_sizes.get(object_key, 0)
        )
        return ObjectHead(content_length=size, content_type="video/mp4", etag='"complete"')

    def generate_get_url(self, object_key: str, expires_in: int) -> str:
        self._fail("get-url")
        return f"https://r2.test/{object_key}?preview=1"

    def download_object(self, object_key: str, destination: Path) -> None:
        self._fail("download")
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(self.download_payloads.get(object_key, b"mock-video"))

    def upload_object(
        self, object_key: str, source: Path, content_type: str, metadata: dict[str, str]
    ) -> None:
        del content_type, metadata
        self._fail("upload-object")
        payload = source.read_bytes()
        self.uploaded_objects.append(object_key)
        self.download_payloads[object_key] = payload
        self.object_sizes[object_key] = len(payload)

    def delete_object(self, object_key: str) -> None:
        self._fail("delete")
        self.deleted.append(object_key)
        self.object_sizes.pop(object_key, None)


@pytest.fixture()
def testing_session_factory(tmp_path):
    database_path = tmp_path / "test.db"
    engine = create_engine(
        f"sqlite:///{database_path.as_posix()}",
        connect_args={"check_same_thread": False},
    )
    testing_session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    Base.metadata.create_all(bind=engine)

    yield testing_session

    Base.metadata.drop_all(bind=engine)
    engine.dispose()


@pytest.fixture()
def mock_storage() -> MockStorageService:
    return MockStorageService()


@pytest.fixture()
def client(
    testing_session_factory, mock_storage: MockStorageService
) -> Generator[TestClient, None, None]:

    def override_get_db() -> Generator[Session, None, None]:
        db = testing_session_factory()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_storage_service] = lambda: mock_storage
    upload_rate_limiter.reset()
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
    upload_rate_limiter.reset()

