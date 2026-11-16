import asyncio
import math
import os
from collections.abc import AsyncIterator, Callable, Mapping, Sequence
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from urllib.parse import urlsplit

import asyncpg
import httpx
from pymilvus import MilvusClient

from .models import (
    Document,
    DocumentPage,
    KnowledgeBase,
    KnowledgeBases,
    SearchMatch,
    SearchResults,
)

IO_TIMEOUT = 15.0
EXCERPT_LENGTH = 3000

_DATABASE_SQL = """
    SELECT db_id, name, description, kb_type, embedding_model_id, embedding_model, embedding_dimension
    FROM mcp_kb.databases
    WHERE db_id = $1
"""
_DOCUMENT_PAGE_SQL = """
    WITH matched AS (
        SELECT file_id, file_name, original_file_name, file_type, status
        FROM mcp_kb.documents
        WHERE db_id = $1 AND (
            $2::text IS NULL
            OR strpos(lower(file_name), lower($2)) > 0
            OR strpos(lower(original_file_name), lower($2)) > 0
        )
    ), page AS (
        SELECT * FROM matched
        ORDER BY lower(file_name), file_id
        LIMIT $3 OFFSET $4
    )
    SELECT page.*, totals.total
    FROM (SELECT count(*) AS total FROM matched) AS totals
    LEFT JOIN page ON true
    ORDER BY lower(page.file_name), page.file_id
"""
_SEARCH_DOCUMENTS_SQL = """
    SELECT file_id, file_name, original_file_name
    FROM mcp_kb.documents
    WHERE db_id = $1 AND file_id = ANY($2::text[])
"""


class KnowledgeError(ValueError):
    """A failure with a message suitable for a knowledge tool caller."""


@dataclass(frozen=True)
class Settings:
    db_id: str
    postgres_dsn: str = field(repr=False)
    milvus_uri: str = field(repr=False)
    milvus_database: str
    milvus_token: str = field(repr=False)
    embedding_url: str = field(repr=False)
    embedding_api_key: str = field(default="", repr=False)

    @classmethod
    def from_env(cls) -> "Settings":
        db_id = _require_env("WUXI_KG_DB_ID")
        postgres_dsn = _require_env("WUXI_KG_POSTGRES_DSN")
        if not postgres_dsn.startswith(("postgresql://", "postgres://")):
            raise KnowledgeError(
                "WUXI_KG_POSTGRES_DSN 必须使用 PostgreSQL 连接字符串。"
            )
        return cls(
            db_id=db_id,
            postgres_dsn=postgres_dsn,
            milvus_uri=_require_http_url("WUXI_KG_MILVUS_URI"),
            milvus_database=_require_env("WUXI_KG_MILVUS_DATABASE"),
            milvus_token=_require_env("WUXI_KG_MILVUS_TOKEN"),
            embedding_url=_require_http_url("WUXI_KG_EMBEDDING_URL"),
            embedding_api_key=os.environ.get("WUXI_KG_EMBEDDING_API_KEY", "").strip(),
        )


def _require_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise KnowledgeError(f"请设置环境变量 {name}。")
    return value


def _require_http_url(name: str) -> str:
    value = _require_env(name)
    try:
        url = urlsplit(value)
        if url.scheme in {"http", "https"} and url.hostname and url.username is None:
            return value
    except ValueError:
        pass
    raise KnowledgeError(f"{name} 必须使用完整的 HTTP 或 HTTPS 服务地址。")


