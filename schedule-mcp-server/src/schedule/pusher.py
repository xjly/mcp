"""Push Service - 推送服务层"""

import os
import json
import httpx
from datetime import datetime
from typing import Optional
from dotenv import load_dotenv

load_dotenv()


class PushService:
    """大屏推送服务"""

    def __init__(self):
        self._base_url = os.getenv("PUSH_SERVICE_URL", "http://localhost:8080/api/push")
        self._timeout = int(os.getenv("PUSH_TIMEOUT", "30"))

    async def push_to_screen(
        self,
        content: str,
        screen_id: str = "default_screen",
        title: Optional[str] = None
    ) -> dict:
        """
        推送内容到大屏

        Args:
            content: 推送内容
            screen_id: 大屏标识符
            title: 推送标题

        Returns:
            推送结果字典
        """
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.post(
                    f"{self._base_url}/{screen_id}",
                    json={
                        "content": content,
                        "title": title,
                        "timestamp": datetime.now().isoformat()
                    },
                    headers={"Content-Type": "application/json"}
                )

                if response.status_code == 200:
                    result = response.json()
                    return {
                        "status": "success",
                        "screen_id": screen_id,
                        "title": title,
                        "content_preview": content[:100] + "..." if len(content) > 100 else content,
                        "message": f"内容已成功推送到大屏 {screen_id}",
                        "server_response": result
                    }
                else:
                    return {
                        "status": "error",
                        "screen_id": screen_id,
                        "error": f"推送失败，HTTP {response.status_code}",
                        "response": response.text
                    }

        except httpx.ConnectError:
            return {
                "status": "error",
                "screen_id": screen_id,
                "error": f"无法连接到大屏服务: {self._base_url}"
            }
        except httpx.TimeoutException:
            return {
                "status": "error",
                "screen_id": screen_id,
                "error": "推送请求超时"
            }
        except Exception as e:
            return {
                "status": "error",
                "screen_id": screen_id,
                "error": f"推送失败: {str(e)}"
            }


# 全局实例
_push_service: PushService | None = None


def get_push_service() -> PushService:
    """获取或创建 PushService 实例"""
    global _push_service
    if _push_service is None:
        _push_service = PushService()
    return _push_service