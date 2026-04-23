"""QWeather MCP Server - 气象数据查询服务。"""

from __future__ import annotations

import json
from typing import Any

from mcp.server.fastmcp import FastMCP

from weather.config import get_qweather_config
from weather.qweather_client import QWeatherClient

mcp = FastMCP(
    "weather",
    instructions="""
## 和风天气查询服务

### 服务能力
- `search_location_id_by_name`: 通过城市名/区名查询候选 location_id
- `get_weather_forecast`: 查询未来天气（hourly/daily）
- `get_weather_history`: 查询历史天气（hourly/daily）

### 参数约束
- 主查询参数使用 `location_id`
- 粒度仅支持：`hourly`、`daily`
- `hours` 范围：1~168
- `days` 范围：1~30
""",
)

_client: QWeatherClient | None = None


def get_client() -> QWeatherClient:
    """Get or create singleton QWeather client."""
    global _client
    if _client is None:
        _client = QWeatherClient(get_qweather_config())
    return _client


def _safe_result(result: Any) -> Any:
    """Convert result to JSON-serializable values."""
    if result is None:
        return None
    if isinstance(result, dict):
        return {k: _safe_result(v) for k, v in result.items()}
    if isinstance(result, list):
        return [_safe_result(v) for v in result]
    if isinstance(result, (str, int, float, bool)):
        return result
    return str(result)


@mcp.tool()
async def search_location_id_by_name(
    query: str,
    adm: str | None = None,
    limit: int = 5,
) -> str:
    """
    通过城市名或区名检索候选 location_id。

    Args:
        query: 地名关键字（如“上海”“浦东新区”）
        adm: 行政区过滤（可选，如“上海”）
        limit: 返回候选数量上限，默认 5，最大 20

    Returns:
        JSON 字符串，包含候选位置与 location_id 列表
    """
    if not query.strip():
        return json.dumps({"error": "query is required"}, ensure_ascii=False, indent=2)

    limit = max(1, min(limit, 20))
    result = get_client().search_location_id_by_name(query=query, adm=adm, limit=limit)
    return json.dumps(_safe_result(result), ensure_ascii=False, indent=2)


@mcp.tool()
async def get_weather_forecast(
    location_id: str,
    granularity: str = "hourly",
    hours: int = 24,
    days: int = 7,
) -> str:
    """
    查询未来天气数据（小时级或天级）。

    Args:
        location_id: 和风 location_id
        granularity: 粒度，hourly 或 daily
        hours: granularity=hourly 时窗口大小（1~168）
        days: granularity=daily 时窗口大小（1~30）

    Returns:
        JSON 字符串，包含标准化后的天气数据
    """
    if not location_id.strip():
        return json.dumps(
            {"error": "location_id is required"},
            ensure_ascii=False,
            indent=2,
        )

    try:
        result = get_client().get_weather_forecast(
            location_id=location_id,
            granularity=granularity,
            hours=hours,
            days=days,
        )
    except ValueError as exc:
        return json.dumps({"error": str(exc)}, ensure_ascii=False, indent=2)
    return json.dumps(_safe_result(result), ensure_ascii=False, indent=2)


@mcp.tool()
async def get_weather_history(
    location_id: str,
    granularity: str = "hourly",
    hours: int = 24,
    days: int = 7,
) -> str:
    """
    查询历史天气数据（小时级或天级）。

    Args:
        location_id: 和风 location_id
        granularity: 粒度，hourly 或 daily
        hours: granularity=hourly 时窗口大小（1~168）
        days: granularity=daily 时窗口大小（1~30）

    Returns:
        JSON 字符串，包含标准化后的历史天气数据
    """
    if not location_id.strip():
        return json.dumps(
            {"error": "location_id is required"},
            ensure_ascii=False,
            indent=2,
        )

    try:
        result = get_client().get_weather_history(
            location_id=location_id,
            granularity=granularity,
            hours=hours,
            days=days,
        )
    except ValueError as exc:
        return json.dumps({"error": str(exc)}, ensure_ascii=False, indent=2)
    return json.dumps(_safe_result(result), ensure_ascii=False, indent=2)


def main():
    """Entry point for MCP runtime."""
    mcp.run()
