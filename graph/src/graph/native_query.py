"""Call the water-network graph query service used by wuxi_kg."""

import asyncio
import os
from typing import Annotated, Any, Literal
from urllib.parse import urlsplit

import httpx
from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.exceptions import ToolError
from mcp.types import ToolAnnotations
from pydantic import BaseModel, Field, StringConstraints


class NativeGraphResult(BaseModel):
    kind: Literal["graph_query_result"]
    status: Literal["ok", "empty", "clarification"]
    intent: str
    answer_text: str
    nodes: list[dict[str, Any]]
    edges: list[dict[str, Any]]
    candidates: list[dict[str, Any]]
    meta: dict[str, Any]


def _query_settings() -> tuple[str, str]:
    base_url = os.getenv("WUXI_KG_API_BASE_URL", "").strip()
    access_token = os.getenv("WUXI_KG_ACCESS_TOKEN", "").strip()
    if not base_url or not access_token:
        raise ToolError(
            "请配置 WUXI_KG_API_BASE_URL 和 WUXI_KG_ACCESS_TOKEN 以使用自然语言图谱查询。"
        )
    try:
        parsed = urlsplit(base_url)
        valid = (
            parsed.scheme in {"http", "https"}
            and parsed.hostname
            and parsed.username is None
            and parsed.port != 0
            and "?" not in base_url
            and "#" not in base_url
            and "\\" not in base_url
            and not any(
                char.isspace() or ord(char) < 32 or ord(char) == 127
                for char in base_url
            )
        )
    except ValueError:
        valid = False
    if not valid:
        raise ToolError(
            "WUXI_KG_API_BASE_URL 须为不含凭证、查询参数或片段的 HTTP(S) 地址。"
        )

    return base_url.rstrip("/") + "/api/native-graph/mcp/query", access_token


async def query_native_graph(
    user_query: Annotated[
        str,
        StringConstraints(strip_whitespace=True, min_length=1, max_length=1000),
        Field(description="水网图谱自然语言问题，包含待查询的实体或关系"),
    ],
    top_k: Annotated[int, Field(ge=1, le=50, description="最多返回的节点数")] = 20,
) -> NativeGraphResult:
    """通过 wuxi_kg 查询水网实体、关系、统计、路径或多跳子图。请保留 answer_text 的事实与数值。"""
    endpoint, access_token = _query_settings()
    try:
        async with (
            asyncio.timeout(50),
            httpx.AsyncClient(
                timeout=httpx.Timeout(45, connect=5), follow_redirects=False
            ) as client,
        ):
            response = await client.post(
                endpoint,
                headers={"Authorization": f"Bearer {access_token}"},
                json={"user_query": user_query.strip(), "top_k": top_k},
            )
    except (TimeoutError, httpx.TimeoutException):
        raise ToolError("图谱查询超时，请缩小问题范围或稍后重试。") from None
    except (httpx.RequestError, httpx.InvalidURL):
        raise ToolError("无法连接 wuxi_kg 图谱接口，请检查服务地址和网络。") from None

    if response.status_code in {401, 403}:
        raise ToolError("wuxi_kg 拒绝访问，请确认令牌有效且账号有权限查询。")
    if response.status_code == 404:
        raise ToolError("未找到自然语言图谱查询接口，请确认 wuxi_kg 已部署对应版本。")
    if not response.is_success:
        raise ToolError("图谱查询失败，请稍后重试或联系管理员。")

    try:
        payload = response.json()
        if isinstance(payload, dict) and payload.get("status") == "error":
            raise ToolError("图谱查询失败，请稍后重试或联系管理员。")
        return NativeGraphResult.model_validate(payload)
    except ValueError:
        raise ToolError("wuxi_kg 图谱接口响应格式不正确。") from None


def register_native_query(mcp: FastMCP) -> None:
    mcp.add_tool(
        query_native_graph,
        title="查询水网知识图谱",
        annotations=ToolAnnotations(
            readOnlyHint=True,
            destructiveHint=False,
            idempotentHint=True,
            openWorldHint=True,
        ),
    )