class KnowledgeBackend:
    def __init__(
        self,
        settings: Settings,
        *,
        postgres: asyncpg.Pool,
        http: httpx.AsyncClient,
        milvus: MilvusClient | None = None,
    ) -> None:
        self._settings = settings
        self._postgres = postgres
        self._milvus = milvus
        self._milvus_lock = asyncio.Lock()
        self._http = http

    async def list_knowledge_bases(self) -> KnowledgeBases:
        database = await self._configured_database(self._settings.db_id)
        return KnowledgeBases(databases=[KnowledgeBase.model_validate(dict(database))])

    async def list_documents(
        self, db_id: str, file_name: str | None = None, limit: int = 20, offset: int = 0
    ) -> DocumentPage:
        if not 1 <= limit <= 100 or offset < 0:
            raise KnowledgeError(
                "文档列表的 limit 须在 1 至 100 之间，offset 须为非负整数。"
            )
        file_name = (file_name or "").strip() or None
        if file_name and len(file_name) > 200:
            raise KnowledgeError("文件名筛选条件最多 200 个字符。")
        await self._configured_database(db_id)
        rows = await self._fetch(_DOCUMENT_PAGE_SQL, db_id, file_name, limit, offset)
        total = rows[0]["total"]
        files = [
            Document.model_validate(dict(row))
            for row in rows
            if row["file_id"] is not None
        ]
        return DocumentPage(
            db_id=db_id,
            files=files,
            limit=limit,
            offset=offset,
            total=total,
            has_more=offset + len(files) < total,
        )

    async def search_documents(
        self, db_id: str, query: str, limit: int = 5
    ) -> SearchResults:
        query = query.strip()
        if not 1 <= len(query) <= 1000:
            raise KnowledgeError("查询文本须在 1 至 1000 个字符之间。")
        if not 1 <= limit <= 20:
            raise KnowledgeError("检索的 limit 须在 1 至 20 之间。")

        database = await self._configured_database(db_id)
        model_id = database["embedding_model_id"]
        model = database["embedding_model"]
        dimension = database["embedding_dimension"]
        if not model_id or not model or not isinstance(dimension, int) or dimension < 1:
            raise KnowledgeError(
                "知识库缺少嵌入模型标识、模型名或有效维度，请检查 PostgreSQL 视图。"
            )

        milvus = await self._milvus_client()
        collection = await _call_milvus(
            milvus.describe_collection, collection_name=db_id
        )
        vector_field = next(
            (item for item in collection["fields"] if item["name"] == "embedding"), None
        )
        if not vector_field or str(vector_field.get("params", {}).get("dim")) != str(
            dimension
        ):
            raise KnowledgeError("Milvus 集合的 embedding 字段维度与知识库配置不一致。")

        vector = await self._embed(query, model_id, model, dimension)
        hits = await _call_milvus(
            milvus.search,
            collection_name=db_id,
            data=[vector],
            anns_field="embedding",
            limit=limit,
            output_fields=["content", "file_id", "chunk_id", "chunk_index"],
            search_params={"metric_type": "COSINE", "params": {"nprobe": 10}},
        )
        scoped_hits = await self._match_documents(db_id, hits[0] if hits else [])
        return SearchResults(db_id=db_id, matches=scoped_hits)

    async def _milvus_client(self) -> MilvusClient:
        async with self._milvus_lock:
            if self._milvus is None:
                self._milvus = await _call_milvus(
                    MilvusClient,
                    uri=self._settings.milvus_uri,
                    db_name=self._settings.milvus_database,
                    token=self._settings.milvus_token,
                )
            return self._milvus

    async def _close_milvus(self) -> None:
        if self._milvus is not None:
            await asyncio.to_thread(self._milvus.close)

    async def _configured_database(self, db_id: str) -> asyncpg.Record:
        if db_id != self._settings.db_id:
            raise KnowledgeError(
                "该知识库未开放给此 MCP 实例。请先调用 list_knowledge_bases。"
            )
        try:
            row = await self._postgres.fetchrow(
                _DATABASE_SQL, db_id, timeout=IO_TIMEOUT
            )
        except Exception:
            raise KnowledgeError(
                "读取知识库元数据失败，请检查 PostgreSQL 连接及只读视图权限。"
            ) from None
        if row is None:
            raise KnowledgeError(
                "未找到配置的知识库，请检查 WUXI_KG_DB_ID 及 PostgreSQL 视图范围。"
            )
        if row["kb_type"] != "milvus":
            raise KnowledgeError("此 MCP 实例要求选择一个 Milvus 文档知识库。")
        return row

    async def _fetch(self, query: str, *args: object) -> list[asyncpg.Record]:
        try:
            return await self._postgres.fetch(query, *args, timeout=IO_TIMEOUT)
        except Exception:
            raise KnowledgeError(
                "读取文档元数据失败，请检查 PostgreSQL 连接及只读视图权限。"
            ) from None

    async def _embed(
        self, query: str, model_id: str, model: str, dimension: int
    ) -> list[float]:
        headers = {}
        if self._settings.embedding_api_key:
            headers["Authorization"] = f"Bearer {self._settings.embedding_api_key}"
        try:
            async with asyncio.timeout(IO_TIMEOUT):
                response = await self._http.post(
                    self._settings.embedding_url,
                    json={"model": model, "input": [query]},
                    headers=headers,
                )
            response.raise_for_status()
            payload = response.json()
            if model_id.startswith("ollama/"):
                vector = payload["embeddings"][0]
            else:
                vector = payload["data"][0]["embedding"]
        except (
            httpx.HTTPError,
            httpx.InvalidURL,
            TimeoutError,
            ValueError,
            TypeError,
            KeyError,
            IndexError,
        ):
            raise KnowledgeError(
                "嵌入请求失败，请检查嵌入服务地址、凭证和知识库模型配置。"
            ) from None

        if (
            not isinstance(vector, list)
            or len(vector) != dimension
            or not all(_is_finite_number(value) for value in vector)
            or not any(vector)
        ):
            raise KnowledgeError("嵌入服务返回的向量无效，请核对模型及向量维度。")
        return vector

    async def _match_documents(
        self, db_id: str, hits: Sequence[Mapping]
    ) -> list[SearchMatch]:
        candidates = []
        for hit in hits:
            entity = hit.get("entity", {})
            file_id = entity.get("file_id")
            content = entity.get("content")
            if (
                isinstance(file_id, str)
                and file_id
                and isinstance(content, str)
                and content.strip()
            ):
                candidates.append((file_id, content, entity, hit.get("distance")))
        if not candidates:
            return []

        file_ids = list(dict.fromkeys(file_id for file_id, *_ in candidates))
        rows = await self._fetch(_SEARCH_DOCUMENTS_SQL, db_id, file_ids)
        file_names = {
            row["file_id"]: row["original_file_name"] or row["file_name"]
            for row in rows
        }
        matches = []
        for file_id, content, entity, score in candidates:
            if file_id not in file_names:
                continue
            chunk_id = entity.get("chunk_id")
            chunk_index = entity.get("chunk_index")
            matches.append(
                SearchMatch(
                    content=content[:EXCERPT_LENGTH],
                    truncated=len(content) > EXCERPT_LENGTH,
                    file_id=file_id,
                    file_name=file_names[file_id],
                    chunk_id=chunk_id
                    if isinstance(chunk_id, str) and chunk_id
                    else None,
                    chunk_index=chunk_index
                    if type(chunk_index) is int and chunk_index >= 0
                    else None,
                    score=score if _is_finite_number(score) else None,
                )
            )
        return matches


