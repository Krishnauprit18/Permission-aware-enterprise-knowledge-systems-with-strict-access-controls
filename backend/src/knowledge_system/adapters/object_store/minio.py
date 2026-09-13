"""MinIO adapter for immutable raw source snapshots."""

from __future__ import annotations

from hashlib import sha256
from io import BytesIO

from minio import Minio
from minio.error import S3Error

from knowledge_system.application.ingestion import (
    PermanentIngestionError,
    TransientIngestionError,
)
from knowledge_system.application.ports.ingestion import RawObjectStore
from knowledge_system.domain.ingestion import RawObjectRef, RawSnapshot


class MinioRawObjectStore(RawObjectStore):
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
