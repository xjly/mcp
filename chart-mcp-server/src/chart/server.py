"""Chart MCP Server - 图表理解和生成服务"""

import json
import os
import httpx
from typing import Any

from mcp.server.fastmcp import FastMCP
from chart.chart_service import get_chart_service
from chart.minio_client import get_minio_client
from chart.ocr_service import get_ocr_service


async def call_llm_for_explanation(ocr_text: str, context: str = "") -> str:
    """调用 LLM 生成图表解释"""
    try:
        api_key = os.getenv("LLM_API_KEY", "")
        model = os.getenv("LLM_MODEL", "deepseek-ai/DeepSeek-V3")
        
        prompt = f"""你是一个专业的数据分析师。请根据以下 OCR 识别结果，解释图表反映的状况：

OCR识别结果：{ocr_text}

用户提供的背景信息：{context or '无'}

请分析：
1. 图表类型
2. 展示的数据项
3. 关键趋势或异常点
4. 结论和建议

请用简洁专业的语言回答。"""

        # 从环境变量获取 LLM API 端点
        llm_api_url = os.getenv("LLM_API_URL", "https://api.siliconflow.cn/v1/chat/completions")
        
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(
                llm_api_url,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": model,
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": 1000
                }
            )
            
            if response.status_code == 200:
                result = response.json()
                return result.get("choices", [{}])[0].get("message", {}).get("content", ocr_text[:500])
            else:
                return f"图表内容：{ocr_text[:500]}..."
                
    except Exception as e:
        print(f"LLM 调用失败: {e}")
        return f"图表内容：{ocr_text[:500]}..."

# ============================================================================
# MCP 服务器定义
# ============================================================================

mcp = FastMCP(
    "chart-mcp",
    instructions="""
## 图表理解和生成服务

### 服务能力
本服务提供图表处理能力：
- **explain_chart**: 解释已有图表（从图片中提取文字并分析）
- **generate_chart**: 根据数据生成图表结构

### 使用场景
1. 上传图表图片，自动识别和分析
2. 根据数据自动生成可视化图表规格
""",
)


@mcp.tool()
def generate_chart(
    data_json: Any = None,
    chart_type: str = None,
    title: str = None,
    text: str = None,
    threshold: float = None,
) -> str:
    """
    根据数据生成图表结构。
    返回格式与图表理解工具完全一致。
    """
    try:
        # --- 1. 参数标准化 ---
        if threshold == "None" or threshold == "null":
            threshold = None

        if data_json is None:
            return json.dumps({
                "mode": "generate",
                "ok": False,
                "error": "必须提供 data_json 数据"
            }, ensure_ascii=False)

        # 解析 data_json
        if isinstance(data_json, str):
            raw_data = data_json.strip()
            if raw_data.startswith('{{') and raw_data.endswith('}}'):
                raw_data = raw_data[1:-1]
            try:
                data_json = json.loads(raw_data)
            except json.JSONDecodeError:
                return json.dumps({
                    "mode": "generate",
                    "ok": False,
                    "error": f"data_json 格式错误，无法解析为 JSON"
                }, ensure_ascii=False)

        # 转换为列表格式
        if isinstance(data_json, dict):
            if "values" in data_json:
                data_json = data_json["values"]
            else:
                data_json = [{"name": k, "value": v} for k, v in data_json.items()]

        if not isinstance(data_json, list):
            return json.dumps({
                "mode": "generate",
                "ok": False,
                "error": f"data_json 必须是数组格式"
            }, ensure_ascii=False)

        # 标准化数据
        normalized_data = []
        for i, item in enumerate(data_json):
            if isinstance(item, dict):
                # 查找 name
                name = None
                for key in ["name", "label", "category", "x"]:
                    if key in item:
                        name = item[key]
                        break
                if name is None:
                    name = f"项{i+1}"
                
                # 查找 value
                value = None
                for key in ["value", "amount", "count", "y"]:
                    if key in item:
                        val = item[key]
                        if isinstance(val, (int, float)):
                            value = val
                        elif isinstance(val, list) and len(val) > 0:
                            value = val[0] if isinstance(val[0], (int, float)) else 0
                        else:
                            try:
                                value = float(val)
                            except:
                                value = 0
                        break
                
                if value is None:
                    value = 0
                
                normalized_data.append({"name": str(name), "value": value})
            elif isinstance(item, (int, float)):
                normalized_data.append({"name": f"项{i+1}", "value": item})
            else:
                normalized_data.append({"name": str(item), "value": 0})

        # --- 2. 推断图表类型 ---
        inferred_type = chart_type or "bar"
        final_title = title or text or "数据图表"

        # --- 3. 构建 chart_spec（与图表理解工具完全一致）---
        chart_spec = {
            "type": inferred_type,
            "title": final_title,
            "x_field": "name",
            "y_field": "value",
            "values": normalized_data
        }
        if threshold and isinstance(threshold, (int, float)):
            chart_spec["threshold"] = threshold

        # --- 4. 返回与图表理解工具完全一致的格式 ---
        return json.dumps({
            "type": "chart",
            "mode": "generate",
            "ok": True,
            "chart_type": inferred_type,
            "chart_spec": chart_spec,
            "explanation": f"已成功生成{final_title}。数据点共 {len(normalized_data)} 个。"
        }, ensure_ascii=False)

    
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        return json.dumps({
            "mode": "generate",
            "ok": False,
            "error": f"图表生成失败: {str(e)}"
        }, ensure_ascii=False)


