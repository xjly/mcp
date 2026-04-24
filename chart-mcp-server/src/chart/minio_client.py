"""MinIO 客户端 - 文件存储服务"""

import os
from typing import Optional
from minio import Minio
from dotenv import load_dotenv

load_dotenv()


class MinioClient:
    """MinIO 存储客户端"""
    
    def __init__(self):
        self.endpoint = os.getenv("MINIO_ENDPOINT", "114.66.47.144:9000")
        self.access_key = os.getenv("MINIO_ACCESS_KEY", "minioadmin")
        self.secret_key = os.getenv("MINIO_SECRET_KEY", "minioadmin")
        self.secure = os.getenv("MINIO_SECURE", "False").lower() == "true"
        self._client = None
    
    def _get_client(self) -> Minio:
        if self._client is None:
            self._client = Minio(
                self.endpoint,
                access_key=self.access_key,
                secret_key=self.secret_key,
                secure=self.secure
            )
        return self._client
    
    async def download_file(self, bucket_name: str, object_name: str) -> Optional[bytes]:
        """下载文件（异步包装）"""
        try:
            client = self._get_client()
            # MinIO 的 get_object 是同步的，但我们在 async 函数中调用
            response = client.get_object(bucket_name, object_name)
            data = response.read()
            response.close()
            response.release_conn()
            return data
        except Exception as e:
            print(f"MinIO download error: {e}")
            return None


_minio_client: MinioClient | None = None


def get_minio_client() -> MinioClient:
    global _minio_client
    if _minio_client is None:
        _minio_client = MinioClient()
    return _minio_client