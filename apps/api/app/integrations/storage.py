"""S3-compatible object storage: presigned upload and download URLs.

Signature Version 4 query-string signing is implemented here with the standard library
(hmac/hashlib), so no AWS SDK is needed for two operations. Path-style addressing
(``https://endpoint/bucket/key``) works with AWS S3, Cloudflare R2 and MinIO. An upload
URL signs the exact Content-Type and Content-Length the client declared, so the object
store rejects a request with a different type or size; the API rejects anything outside
the configured limits before signing.
"""

import hashlib
import hmac
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Protocol
from urllib.parse import quote, urlsplit

from app.core.config import Settings, secret_value
from app.core.errors import DomainError, ErrorCode

KEY_MAX_LENGTH = 512


@dataclass(frozen=True)
class PresignedUpload:
    url: str
    method: str
    # The client must send exactly these headers.
    headers: dict[str, str]
    expires_in: int


class ObjectStorage(Protocol):
    def presign_upload(
        self, key: str, content_type: str, size: int, *, now: datetime | None = None
    ) -> PresignedUpload: ...

    def presign_download(self, key: str, *, now: datetime | None = None) -> str: ...


def validate_upload(config: Settings, key: str, content_type: str, size: int) -> None:
    """Raise ``upload_not_allowed`` unless the type is allowed and 0 < size <= the limit."""
    reasons: dict[str, object] = {}
    if content_type.lower() not in config.storage_allowed_content_types:
        reasons["content_type"] = config.storage_allowed_content_types
    if not 0 < size <= config.storage_max_upload_bytes:
        reasons["max_bytes"] = config.storage_max_upload_bytes
    if not valid_key(key):
        reasons["key"] = "invalid"
    if reasons:
        raise DomainError(ErrorCode.UPLOAD_NOT_ALLOWED, details=reasons)


def valid_key(key: str) -> bool:
    return (
        0 < len(key) <= KEY_MAX_LENGTH
        and not key.startswith("/")
        and all(part not in {"", ".", ".."} for part in key.split("/"))
        and all(32 < ord(char) < 127 for char in key)
    )


@dataclass
class MemoryStorage:
    """Tests: validates like the real backend and returns predictable fake URLs."""

    config: Settings
    uploads: list[tuple[str, str, int]] = field(default_factory=list)

    def presign_upload(
        self, key: str, content_type: str, size: int, *, now: datetime | None = None
    ) -> PresignedUpload:
        validate_upload(self.config, key, content_type, size)
        self.uploads.append((key, content_type, size))
        return PresignedUpload(
            f"https://storage.test/{quote(key)}?upload",
            "PUT",
            {"Content-Type": content_type, "Content-Length": str(size)},
            self.config.storage_url_expire_seconds,
        )

    def presign_download(self, key: str, *, now: datetime | None = None) -> str:
        if not valid_key(key):
            raise DomainError(ErrorCode.UPLOAD_NOT_ALLOWED, details={"key": "invalid"})
        return f"https://storage.test/{quote(key)}?download"


def _hmac(key: bytes, message: str) -> bytes:
    return hmac.new(key, message.encode(), hashlib.sha256).digest()


def encode(value: str) -> str:
    return quote(value, safe="-_.~")


class S3Storage:
    def __init__(self, config: Settings) -> None:
        assert config.storage_endpoint_url is not None  # validated by Settings
        self.config = config
        parts = urlsplit(str(config.storage_endpoint_url))
        self.scheme = parts.scheme
        self.host = parts.netloc
        self.prefix = parts.path.rstrip("/")

    def object_path(self, key: str) -> str:
        return f"{self.prefix}/{self.config.storage_bucket}/{key}"

    def presign(
        self,
        method: str,
        path: str,
        signed_headers: dict[str, str],
        *,
        now: datetime | None = None,
        expires: int | None = None,
    ) -> str:
        config = self.config
        now = now or datetime.now(UTC)
        stamp = now.strftime("%Y%m%dT%H%M%SZ")
        day = stamp[:8]
        scope = f"{day}/{config.storage_region}/s3/aws4_request"
        headers = {"host": self.host} | {k.lower(): v.strip() for k, v in signed_headers.items()}
        names = ";".join(sorted(headers))
        query = {
            "X-Amz-Algorithm": "AWS4-HMAC-SHA256",
            "X-Amz-Credential": f"{config.storage_access_key_id}/{scope}",
            "X-Amz-Date": stamp,
            "X-Amz-Expires": str(expires or config.storage_url_expire_seconds),
            "X-Amz-SignedHeaders": names,
        }
        canonical_query = "&".join(f"{encode(k)}={encode(v)}" for k, v in sorted(query.items()))
        canonical_path = quote(path, safe="/-_.~")
        canonical_headers = "".join(f"{k}:{headers[k]}\n" for k in sorted(headers))
        request = "\n".join(
            [method, canonical_path, canonical_query, canonical_headers, names, "UNSIGNED-PAYLOAD"]
        )
        to_sign = "\n".join(
            ["AWS4-HMAC-SHA256", stamp, scope, hashlib.sha256(request.encode()).hexdigest()]
        )
        secret = secret_value(config.storage_secret_access_key)
        signing_key = _hmac(
            _hmac(_hmac(_hmac(f"AWS4{secret}".encode(), day), config.storage_region), "s3"),
            "aws4_request",
        )
        signature = hmac.new(signing_key, to_sign.encode(), hashlib.sha256).hexdigest()
        return f"{self.scheme}://{self.host}{canonical_path}?{canonical_query}&X-Amz-Signature={signature}"

    def presign_upload(
        self, key: str, content_type: str, size: int, *, now: datetime | None = None
    ) -> PresignedUpload:
        validate_upload(self.config, key, content_type, size)
        headers = {"Content-Type": content_type, "Content-Length": str(size)}
        url = self.presign("PUT", self.object_path(key), headers, now=now)
        return PresignedUpload(url, "PUT", headers, self.config.storage_url_expire_seconds)

    def presign_download(self, key: str, *, now: datetime | None = None) -> str:
        if not valid_key(key):
            raise DomainError(ErrorCode.UPLOAD_NOT_ALLOWED, details={"key": "invalid"})
        return self.presign("GET", self.object_path(key), {}, now=now)


def build_storage(config: Settings) -> ObjectStorage | None:
    if config.storage_backend == "s3":
        return S3Storage(config)
    if config.storage_backend == "memory":
        return MemoryStorage(config)
    return None
