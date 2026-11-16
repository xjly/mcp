import asyncio
from unittest.mock import patch
from urllib.parse import parse_qs, unquote, urlsplit

import pytest
from minio.error import S3Error
from urllib3.response import HTTPResponse

from knowledge_mcp.downloads import DownloadError, DownloadSettings, DownloadStorage


BUCKET = "ref-kb-water"
SETTINGS = DownloadSettings(
    url="https://downloads.example.test:9000",
    access_key="fixture-access-key",
    secret_key="fixture-secret-key",
)


@pytest.mark.parametrize(
    "stored_path",
    [
        f"http://internal.invalid:9000/{BUCKET}/archive/水务%20图#1?.pdf",
        f"minio://{BUCKET}/archive/水务%20图#1?.pdf",
        f"s3://{BUCKET}/archive/水务%20图#1?.pdf",
    ],
)
def test_download_signs_exact_raw_key_for_configured_browser_origin(stored_path):
    storage = DownloadStorage(SETTINGS, bucket=BUCKET)
    with patch("knowledge_mcp.downloads.Minio.stat_object") as stat:
        url = asyncio.run(storage.download_url(stored_path, "水务手册.pdf"))

    stat.assert_called_once_with(BUCKET, "archive/水务%20图#1?.pdf")
    parsed = urlsplit(url)
    assert parsed.scheme == "https"
    assert parsed.netloc == "downloads.example.test:9000"
    assert unquote(parsed.path) == f"/{BUCKET}/archive/水务%20图#1?.pdf"
    query = parse_qs(parsed.query)
    assert query["X-Amz-Expires"] == ["300"]
    assert query["X-Amz-Algorithm"] == ["AWS4-HMAC-SHA256"]
    assert query["X-Amz-Signature"][0]
    disposition = query["response-content-disposition"][0]
    assert unquote(disposition) == "attachment; filename*=UTF-8''水务手册.pdf"
    assert SETTINGS.secret_key not in url


@pytest.mark.parametrize(
    "stored_path",
    [
        "/app/saves/secret.zip",
        "s3://ref-kb-private/file.pdf",
        "https://upload.example.test/ref-kb-private/file.pdf",
        "https://upload.example.test/ref-kb-water/",
        "https://upload.example.test/ref-kb-water/../other.pdf",
        "https://upload.example.test/ref-kb-water/dir/./other.pdf",
        "https://upload.example.test/ref-kb-water/dir\\other.pdf",
        "https://upload.example.test/ref-kb-water/dir\x00file.pdf",
    ],
)
def test_download_rejects_invalid_or_unscoped_keys_before_storage_access(stored_path):
    storage = DownloadStorage(SETTINGS, bucket=BUCKET)
    with (
        patch("knowledge_mcp.downloads.Minio.stat_object") as stat,
        pytest.raises(DownloadError),
    ):
        asyncio.run(storage.download_url(stored_path, "file.pdf"))
    stat.assert_not_called()


@pytest.mark.parametrize(
    "invalid_url",
    [
        "https://name:secret@downloads.example.test",
        "https://downloads.example.test/prefix",
        "https://downloads.example.test?token=secret",
        "https://downloads.example.test#token",
        "https://downloads.example.test:invalid",
    ],
)
def test_download_checks_minio_origin_without_exposing_bad_config(invalid_url):
    settings = DownloadSettings(invalid_url, SETTINGS.access_key, SETTINGS.secret_key)
    with (
        patch("knowledge_mcp.downloads.Minio.stat_object") as stat,
        pytest.raises(DownloadError, match="WUXI_KG_MINIO_URL") as caught,
    ):
        DownloadStorage(settings, bucket=BUCKET)
    stat.assert_not_called()
    assert "secret" not in str(caught.value)


def test_missing_optional_download_config_is_reported_at_download_time(monkeypatch):
    for name in (
        "WUXI_KG_MINIO_URL",
        "WUXI_KG_MINIO_ACCESS_KEY",
        "WUXI_KG_MINIO_SECRET_KEY",
    ):
        monkeypatch.delenv(name, raising=False)
    settings = DownloadSettings.from_env()
    assert settings == DownloadSettings()
    with pytest.raises(DownloadError, match="WUXI_KG_MINIO_URL"):
        DownloadStorage(settings, bucket=BUCKET)
    assert SETTINGS.access_key not in repr(SETTINGS)
    assert SETTINGS.secret_key not in repr(SETTINGS)


def test_unavailable_object_does_not_produce_link_or_leak_storage_error():
    storage = DownloadStorage(SETTINGS, bucket=BUCKET)
    with (
        patch(
            "knowledge_mcp.downloads.Minio.stat_object",
            side_effect=OSError("secret locator"),
        ),
        patch("knowledge_mcp.downloads.Minio.presigned_get_object") as sign,
        pytest.raises(DownloadError, match="文件存储") as caught,
    ):
        asyncio.run(storage.download_url(f"s3://{BUCKET}/manual.pdf", "manual.pdf"))
    sign.assert_not_called()
    assert "secret locator" not in str(caught.value)


@pytest.mark.parametrize(
    ("status", "error_code"), [(404, "NoSuchKey"), (403, "AccessDenied")]
)
def test_missing_or_denied_object_reports_read_failure(status, error_code):
    error = S3Error(
        response=HTTPResponse(status=status),
        code=error_code,
        message="private endpoint diagnostics",
        resource="/private-path",
        request_id=None,
        host_id=None,
    )
    storage = DownloadStorage(SETTINGS, bucket=BUCKET)
    with (
        patch("knowledge_mcp.downloads.Minio.stat_object", side_effect=error),
        patch("knowledge_mcp.downloads.Minio.presigned_get_object") as sign,
        pytest.raises(
            DownloadError, match="原文件不存在或文件存储账号无权读取"
        ) as caught,
    ):
        asyncio.run(storage.download_url(f"s3://{BUCKET}/manual.pdf", "manual.pdf"))
    sign.assert_not_called()
    assert "private" not in str(caught.value)
