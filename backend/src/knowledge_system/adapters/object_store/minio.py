"""MinIO adapter for immutable raw source snapshots."""

from __future__ import annotations

from hashlib import sha256
from io import BytesIO
from urllib.parse import urlparse

from minio import Minio
from minio.error import S3Error

from knowledge_system.application.ingestion import (
    PermanentIngestionError,
    TransientIngestionError,
)
from knowledge_system.application.ports.ingestion import RawObjectReader, RawObjectStore
from knowledge_system.domain.ingestion import RawObjectRef, RawSnapshot


class MinioRawObjectStore(RawObjectStore, RawObjectReader):
    """Store raw bytes with source provenance in MinIO user metadata."""

    def __init__(
        self,
        endpoint: str,
        access_key: str,
        secret_key: str,
        *,
        bucket: str = "raw",
        secure: bool = False,
    ) -> None:
        host = endpoint.removeprefix("http://").removeprefix("https://").rstrip("/")
        self._client = Minio(
            host,
            access_key=access_key,
            secret_key=secret_key,
            secure=secure,
        )
        self._bucket = bucket

    def put(self, snapshot: RawSnapshot) -> RawObjectRef:
        key = str(snapshot.object_key)
        if key.startswith("/") or ".." in key.split("/"):
            raise PermanentIngestionError("raw object key is unsafe")
        try:
            self._client.put_object(
                self._bucket,
                key,
                BytesIO(snapshot.payload),
                len(snapshot.payload),
                content_type=snapshot.content_type,
                metadata=dict(snapshot.metadata),
            )
        except S3Error as exc:
            if exc.code in {
                "AccessDenied",
                "InvalidArgument",
                "InvalidBucketName",
                "NoSuchBucket",
            }:
                raise PermanentIngestionError(
                    "raw object store rejected request"
                ) from exc
            raise TransientIngestionError("raw object store unavailable") from exc
        except OSError as exc:
            raise TransientIngestionError("raw object store unavailable") from exc
        return RawObjectRef(
            object_uri=f"minio://{self._bucket}/{key}",
            content_hash=f"sha256:{sha256(snapshot.payload).hexdigest()}",
            size_bytes=len(snapshot.payload),
        )

    def get(
        self,
        object_uri: str,
        *,
        expected_content_hash: str,
        max_bytes: int,
    ) -> bytes:
        """Read one verified primary snapshot without logging its contents."""

        if max_bytes < 1:
            raise ValueError("raw object maximum size must be positive")
        bucket, key = self._parse_uri(object_uri)
        if bucket != self._bucket:
            raise PermanentIngestionError("raw object bucket is not allowed")
        try:
            response = self._client.get_object(bucket, key)
            try:
                payload = response.read(max_bytes + 1)
            finally:
                response.close()
                response.release_conn()
        except S3Error as exc:
            if exc.code in {
                "AccessDenied",
                "InvalidBucketName",
                "NoSuchBucket",
                "NoSuchKey",
            }:
                raise PermanentIngestionError("raw object store rejected read") from exc
            raise TransientIngestionError("raw object store unavailable") from exc
        except OSError as exc:
            raise TransientIngestionError("raw object store unavailable") from exc
        if not payload or len(payload) > max_bytes:
            raise PermanentIngestionError("raw object size verification failed")
        actual_hash = f"sha256:{sha256(payload).hexdigest()}"
        if actual_hash != expected_content_hash:
            raise PermanentIngestionError("raw object hash verification failed")
        return payload

    @staticmethod
    def _parse_uri(object_uri: str) -> tuple[str, str]:
        parsed = urlparse(object_uri)
        if parsed.scheme != "minio" or not parsed.netloc or not parsed.path:
            raise PermanentIngestionError("raw object URI is invalid")
        key = parsed.path.lstrip("/")
        if not key or key.startswith("/") or ".." in key.split("/"):
            raise PermanentIngestionError("raw object key is unsafe")
        return parsed.netloc, key