def _is_finite_number(value: object) -> bool:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    try:
        return math.isfinite(value)
    except OverflowError:
        return False


async def _call_milvus[T](operation: Callable[..., T], **kwargs: object) -> T:
    try:
        async with asyncio.timeout(IO_TIMEOUT):
            return await asyncio.to_thread(operation, **kwargs, timeout=IO_TIMEOUT)
    except Exception:
        raise KnowledgeError(
            "Milvus 检索服务调用失败，请检查连接、只读权限及集合加载状态。"
        ) from None


@asynccontextmanager
async def open_backend(settings: Settings) -> AsyncIterator[KnowledgeBackend]:
    try:
        postgres = await asyncpg.create_pool(
            dsn=settings.postgres_dsn,
            min_size=0,
            max_size=4,
            timeout=IO_TIMEOUT,
            command_timeout=IO_TIMEOUT,
            server_settings={"default_transaction_read_only": "on"},
        )
    except Exception:
        raise KnowledgeError(
            "无法连接 PostgreSQL，请检查 WUXI_KG_POSTGRES_DSN。"
        ) from None

    try:
        async with httpx.AsyncClient(timeout=IO_TIMEOUT) as http:
            backend = KnowledgeBackend(settings, postgres=postgres, http=http)
            try:
                yield backend
            finally:
                await backend._close_milvus()
    finally:
        await asyncio.wait_for(postgres.close(), timeout=IO_TIMEOUT)
