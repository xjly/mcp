"""Chart MCP Server - chart understanding and generation tools."""

import logging
import os
from typing import Any

import httpx
from mcp.server.fastmcp import FastMCP

from chart.chart_service import get_chart_service
from chart.minio_client import get_minio_client
from chart.ocr_service import get_ocr_service

logger = logging.getLogger(__name__)


async def call_llm_for_explanation(ocr_text: str, context: str = "") -> str:
    """Generate a concise chart explanation from OCR text."""
    api_key = os.getenv("LLM_API_KEY", "")
    if not api_key:
        return f"图表内容：{ocr_text[:500]}..."

    model = os.getenv("LLM_MODEL", "deepseek-ai/DeepSeek-V3")
    llm_api_url = os.getenv("LLM_API_URL", "https://api.siliconflow.cn/v1/chat/completions")
    prompt = f"""你是一个专业的数据分析师。请根据以下 OCR 识别结果，解释图表反映的情况。

OCR 识别结果：
{ocr_text}

用户提供的背景信息：
{context or "无"}

请分析：
1. 图表类型
2. 展示的数据项
3. 关键趋势或异常点
4. 结论和建议

请用简洁、专业的语言回答。"""

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(
                llm_api_url,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": model,
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": 1000,
                },
            )
            response.raise_for_status()
            result = response.json()
            return result.get("choices", [{}])[0].get("message", {}).get("content") or ocr_text[:500]
    except Exception as exc:
        logger.warning("LLM explanation failed: %s", exc)
        return f"图表内容：{ocr_text[:500]}..."


mcp = FastMCP(
    "chart-mcp",
    instructions="""
## 图表理解和生成服务

### 服务能力
- **explain_chart**: 解释已有图表，从图片中提取文字并分析。
- **generate_chart**: 根据数据生成图表结构。

### 返回格式
工具返回结构化对象，客户端可直接读取 `chart_spec`、`ocr_text`、`explanation` 等字段。
""",
)


@mcp.tool()
def generate_chart(
    data_json: Any = None,
    chart_type: str | None = None,
    title: str | None = None,
    text: str | None = None,
    threshold: float | None = None,
) -> dict[str, Any]:
    """根据数据生成图表结构。"""
    try:
        if isinstance(threshold, str) and threshold.lower() in {"none", "null", ""}:
            threshold = None

        if data_json is None:
            return {
                "mode": "generate",
                "ok": False,
                "error": "必须提供 data_json 数据",
            }

        chart_svc = get_chart_service()
        parsed_data = chart_svc.parse_data_json(data_json)
        normalized_data = chart_svc.normalize_data(parsed_data)

        if not normalized_data:
            return {
                "mode": "generate",
                "ok": False,
                "error": "data_json 至少需要包含一个有效数据点",
            }

        inferred_type = chart_svc.infer_chart_type(normalized_data, chart_type, text or "")
        final_title = title or text or "数据图表"
        chart_spec = chart_svc.build_chart_spec(
            inferred_type,
            final_title,
            normalized_data,
            threshold,
        )

        return {
            "type": "chart",
            "mode": "generate",
            "ok": True,
            "chart_type": inferred_type,
            "data_points": len(normalized_data),
            "chart_spec": chart_spec,
            "explanation": f"已成功生成{final_title}。数据点共 {len(normalized_data)} 个。",
        }
    except Exception as exc:
        logger.exception("Chart generation failed")
        return {
            "mode": "generate",
            "ok": False,
            "error": f"图表生成失败: {exc}",
        }


@mcp.tool()
async def explain_chart(
    chart_url: str | None = None,
    text: str | None = None,
    ocr_processor: str | None = None,
) -> dict[str, Any]:
    """解释已有图表，从图片中提取文字并进行分析。"""
    if not chart_url:
        return {
            "mode": "explain",
            "ok": False,
            "error": "必须提供 chart_url",
        }

    try:
        chart_svc = get_chart_service()
        minio_client = get_minio_client()
        ocr_svc = get_ocr_service()

        fixed_url = chart_svc.fix_minio_url(chart_url)
        bucket_name, object_name = chart_svc.parse_minio_object(fixed_url)

        image_data = await minio_client.download_file(bucket_name, object_name)
        if not image_data:
            return {
                "mode": "explain",
                "ok": False,
                "error": f"无法下载图片: {bucket_name}/{object_name}",
                "image_url": fixed_url,
            }

        processor = ocr_processor or os.getenv("OCR_PROCESSOR", "deepseek_ocr")
        status, ocr_text = await ocr_svc.extract_text_from_image(image_data, processor)

        if status == "failed":
            return {
                "mode": "explain",
                "ok": False,
                "ocr_text": "",
                "image_url": fixed_url,
                "explanation": f"无法从图片中识别文字内容。图片 URL: {fixed_url}",
                "ocr_error": ocr_text,
            }

        explanation = await call_llm_for_explanation(ocr_text, text or "")
        return {
            "mode": "explain",
            "ok": True,
            "ocr_text": ocr_text,
            "image_url": fixed_url,
            "explanation": explanation,
        }
    except Exception as exc:
        logger.exception("Chart explanation failed")
        return {
            "mode": "explain",
            "ok": False,
            "error": f"处理失败: {exc}",
        }


def main() -> None:
    """Run the MCP server using stdio transport."""
    logging.basicConfig(level=os.getenv("LOG_LEVEL", "WARNING"))
    mcp.run()


if __name__ == "__main__":
    main()
