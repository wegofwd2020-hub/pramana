"""Object-storage seam for generated media (video assets).

The video generation service (:mod:`pramana.services.video_generation`) owns
**persisting** the asset (ADR-026 D2 — the wegofwd-video package never stores).
This module is the thin storage port it calls: a ``VideoUploader`` callable
``(data, key) -> stored_key`` plus a deterministic key helper and an S3-backed
factory. Injecting the uploader keeps the generation service fully testable
without boto3 / network (tests pass an in-memory uploader).
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING
from uuid import UUID

from pramana.exceptions import ObjectStorageError

if TYPE_CHECKING:
    from pramana.config import Settings

# (bytes, key) -> the stored key (echoed back so the caller records exactly what
# landed in storage).
VideoUploader = Callable[[bytes, str], str]


def video_asset_key(*, course_id: UUID, draft_id: UUID) -> str:
    """Deterministic S3 key for a draft's video asset.

    Draft-scoped so re-generating a draft overwrites rather than orphaning; the
    key is copied onto the immutable course version verbatim at publish.
    """
    return f"video/{course_id}/{draft_id}.mp4"


def build_s3_video_uploader(settings: Settings) -> VideoUploader:
    """Return a ``VideoUploader`` that puts bytes into the configured video bucket.

    boto3 is imported lazily so the dependency is only required by deployments that
    actually upload (mirrors the optional-SDK pattern in wegofwd-llm / wegofwd-video).
    """

    def _upload(data: bytes, key: str) -> str:
        try:
            import boto3  # type: ignore
        except ImportError as exc:  # pragma: no cover - depends on deploy extras
            raise ObjectStorageError(
                "video upload requires boto3 (install the storage extra)"
            ) from exc
        client = boto3.client(
            "s3",
            region_name=settings.aws_region,
            aws_access_key_id=settings.aws_access_key_id or None,
            aws_secret_access_key=(settings.aws_secret_access_key.get_secret_value() or None),
        )
        try:
            client.put_object(
                Bucket=settings.s3_bucket_video,
                Key=key,
                Body=data,
                ContentType="video/mp4",
            )
        except Exception:  # pragma: no cover - network/credentials
            # Never chain — an S3 error repr can echo request details / credentials.
            raise ObjectStorageError("failed to upload video asset") from None
        return key

    return _upload
