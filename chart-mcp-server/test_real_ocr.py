"""Manual OCR integration test.

Set LLM_API_KEY and OCR_TEST_IMAGE_URL before running this file.
"""

import asyncio
import os
import sys

import httpx

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from chart.ocr_service import get_ocr_service


async def test() -> None:
    api_key = os.getenv("LLM_API_KEY")
    image_url = os.getenv("OCR_TEST_IMAGE_URL")

    if not api_key:
        raise RuntimeError("请先设置 LLM_API_KEY")
    if not image_url:
        raise RuntimeError("请先设置 OCR_TEST_IMAGE_URL")

    async with httpx.AsyncClient() as client:
        response = await client.get(image_url)
        response.raise_for_status()

    ocr = get_ocr_service()
    status, text = await ocr.extract_text_from_image(response.content)

    print(f"识别状态: {status}")
    print(text[:500] if text else "识别结果为空")


if __name__ == "__main__":
    asyncio.run(test())
