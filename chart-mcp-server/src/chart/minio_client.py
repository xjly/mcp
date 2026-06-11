"""MinIO storage client."""

import asyncio
import logging
import os
from typing import Optional

from dotenv import load_dotenv
from minio import Minio

load_dotenv()

logger = logging.getLogger(__name__)


class MinioClient:
    """MinIO storage client."""

    def __init__(self) -> None:
        self.endpoint = os.getenv("MINIO_ENDPOINT", "")
        self.access_key = os.getenv("MINIO_ACCESS_KEY", "")
        self.secret_key = os.getenv("MINIO_SECRET_KEY", "")
        self.secure = os.getenv("MINIO_SECURE", "false").lower() == "true"
        self._client: Minio | None = None

    def _get_client(self) -> Minio:
        if not self.endpoint or not self.access_key or not self.secret_key:
            raise RuntimeError("MinIO 配置不完整，请设置 MINIO_ENDPOINT、MINIO_ACCESS_KEY、MINIO_SECRET_KEY")

        if self._client is None:
            self._client = Minio(
                self.endpoint,
                access_key=self.access_key,
                secret_key=self.secret_key,
                secure=self.secure,
            )
        return self._client

    async def download_file(self, bucket_name: str, object_name: str) -> Optional[bytes]:
        """Download a file without blocking the event loop."""
        try:
            return await asyncio.to_thread(self._download_file_sync, bucket_name, object_name)
        except Exception as exc:
            logger.warning("MinIO download failed for %s/%s: %s", bucket_name, object_name, exc)
            return None

    def _download_file_sync(self, bucket_name: str, object_name: str) -> bytes:
        client = self._get_client()
        response = client.get_object(bucket_name, object_name)
        try:
            return response.read()
        finally:
            response.close()
            response.release_conn()


_minio_client: MinioClient | None = None


def get_minio_client() -> MinioClient:
    """Get the shared MinIO client instance."""
    global _minio_client
    if _minio_client is None:
        _minio_client = MinioClient()
    return _minio_client
