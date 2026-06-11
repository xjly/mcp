"""OCR service for extracting text from chart images."""

import base64
import logging
import os
from typing import Tuple

import httpx
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)


class OCRService:
    """OCR service backed by OpenAI-compatible vision APIs."""

    def __init__(self) -> None:
        self._default_processor = os.getenv("OCR_PROCESSOR", "deepseek_ocr")
        self._llm_api_key = os.getenv("LLM_API_KEY", "")
        self._ocr_model = os.getenv("OCR_MODEL", "deepseek-ai/DeepSeek-OCR")
        self._vision_model = os.getenv("VISION_MODEL", "Qwen/Qwen2-VL-72B-Instruct")

    async def extract_text_from_image(
        self,
        image_data: bytes,
        processor: str | None = None,
    ) -> Tuple[str, str]:
        """Extract text from image bytes."""
        selected_processor = processor or self._default_processor
        if selected_processor == "deepseek_ocr":
            return await self._call_vision_model(image_data, self._ocr_model, max_tokens=4000)
        return await self._call_vision_model(image_data, self._vision_model, max_tokens=2000)

    async def _call_vision_model(self, image_data: bytes, model: str, max_tokens: int) -> Tuple[str, str]:
        if not self._llm_api_key:
            return "failed", "未设置 LLM_API_KEY"

        try:
            data_url = self._build_data_url(image_data)
            async with httpx.AsyncClient(timeout=60) as client:
                response = await client.post(
                    os.getenv("LLM_API_URL", "https://api.siliconflow.cn/v1/chat/completions"),
                    headers={
                        "Authorization": f"Bearer {self._llm_api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": model,
                        "messages": [
                            {
                                "role": "user",
                                "content": [
                                    {
                                        "type": "text",
                                        "text": "请识别这张图片中的所有文字内容，包括标题、坐标轴标签、数据标签、图例等。只返回识别出的文字，不要额外解释。",
                                    },
                                    {"type": "image_url", "image_url": {"url": data_url}},
                                ],
                            }
                        ],
                        "max_tokens": max_tokens,
                    },
                )

            if response.status_code != 200:
                return "failed", self._format_api_error(response)

            result = response.json()
            text = result.get("choices", [{}])[0].get("message", {}).get("content", "")
            if not text:
                return "failed", "OCR 识别结果为空"
            return "success", text
        except Exception as exc:
            logger.warning("OCR request failed: %s", exc)
            return "failed", str(exc)

    @staticmethod
    def _build_data_url(image_data: bytes) -> str:
        if image_data[:4] == b"\x89PNG":
            mime_type = "image/png"
        elif image_data[:2] == b"\xff\xd8":
            mime_type = "image/jpeg"
        else:
            mime_type = "image/png"

        base64_image = base64.b64encode(image_data).decode("utf-8")
        return f"data:{mime_type};base64,{base64_image}"

    @staticmethod
    def _format_api_error(response: httpx.Response) -> str:
        try:
            detail = response.json()
        except ValueError:
            detail = response.text[:500]
        return f"API 调用失败: {response.status_code}, {detail}"


_ocr_service: OCRService | None = None


def get_ocr_service() -> OCRService:
    """Get the shared OCR service instance."""
    global _ocr_service
    if _ocr_service is None:
        _ocr_service = OCRService()
    return _ocr_service
