"""Presigned URLs: AWS's published SigV4 example, limits, and the memory backend."""

from datetime import UTC, datetime
from urllib.parse import parse_qs, urlsplit

import pytest

from app.core.config import Settings
from app.core.errors import DomainError, ErrorCode
from app.integrations.storage import MemoryStorage, S3Storage, build_storage

NOW = datetime(2026, 11, 25, 12, 0, 0, tzinfo=UTC)


def storage_config(**overrides) -> Settings:
    fields = {
        "env": "test",
        "database_url": "postgresql://u:p@localhost/db",
        "secret_key": "k" * 40,
        "storage_backend": "s3",
        "storage_endpoint_url": "https://acct.r2.example.com",
        "storage_bucket": "uploads",
        "storage_access_key_id": "AKID",
        "storage_secret_access_key": "secret",
        "storage_region": "auto",
        "storage_max_upload_bytes": 1000,
    }
    return Settings(_env_file=None, **{**fields, **overrides})


def test_signature_matches_the_aws_documentation_example():
    # https://docs.aws.amazon.com/AmazonS3/latest/API/sigv4-query-string-auth.html
    config = storage_config(
        storage_endpoint_url="https://examplebucket.s3.amazonaws.com",
        storage_region="us-east-1",
        storage_access_key_id="AKIAIOSFODNN7EXAMPLE",
        storage_secret_access_key="wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
    )
    url = S3Storage(config).presign(
        "GET",
        "/test.txt",
        {},
        now=datetime(2013, 5, 24, 0, 0, 0, tzinfo=UTC),
        expires=86400,
    )
    assert parse_qs(urlsplit(url).query)["X-Amz-Signature"] == [
        "aeeed9bbccd4d02ee5c0109b86d86835f995330da4c265957d157751f604d404"
    ]


def test_upload_url_signs_the_declared_type_and_size():
    upload = S3Storage(storage_config()).presign_upload(
        "avatars/a%b.png", "image/png", 500, now=NOW
    )
    parts = urlsplit(upload.url)
    query = parse_qs(parts.query)
    assert parts.netloc == "acct.r2.example.com"
    assert parts.path == "/uploads/avatars/a%25b.png"
    assert query["X-Amz-SignedHeaders"] == ["content-length;content-type;host"]
    assert query["X-Amz-Expires"] == ["600"]
    assert upload.method == "PUT"
    assert upload.headers == {"Content-Type": "image/png", "Content-Length": "500"}
    # A different size or type changes the signature.
    other = S3Storage(storage_config()).presign_upload("avatars/a%b.png", "image/png", 501, now=NOW)
    assert parse_qs(urlsplit(other.url).query)["X-Amz-Signature"] != query["X-Amz-Signature"]


def test_download_url_is_a_signed_get():
    url = S3Storage(storage_config()).presign_download("docs/report.pdf", now=NOW)
    query = parse_qs(urlsplit(url).query)
    assert query["X-Amz-SignedHeaders"] == ["host"]
    assert query["X-Amz-Date"] == ["20261125T120000Z"]


@pytest.mark.parametrize(
    ("content_type", "size", "field"),
    [
        ("image/png", 1001, "max_bytes"),
        ("image/png", 0, "max_bytes"),
        ("text/html", 10, "content_type"),
        ("image/*", 10, "content_type"),
    ],
)
@pytest.mark.parametrize("backend", [S3Storage, MemoryStorage])
def test_uploads_outside_the_limits_are_rejected(backend, content_type, size, field):
    with pytest.raises(DomainError) as error:
        backend(storage_config()).presign_upload("a/b.png", content_type, size)
    assert error.value.code == ErrorCode.UPLOAD_NOT_ALLOWED
    assert field in error.value.details


def test_the_limit_itself_and_mixed_case_types_are_allowed():
    S3Storage(storage_config()).presign_upload("a.png", "IMAGE/PNG", 1000)


@pytest.mark.parametrize("key", ["", "/abs", "a/../b", "a//b", "./a", "a b", "x" * 513, "é"])
@pytest.mark.parametrize("backend", [S3Storage, MemoryStorage])
def test_unsafe_keys_are_rejected(backend, key):
    with pytest.raises(DomainError) as error:
        backend(storage_config()).presign_upload(key, "image/png", 10)
    assert error.value.details["key"] == "invalid"
    with pytest.raises(DomainError):
        backend(storage_config()).presign_download(key)


def test_memory_backend_records_uploads_and_builds_fake_urls():
    storage = MemoryStorage(storage_config())
    upload = storage.presign_upload("a/b.png", "image/png", 10)
    assert upload.url == "https://storage.test/a/b.png?upload"
    assert storage.uploads == [("a/b.png", "image/png", 10)]
    assert storage.presign_download("a/b.png") == "https://storage.test/a/b.png?download"


def test_build_storage_follows_the_setting():
    assert isinstance(build_storage(storage_config()), S3Storage)
    assert isinstance(build_storage(storage_config(storage_backend="memory")), MemoryStorage)
    assert build_storage(storage_config(storage_backend="disabled")) is None
