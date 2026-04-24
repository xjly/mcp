"""OCR 服务 - 图片文字识别（使用 DeepSeek OCR）"""

import os
import base64
from typing import Tuple
import httpx
from dotenv import load_dotenv

load_dotenv()


class OCRService:
    """OCR 识别服务 - 使用 DeepSeek OCR 模型"""
    
    def __init__(self):
        self._default_processor = os.getenv("OCR_PROCESSOR", "deepseek_ocr")
        self._llm_api_key = os.getenv("LLM_API_KEY", "")
        # 使用 DeepSeek OCR 专用模型
        self._ocr_model = os.getenv("OCR_MODEL", "deepseek-ai/DeepSeek-OCR")
    
    async def extract_text_from_image(
        self, 
        image_data: bytes, 
        processor: str = "deepseek_ocr"
    ) -> Tuple[str, str]:
        """
        从图片中提取文字
        
        Returns:
            (status, text) - status: "success" or "failed"
        """
        # 使用 DeepSeek OCR
        if processor == "deepseek_ocr":
            return await self._call_deepseek_ocr(image_data)
        else:
            # 备选方案
            return await self._call_llm_vision(image_data)
    
    async def _call_deepseek_ocr(self, image_data: bytes) -> Tuple[str, str]:
        """调用 DeepSeek OCR API"""
        try:
            # 将图片转为 base64
            base64_image = base64.b64encode(image_data).decode('utf-8')
            
            # 检测图片格式
            if image_data[:4] == b'\x89PNG':
                mime_type = "image/png"
            elif image_data[:2] == b'\xff\xd8':
                mime_type = "image/jpeg"
            else:
                mime_type = "image/png"
            
            data_url = f"data:{mime_type};base64,{base64_image}"
            
            async with httpx.AsyncClient(timeout=60) as client:
                response = await client.post(
                    os.getenv("LLM_API_URL", "https://api.siliconflow.cn/v1/chat/completions"),
                    headers={
                        "Authorization": f"Bearer {self._llm_api_key}",
                        "Content-Type": "application/json"
                    },
                    json={
                        "model": self._ocr_model,
                        "messages": [
                            {
                                "role": "user",
                                "content": [
                                    {
                                        "type": "text", 
                                        "text": "请识别这张图片中的所有文字内容。包括标题、坐标轴标签、数据标签、图例等。只返回识别出的文字，不要额外解释。"
                                    },
                                    {
                                        "type": "image_url", 
                                        "image_url": {"url": data_url}
                                    }
                                ]
                            }
                        ],
                        "max_tokens": 4000
                    }
                )
                
                print(f"📡 DeepSeek OCR 响应状态: {response.status_code}")
                
                if response.status_code == 200:
                    result = response.json()
                    text = result.get("choices", [{}])[0].get("message", {}).get("content", "")
                    if text:
                        print(f"✅ OCR 成功，识别文字长度: {len(text)}")
                        return "success", text
                    else:
                        return "failed", "OCR 识别结果为空"
                else:
                    error_msg = f"API 调用失败: {response.status_code}"
                    try:
                        error_detail = response.json()
                        error_msg += f", {error_detail}"
                        print(f"❌ {error_msg}")
                    except:
                        pass
                    return "failed", error_msg
                    
        except Exception as e:
            print(f"❌ OCR 异常: {e}")
            return "failed", str(e)
    
    async def _call_llm_vision(self, image_data: bytes) -> Tuple[str, str]:
        """备用方案：调用通用视觉模型"""
        try:
            base64_image = base64.b64encode(image_data).decode('utf-8')
            
            if image_data[:4] == b'\x89PNG':
                mime_type = "image/png"
            elif image_data[:2] == b'\xff\xd8':
                mime_type = "image/jpeg"
            else:
                mime_type = "image/png"
            
            data_url = f"data:{mime_type};base64,{base64_image}"
            
            async with httpx.AsyncClient(timeout=60) as client:
                response = await client.post(
                    os.getenv("LLM_API_URL", "https://api.siliconflow.cn/v1/chat/completions"),
                    headers={
                        "Authorization": f"Bearer {self._llm_api_key}",
                        "Content-Type": "application/json"
                    },
                    json={
                        "model": "Qwen/Qwen2-VL-72B-Instruct",  # 备用模型
                        "messages": [
                            {
                                "role": "user",
                                "content": [
                                    {"type": "text", "text": "请识别这张图片中的所有文字内容。"},
                                    {"type": "image_url", "image_url": {"url": data_url}}
                                ]
                            }
                        ],
                        "max_tokens": 2000
                    }
                )
                
                if response.status_code == 200:
                    result = response.json()
                    text = result.get("choices", [{}])[0].get("message", {}).get("content", "")
                    return "success", text
                else:
                    return "failed", f"API 调用失败: {response.status_code}"
                    
        except Exception as e:
            return "failed", str(e)


_ocr_service: OCRService | None = None


def get_ocr_service() -> OCRService:
    """获取 OCR 服务实例"""
    global _ocr_service
    if _ocr_service is None:
        _ocr_service = OCRService()
    return _ocr_service