@mcp.tool()
async def explain_chart(
    chart_url: str = None,
    text: str = None,
    ocr_processor: str = os.getenv("OCR_PROCESSOR", "deepseek_ocr"),
) -> str:
    """解释已有图表。从图片中提取文字并进行分析。"""
    
    if chart_url is None:
        return json.dumps({
            "mode": "explain",
            "ok": False,
            "error": "必须提供 chart_url"
        }, ensure_ascii=False)
    
    try:
        chart_svc = get_chart_service()
        minio_client = get_minio_client()
        ocr_svc = get_ocr_service()
        
        # 修复 URL
        chart_url = chart_svc.fix_minio_url(chart_url)
        
        # 解析 MinIO 路径
        from urllib.parse import urlparse
        parsed = urlparse(chart_url)
        path_parts = [p for p in parsed.path.lstrip("/").split("/") if p]
        
        default_bucket = os.getenv("DEFAULT_BUCKET", "kb-images")
        default_chat_path = os.getenv("DEFAULT_CHAT_IMAGES_PATH", "chat-images")
        
        if len(path_parts) >= 2:
            bucket_name = path_parts[0]
            object_name = "/".join(path_parts[1:])
        else:
            bucket_name = default_bucket
            object_name = default_chat_path + "/" + path_parts[0] if path_parts else ""
        
        # 下载图片
        image_data = await minio_client.download_file(bucket_name, object_name)
        
        if not image_data:
            return json.dumps({
                "mode": "explain",
                "ok": False,
                "error": f"无法下载图片: {bucket_name}/{object_name}"
            }, ensure_ascii=False)
        
        # OCR 识别
        status, ocr_text = await ocr_svc.extract_text_from_image(image_data, ocr_processor)
        
        if status == "failed":
            return json.dumps({
                "mode": "explain",
                "ok": True,
                "ocr_text": "",
                "image_url": chart_url,
                "explanation": f"无法从图片中识别文字内容。图片 URL: {chart_url}",
                "ocr_error": ocr_text
            }, ensure_ascii=False, indent=2)
        
        # 生成解释
        explanation = await call_llm_for_explanation(ocr_text, text)
        
        return json.dumps({
            "mode": "explain",
            "ok": True,
            "ocr_text": ocr_text,
            "image_url": chart_url,
            "explanation": explanation
        }, ensure_ascii=False, indent=2)
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        return json.dumps({
            "mode": "explain",
            "ok": False,
            "error": f"处理失败: {str(e)}"
        }, ensure_ascii=False)


def main():
    """主入口函数"""
    import sys
    import io
    
    if sys.platform == 'win32':
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')
    
    print("=" * 60)
    print(" Chart MCP Server 启动中...")
    print("=" * 60)
    print("   - 图表生成: 返回 JSON 格式")
    print("=" * 60)
    mcp.run()


if __name__ == "__main__":
    main()