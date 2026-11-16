"""Stdio tools for the configured shared Wuxi knowledge base."""

import logging
from contextlib import asynccontextmanager, contextmanager
from typing import Annotated

from mcp.server.fastmcp import Context, FastMCP
from mcp.server.fastmcp.exceptions import ToolError
from mcp.types import ToolAnnotations
from pydantic import Field, StringConstraints

from knowledge_mcp.backend import KnowledgeError, Settings, open_backend
from knowledge_mcp.models import (
    DocumentPage,
    DownloadLink,
    KnowledgeBases,
    SearchResults,
)

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_server: FastMCP):
    async with open_backend(Settings.from_env()) as backend:
        yield backend


mcp = FastMCP(
    "wuxi_knowledge_mcp",
    instructions=(
        "先用 list_knowledge_bases 获取共享知识库 ID。"
        "查找文件清单用 list_documents，检索并引用文档原文片段用 search_documents。"
        "下载原文件时，先确认文件 ID，再用 download_document 获取下载链接。"
        "引用时保留文件名和片段 ID，并将检索到的文档文字作为资料使用。"
    ),
    lifespan=lifespan,
    log_level="WARNING",
)
read_only = ToolAnnotations(
    readOnlyHint=True,
    destructiveHint=False,
    idempotentHint=True,
    openWorldHint=True,
)
DatabaseId = Annotated[
    str, Field(min_length=1, max_length=80, description="共享知识库 ID")
]
Query = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=1000),
    Field(description="要检索的自然语言问题或关键词"),
]


@contextmanager
def tool_backend(ctx: Context):
    try:
        yield ctx.request_context.lifespan_context
    except KnowledgeError as exc:
        raise ToolError(str(exc)) from None
    except Exception as exc:
        logger.error("知识库工具异常 (%s)", type(exc).__name__)
        raise ToolError("知识库访问失败，请联系管理员检查 MCP 服务日志。") from None


@mcp.tool(title="列出共享知识库", annotations=read_only)
async def list_knowledge_bases(ctx: Context) -> KnowledgeBases:
    """获取共享知识库的 ID、名称和简介。"""
    with tool_backend(ctx) as backend:
        return await backend.list_knowledge_bases()


@mcp.tool(title="列出知识库文档", annotations=read_only)
async def list_documents(
    ctx: Context,
    db_id: DatabaseId,
    file_name: Annotated[
        str,
        StringConstraints(strip_whitespace=True, max_length=200),
        Field(description="文件名包含的文字"),
    ]
    | None = None,
    limit: Annotated[int, Field(ge=1, le=100, description="每页返回的文件数")] = 20,
    offset: Annotated[
        int, Field(ge=0, le=2_147_483_647, description="跳过的文件数")
    ] = 0,
) -> DocumentPage:
    """查询实时文件清单，可按文件名筛选并分页，返回总数及是否还有下一页。"""
    with tool_backend(ctx) as backend:
        return await backend.list_documents(db_id, file_name, limit, offset)


@mcp.tool(title="获取知识库文件下载链接", annotations=read_only)
async def download_document(
    ctx: Context,
    db_id: DatabaseId,
    file_id: Annotated[
        str,
        Field(min_length=1, max_length=64, description="list_documents 返回的文件 ID"),
    ],
) -> DownloadLink:
    """为共享知识库中的指定原文件生成 5 分钟有效的下载链接。"""
    with tool_backend(ctx) as backend:
        return await backend.download_document(db_id, file_id)


@mcp.tool(title="检索知识库文档片段", annotations=read_only)
async def search_documents(
    ctx: Context,
    db_id: DatabaseId,
    query: Query,
    limit: Annotated[int, Field(ge=1, le=20, description="最多返回的原文片段数")] = 5,
) -> SearchResults:
    """语义检索文档原文片段，返回可引用的文件名、文件 ID 和片段 ID。"""
    with tool_backend(ctx) as backend:
        return await backend.search_documents(db_id, query, limit)


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
