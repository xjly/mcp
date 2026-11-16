"""Adapt the existing wuxi_kg graph assistant to an MCP tool."""

import asyncio
import json
import os
from typing import Annotated, Any, Literal
from urllib.parse import urlsplit

import httpx
from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.exceptions import ToolError
from mcp.types import ToolAnnotations
from pydantic import BaseModel, Field, StringConstraints


_GRAPH_TOOL_KINDS = {
    "NativeGraph工具": {"graph_query_result"},
    "图谱节点实时统计": {"graph_statistics", "graph_statistics_error"},
}


class NativeGraphResult(BaseModel):
    kind: Literal["graph_query_result", "graph_statistics", "agent_answer"]
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

    return base_url.rstrip("/") + "/api/chat/agent/MiniAgent", access_token


def _message_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(
            block["text"]
            for block in content
            if isinstance(block, dict)
            and block.get("type") == "text"
            and isinstance(block.get("text"), str)
        )
    return ""


async def _read_chat_stream(response: httpx.Response) -> NativeGraphResult:
    graph_payload = None
    answer_chunks: list[str] = []
    message_id = None
    async for line in response.aiter_lines():
        if not line.strip():
            continue
        frame = json.loads(line)
        if not isinstance(frame, dict) or not isinstance(frame.get("status"), str):
            raise ValueError("Invalid chat frame")
        status = frame["status"]
        if status == "finished":
            break
        if status == "interrupted":
            raise ToolError("图谱助手中断了对话，请调整问题后重试。")
        if status == "error":
            if frame.get("error_type") == "no_department":
                raise ToolError("图谱助手要求登录账号绑定部门。")
            raise ToolError("图谱助手查询失败，请稍后重试或检查助手配置。")
        message = frame.get("msg")
        if status != "loading" or not isinstance(message, dict):
            continue

        message_type = message.get("type")
        if message_type == "tool":
            answer_chunks.clear()
            message_id = None
            allowed_kinds = _GRAPH_TOOL_KINDS.get(message.get("name", ""), ())
            if allowed_kinds:
                content = message.get("content")
                try:
                    payload = (
                        json.loads(content) if isinstance(content, str) else content
                    )
                except json.JSONDecodeError:
                    continue
                if isinstance(payload, dict) and payload.get("kind") in allowed_kinds:
                    graph_payload = payload
        elif message_type in {"AIMessageChunk", "ai"} and not message.get("tool_calls"):
            chunk = _message_text(frame.get("response")) or _message_text(
                message.get("content")
            )
            if chunk:
                current_id = message.get("id")
                if (current_id and current_id != message_id) or message_type == "ai":
                    answer_chunks.clear()
                answer_chunks.append(chunk)
                message_id = current_id
    else:
        raise ToolError("图谱助手的响应未结束，请重试。")

    if graph_payload is not None:
        if graph_payload.get("status") == "error":
            raise ToolError("图谱查询失败，请稍后重试或联系管理员。")
        if graph_payload["kind"] == "graph_statistics_error":
            raise ToolError("图谱统计失败，请稍后重试或联系管理员。")
        if graph_payload["kind"] == "graph_statistics":
            return NativeGraphResult(
                kind="graph_statistics",
                status="ok",
                intent="statistics",
                answer_text=graph_payload.get("answer_text"),
                nodes=[],
                edges=[],
                candidates=[],
                meta={
                    key: graph_payload[key]
                    for key in (
                        "source",
                        "as_of",
                        "facts",
                        "total_nodes",
                        "total_relationships",
                        "node_types",
                    )
                    if key in graph_payload
                },
            )
        return NativeGraphResult.model_validate(graph_payload)

    answer = "".join(answer_chunks).strip()
    if not answer:
        raise ToolError("图谱助手未返回答案，请检查助手是否启用了 NativeGraph 工具。")
    return NativeGraphResult(
        kind="agent_answer",
        status="ok",
        intent="agent_answer",
        answer_text=answer,
        nodes=[],
        edges=[],
        candidates=[],
        meta={"source": "graph_assistant", "node_count": 0, "edge_count": 0},
    )


def _limit_nodes(result: NativeGraphResult, top_k: int) -> NativeGraphResult:
    if len(result.nodes) <= top_k:
        return result
    nodes = result.nodes[:top_k]
    node_ids = {node["id"] for node in nodes if isinstance(node.get("id"), str)}
    edges = [
        edge
        for edge in result.edges
        if isinstance(edge.get("source"), str)
        and isinstance(edge.get("target"), str)
        and edge["source"] in node_ids
        and edge["target"] in node_ids
    ]
    return result.model_copy(
        update={
            "nodes": nodes,
            "edges": edges,
            "meta": result.meta
            | {
                "node_count": len(nodes),
                "edge_count": len(edges),
                "truncated": True,
            },
        }
    )


async def query_native_graph(
    user_query: Annotated[
        str,
        StringConstraints(strip_whitespace=True, min_length=1, max_length=1000),
        Field(description="水网图谱自然语言问题，包含待查询的实体或关系"),
    ],
    top_k: Annotated[
        int, Field(ge=1, le=50, description="MCP 结果最多返回的节点数")
    ] = 20,
) -> NativeGraphResult:
    """询问 wuxi_kg 图谱助手。助手会处理本次对话，启用 NativeGraph 工具时可返回水网查询证据。"""
    endpoint, access_token = _query_settings()
    try:
        async with (
            asyncio.timeout(90),
            httpx.AsyncClient(
                timeout=httpx.Timeout(45, connect=5), follow_redirects=False
            ) as client,
        ):
            async with client.stream(
                "POST",
                endpoint,
                headers={"Authorization": f"Bearer {access_token}"},
                json={"query": user_query.strip()},
            ) as response:
                if response.status_code in {401, 403}:
                    raise ToolError(
                        "wuxi_kg 拒绝访问，请确认令牌有效且账号有权限查询。"
                    )
                if response.status_code == 404:
                    raise ToolError("未找到 wuxi_kg 图谱助手的对话接口。")
                if not response.is_success:
                    raise ToolError("图谱助手查询失败，请稍后重试或联系管理员。")
                return _limit_nodes(await _read_chat_stream(response), top_k)
    except (TimeoutError, httpx.TimeoutException):
        raise ToolError("图谱查询超时，请缩小问题范围或稍后重试。") from None
    except (httpx.RequestError, httpx.InvalidURL):
        raise ToolError("无法连接 wuxi_kg 图谱接口，请检查服务地址和网络。") from None
    except ValueError:
        raise ToolError("wuxi_kg 图谱助手响应格式不正确。") from None


def register_native_query(mcp: FastMCP) -> None:
    mcp.add_tool(
        query_native_graph,
        title="查询水网知识图谱",
        annotations=ToolAnnotations(
            readOnlyHint=False,
            idempotentHint=False,
            openWorldHint=True,
        ),
    )
