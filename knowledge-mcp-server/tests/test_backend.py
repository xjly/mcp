import json
import unittest
from dataclasses import replace
from unittest.mock import AsyncMock, Mock, patch

import httpx

from knowledge_mcp.backend import (
    KnowledgeBackend,
    KnowledgeError,
    Settings,
    open_backend,
)
from knowledge_mcp.downloads import DownloadSettings


CONFIG = {
    "WUXI_KG_DB_ID": "kb_water",
    "WUXI_KG_POSTGRES_DSN": "postgresql://readonly:pg-secret@pg.example/kb",
    "WUXI_KG_MILVUS_URI": "http://milvus.example:19530",
    "WUXI_KG_MILVUS_DATABASE": "knowledge",
    "WUXI_KG_MILVUS_TOKEN": "reader:milvus-secret",
    "WUXI_KG_EMBEDDING_URL": "https://embedding.example/v1/embeddings",
    "WUXI_KG_EMBEDDING_API_KEY": "embedding-secret",
}
KB = {
    "db_id": "kb_water",
    "name": "水务知识库",
    "description": None,
    "kb_type": "milvus",
    "embedding_model_id": "vendor/team/model",
    "embedding_model": "deployed-model",
    "embedding_dimension": 2,
}


class SettingsTests(unittest.TestCase):
    def test_requires_database_scope(self):
        env = {key: value for key, value in CONFIG.items() if key != "WUXI_KG_DB_ID"}
        with (
            patch.dict("os.environ", env, clear=True),
            self.assertRaisesRegex(KnowledgeError, "WUXI_KG_DB_ID"),
        ):
            Settings.from_env()

    def test_repr_does_not_show_credentials(self):
        with patch.dict("os.environ", CONFIG, clear=True):
            settings = Settings.from_env()
        self.assertNotIn("secret", repr(settings))


class KnowledgeBackendTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.postgres = Mock(fetchrow=AsyncMock(return_value=KB), fetch=AsyncMock())
        self.milvus = Mock(
            describe_collection=Mock(
                return_value={"fields": [{"name": "embedding", "params": {"dim": 2}}]}
            ),
            search=Mock(return_value=[[]]),
        )
        self.requests = []
        self.embedding_response = {"data": [{"index": 0, "embedding": [0.6, 0.8]}]}

        def embed(request):
            self.requests.append(request)
            return httpx.Response(200, json=self.embedding_response)

        self.http = httpx.AsyncClient(transport=httpx.MockTransport(embed))
        self.addAsyncCleanup(self.http.aclose)
        with patch.dict("os.environ", CONFIG, clear=True):
            settings = Settings.from_env()
        self.backend = KnowledgeBackend(
            settings, postgres=self.postgres, milvus=self.milvus, http=self.http
        )

    async def test_lists_only_public_metadata_for_configured_library(self):
        result = await self.backend.list_knowledge_bases()
        self.assertEqual(
            result.model_dump(),
            {
                "databases": [
                    {
                        key: KB[key]
                        for key in ("db_id", "name", "description", "kb_type")
                    }
                ]
            },
        )
        self.assertEqual(self.postgres.fetchrow.await_args.args[1:], ("kb_water",))

    async def test_rejects_out_of_scope_library_before_network_calls(self):
        with self.assertRaises(KnowledgeError):
            await self.backend.search_documents("kb_other", "query", 5)
        self.postgres.fetchrow.assert_not_awaited()
        self.milvus.search.assert_not_called()
        self.assertEqual(self.requests, [])

    async def test_download_rejects_another_library_before_looking_up_file(self):
        with self.assertRaisesRegex(KnowledgeError, "该知识库未开放"):
            await self.backend.download_document("kb_other", "file-1")
        self.postgres.fetchrow.assert_not_awaited()

    async def test_download_returns_a_link_for_the_scoped_file(self):
        record = {
            "file_name": "水务手册.pdf",
            "file_type": "pdf",
            "storage_path": "http://minio.internal/ref-kb-water/guide.pdf",
        }
        self.postgres.fetchrow.side_effect = [KB, record]
        signed = "https://minio.example/ref-kb-water/guide.pdf?X-Amz-Signature=signed"
        settings = replace(
            self.backend._settings,
            downloads=DownloadSettings(
                "https://minio.example", "reader", "fixture-secret"
            ),
        )
        with patch("knowledge_mcp.backend.DownloadStorage") as storage:
            storage.return_value.download_url = AsyncMock(return_value=signed)
            backend = KnowledgeBackend(settings, postgres=self.postgres, http=self.http)
            result = await backend.download_document("kb_water", "file-1")
        self.assertEqual(
            self.postgres.fetchrow.await_args.args[1:], ("kb_water", "file-1")
        )
        self.assertEqual(storage.call_args.kwargs["bucket"], "ref-kb-water")
        storage.return_value.download_url.assert_awaited_once_with(
            record["storage_path"], record["file_name"]
        )
        self.assertEqual(
            result.model_dump(),
            {
                "db_id": "kb_water",
                "file_id": "file-1",
                "file_name": "水务手册.pdf",
                "download_url": signed,
                "expires_in_seconds": 300,
            },
        )

    async def test_download_reports_missing_storage_config_without_querying_download_view(
        self,
    ):
        with self.assertRaisesRegex(KnowledgeError, "WUXI_KG_MINIO_URL"):
            await self.backend.download_document("kb_water", "file-1")
        self.assertEqual(self.postgres.fetchrow.await_count, 1)

    async def test_download_rejects_metadata_without_a_stored_original(self):
        self.postgres.fetchrow.side_effect = [
            KB,
            {"file_name": "外部链接", "file_type": "url", "storage_path": None},
        ]
        settings = replace(
            self.backend._settings,
            downloads=DownloadSettings(
                "https://minio.example", "reader", "fixture-secret"
            ),
        )
        backend = KnowledgeBackend(settings, postgres=self.postgres, http=self.http)
        with self.assertRaisesRegex(KnowledgeError, "没有可通过 MCP 下载"):
            await backend.download_document("kb_water", "file-1")

    async def test_pagination_keeps_total_for_offset_past_end(self):
        self.postgres.fetch.return_value = [{"file_id": None, "total": 3}]
        page = await self.backend.list_documents("kb_water", "%_", 2, 5)
        self.assertEqual(page.files, [])
        self.assertEqual(page.total, 3)
        self.assertFalse(page.has_more)
        self.assertEqual(
            self.postgres.fetch.await_args.args[1:], ("kb_water", "%_", 2, 5)
        )

    async def test_pagination_exposes_document_metadata(self):
        self.postgres.fetch.return_value = [
            {
                "file_id": "file-1",
                "file_name": "水务手册.pdf",
                "original_file_name": None,
                "file_type": "pdf",
                "status": "indexed",
                "total": 2,
            }
        ]
        page = await self.backend.list_documents("kb_water", None, 1, 0)
        self.assertEqual(page.files[0].file_name, "水务手册.pdf")
        self.assertTrue(page.has_more)

    async def test_search_uses_indexed_model_and_returns_scoped_metadata(self):
        content = "水务" * 1600
        self.milvus.search.return_value = [
            [
                {
                    "id": "key-1",
                    "distance": 0.8,
                    "entity": {
                        "file_id": "file-1",
                        "content": content,
                        "chunk_id": "chunk-1",
                        "chunk_index": 0,
                        "source": "/internal/storage",
                    },
                },
                {
                    "id": "key-2",
                    "distance": 0.7,
                    "entity": {
                        "file_id": "other-library",
                        "content": "outside scope",
                        "chunk_id": "chunk-2",
                        "chunk_index": 1,
                    },
                },
            ]
        ]
        self.postgres.fetch.return_value = [
            {
                "file_id": "file-1",
                "file_name": "水务手册.pdf",
                "original_file_name": "水务手册原件.pdf",
            }
        ]
        result = await self.backend.search_documents("kb_water", "  查询资料  ", 5)
        self.assertEqual(len(result.matches), 1)
        match = result.matches[0]
        self.assertEqual(
            (
                match.file_id,
                match.file_name,
                match.chunk_id,
                match.chunk_index,
                match.score,
            ),
            ("file-1", "水务手册原件.pdf", "chunk-1", 0, 0.8),
        )
        self.assertEqual(len(match.content), 3000)
        self.assertTrue(match.truncated)
        self.assertNotIn("/internal/storage", result.model_dump_json())
        self.assertEqual(
            json.loads(self.requests[0].content),
            {"model": "deployed-model", "input": ["查询资料"]},
        )
        self.assertEqual(
            self.requests[0].headers["Authorization"], "Bearer embedding-secret"
        )
        self.assertEqual(
            self.postgres.fetch.await_args.args[1:],
            ("kb_water", ["file-1", "other-library"]),
        )
        self.assertEqual(
            self.milvus.search.call_args.kwargs["collection_name"], "kb_water"
        )
        self.assertEqual(
            self.milvus.search.call_args.kwargs["search_params"]["metric_type"],
            "COSINE",
        )

    async def test_no_milvus_matches_is_successful_empty_result(self):
        self.assertEqual(
            (await self.backend.search_documents("kb_water", "query", 5)).matches, []
        )

    async def test_ollama_embedding_protocol(self):
        self.postgres.fetchrow.return_value = KB | {
            "embedding_model_id": "ollama/model"
        }
        self.embedding_response = {"embeddings": [[0.6, 0.8]]}
        await self.backend.search_documents("kb_water", "query", 5)
        self.assertEqual(self.milvus.search.call_args.kwargs["data"], [[0.6, 0.8]])

    async def test_collection_dimension_mismatch_stops_before_sending_query_text(self):
        self.milvus.describe_collection.return_value = {
            "fields": [{"name": "embedding", "params": {"dim": 3}}]
        }
        with self.assertRaises(KnowledgeError):
            await self.backend.search_documents("kb_water", "query", 5)
        self.assertEqual(self.requests, [])
        self.milvus.search.assert_not_called()

    async def test_bad_embedding_stops_search(self):
        self.embedding_response = {"data": [{"index": 0, "embedding": [0.6]}]}
        with self.assertRaises(KnowledgeError):
            await self.backend.search_documents("kb_water", "query", 5)
        self.milvus.search.assert_not_called()

    async def test_out_of_range_embedding_value_is_a_tool_error(self):
        self.embedding_response = {"data": [{"index": 0, "embedding": [10**400, 0.6]}]}
        with self.assertRaises(KnowledgeError):
            await self.backend.search_documents("kb_water", "query", 5)
        self.milvus.search.assert_not_called()

    async def test_missing_embedding_model_stops_search(self):
        self.postgres.fetchrow.return_value = KB | {"embedding_model": None}
        with self.assertRaisesRegex(KnowledgeError, "嵌入模型"):
            await self.backend.search_documents("kb_water", "query", 5)
        self.assertEqual(self.requests, [])
        self.milvus.search.assert_not_called()

    async def test_upstream_failure_is_a_sanitized_error(self):
        self.milvus.search.side_effect = RuntimeError("upstream-secret")
        with self.assertRaises(KnowledgeError) as error:
            await self.backend.search_documents("kb_water", "query", 5)
        self.assertNotIn("upstream-secret", str(error.exception))
        self.assertTrue(error.exception.__suppress_context__)

    async def test_unavailable_milvus_does_not_block_listing_or_later_search(self):
        self.postgres.close = AsyncMock()
        with patch.dict("os.environ", CONFIG, clear=True):
            settings = Settings.from_env()

        with (
            patch(
                "knowledge_mcp.backend.asyncpg.create_pool",
                new_callable=AsyncMock,
                return_value=self.postgres,
            ) as create_pool,
            patch(
                "knowledge_mcp.backend.MilvusClient",
                side_effect=[RuntimeError("offline"), self.milvus],
            ) as connect,
            patch("knowledge_mcp.backend.httpx.AsyncClient", return_value=self.http),
        ):
            async with open_backend(settings) as backend:
                self.assertEqual(
                    (await backend.list_knowledge_bases()).databases[0].db_id,
                    "kb_water",
                )
                connect.assert_not_called()
                self.assertEqual(create_pool.await_args.kwargs["min_size"], 0)
                with self.assertRaises(KnowledgeError):
                    await backend.search_documents("kb_water", "query")
                self.assertEqual(
                    (await backend.search_documents("kb_water", "query")).matches, []
                )

        self.milvus.close.assert_called_once()
        self.postgres.close.assert_awaited_once()
