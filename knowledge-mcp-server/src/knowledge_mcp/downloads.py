"""Create time-limited original file downloads from a scoped MinIO bucket."""

import asyncio
import os
from dataclasses import dataclass, field
from datetime import timedelta
from urllib.parse import SplitResult, quote, urlsplit

from minio import Minio
from minio.error import S3Error
from urllib3 import PoolManager, Timeout


DOWNLOAD_TTL_SECONDS = 300
IO_TIMEOUT = 10


class DownloadError(ValueError):
    """A download failure whose message is suitable for MCP tool callers."""


@dataclass(frozen=True)
class DownloadSettings:
    url: str = field(default="", repr=False)
    access_key: str = field(default="", repr=False)
    secret_key: str = field(default="", repr=False)

    @classmethod
    def from_env(cls) -> "DownloadSettings":
        return cls(
            url=os.environ.get("WUXI_KG_MINIO_URL", "").strip(),
            access_key=os.environ.get("WUXI_KG_MINIO_ACCESS_KEY", "").strip(),
            secret_key=os.environ.get("WUXI_KG_MINIO_SECRET_KEY", "").strip(),
        )

    def origin(self) -> SplitResult:
        if not self.url or not self.access_key or not self.secret_key:
            raise DownloadError(
                "文件下载尚未配置，请设置 WUXI_KG_MINIO_URL、"
                "WUXI_KG_MINIO_ACCESS_KEY 和 WUXI_KG_MINIO_SECRET_KEY。"
            )
        try:
            return _http_origin(self.url)
        except ValueError:
            raise DownloadError(
                "WUXI_KG_MINIO_URL 必须是无凭证、路径或查询参数的 HTTP(S) 服务地址。"
            ) from None


class DownloadStorage:
    def __init__(self, settings: DownloadSettings, *, bucket: str) -> None:
        self._settings = settings
        self._origin = settings.origin()
        self._bucket = bucket

    async def download_url(self, storage_path: str, file_name: str) -> str:
        object_name = self._object_name(storage_path)
        try:
            async with asyncio.timeout(IO_TIMEOUT):
                return await asyncio.to_thread(self._sign, object_name, file_name)
        except S3Error as exc:
            if exc.code in {
                "NoSuchKey",
                "NoSuchObject",
                "NoSuchBucket",
                "NotFound",
                "AccessDenied",
            }:
                raise DownloadError("原文件不存在或文件存储账号无权读取。") from None
            raise DownloadError("无法从文件存储生成下载链接。") from None
        except Exception:
            raise DownloadError(
                "无法从文件存储生成下载链接，请检查连接及读取权限。"
            ) from None

    def _object_name(self, storage_path: str) -> str:
        # Wuxi's upload endpoint stores the object name literally in the locator.
        # Preserve spaces, percent signs, question marks and hashes for the SDK to encode.
        scheme, separator, locator = storage_path.partition("://")
        if separator and scheme.lower() in {"http", "https"}:
            authority, _, locator = locator.partition("/")
            try:
                _http_origin(f"{scheme}://{authority}")
            except ValueError:
                raise DownloadError("文件记录中的对象存储地址无效。") from None
        elif not separator or scheme.lower() not in {"minio", "s3"}:
            raise DownloadError("该文件没有可下载的对象存储原件。")

        bucket, _, object_name = locator.partition("/")
        if bucket != self._bucket:
            raise DownloadError("该原文件不属于当前知识库的下载存储桶。")
        if (
            not object_name.strip()
            or "\\" in object_name
            or any(ord(char) < 32 or ord(char) == 127 for char in object_name)
            or any(part in {"", ".", ".."} for part in object_name.split("/"))
        ):
            raise DownloadError("文件记录中的对象名称无效。")
        return object_name

    def _sign(self, object_name: str, file_name: str) -> str:
        name = file_name.replace("\\", "/").rsplit("/", maxsplit=1)[-1]
        name = "".join(
            char for char in name if ord(char) >= 32 and ord(char) != 127
        ).strip()
        if name in {"", ".", ".."}:
            name = "document"
        disposition = f"attachment; filename*=UTF-8''{quote(name, safe='')}"
        with PoolManager(
            timeout=Timeout(total=IO_TIMEOUT, connect=5, read=5),
            retries=False,
            cert_reqs="CERT_REQUIRED",
            ca_certs=os.environ.get("SSL_CERT_FILE"),
        ) as http:
            client = Minio(
                self._origin.netloc,
                access_key=self._settings.access_key,
                secret_key=self._settings.secret_key,
                secure=self._origin.scheme == "https",
                region="us-east-1",
                http_client=http,
            )
            client.stat_object(self._bucket, object_name)
            return client.presigned_get_object(
                self._bucket,
                object_name,
                expires=timedelta(seconds=DOWNLOAD_TTL_SECONDS),
                response_headers={"response-content-disposition": disposition},
            )


def _http_origin(url: str) -> SplitResult:
    parsed = urlsplit(url)
    port = parsed.port
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username is not None
        or parsed.path not in {"", "/"}
        or "?" in url
        or "#" in url
        or "\\" in url
        or any(char.isspace() or ord(char) < 32 or ord(char) == 127 for char in url)
        or port == 0
        or parsed.netloc.endswith(":")
    ):
        raise ValueError("Invalid HTTP origin")
    return parsed
