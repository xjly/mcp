"""测试 OCR 功能"""

import asyncio
import os
import httpx

# 设置环境变量
os.environ["LLM_API_KEY"] = "sk-dutlwewtllevkhexfserymkxiwxjglhfvjjqpvagcegaabom"

from chart.ocr_service import get_ocr_service

async def test():
    print("=" * 60)
    print("测试 OCR 功能")
    print("=" * 60)
    
    # 检查环境变量
    api_key = os.getenv("LLM_API_KEY")
    print(f"LLM_API_KEY: {api_key[:20]}..." if api_key else "未设置")
    
    ocr = get_ocr_service()
    
    # 下载图片
    image_url = "http://114.66.47.144:9000/kb-images/chat-images/20388ff22b1b4b36aa000f5d31c944e5.png"
    print(f"图片 URL: {image_url}")
    
    async with httpx.AsyncClient() as client:
        resp = await client.get(image_url)
        print(f"图片大小: {len(resp.content)} bytes")
        
        if resp.status_code != 200:
            print(f"下载失败: HTTP {resp.status_code}")
            return
        
        # OCR 识别
        print("\n正在识别图片文字...")
        status, text = await ocr.extract_text_from_image(resp.content)
        
        print(f"\n识别状态: {status}")
        if text:
            print(f"识别结果:\n{text[:500]}")
        else:
            print("识别结果为空")

if __name__ == "__main__":
    asyncio.run(test())