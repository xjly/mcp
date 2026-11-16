import asyncio
import socket
import sys
from textwrap import dedent

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


def test_stdio_discovery_structured_results_and_errors(tmp_path):
    launcher = tmp_path / "launch.py"
    launcher.write_text(
        dedent(
            """
            from contextlib import asynccontextmanager

            from knowledge_mcp import server
            from knowledge_mcp.backend import KnowledgeError
            from knowledge_mcp.models import DocumentPage, KnowledgeBases, SearchResults

            class Backend:
                async def list_knowledge_bases(self):
                    return KnowledgeBases(databases=[])

                async def list_documents(self, db_id, file_name, limit, offset):
                    return DocumentPage(
                        db_id=db_id, files=[], limit=limit, offset=offset,
                        total=0, has_more=False,
                    )

                async def search_documents(self, db_id, query, limit):
                    if db_id != "shared":
                        raise KnowledgeError("查询超出共享知识库范围")
                    if query != "水网":
                        raise KnowledgeError("查询参数未按约定传入")
                    return SearchResults(db_id=db_id, matches=[])

                async def download_document(self, db_id, file_id):
                    from knowledge_mcp.models import DownloadLink
                    if db_id != "shared" or file_id != "fixture":
                        raise KnowledgeError("未找到该文件")
                    return DownloadLink(
                        db_id=db_id, file_id=file_id, file_name="guide.pdf",
                        download_url="https://storage.example/guide.pdf?signed",
                        expires_in_seconds=300,
                    )

            @asynccontextmanager
            async def open_fixture(settings):
                yield Backend()

            server.Settings.from_env = staticmethod(lambda: None)
            server.open_backend = open_fixture
            server.main()
            """
        ),
        encoding="utf-8",
    )

    async def exercise():
        params = StdioServerParameters(command=sys.executable, args=[str(launcher)])
        async with asyncio.timeout(20), stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                descriptions = {
                    tool.name: tool for tool in (await session.list_tools()).tools
                }
                assert set(descriptions) == {
                    "list_knowledge_bases",
                    "list_documents",
                    "search_documents",
                    "download_document",
                }
                for tool in descriptions.values():
                    assert tool.annotations.readOnlyHint is True
                    assert tool.outputSchema

                libraries = await session.call_tool("list_knowledge_bases")
                assert not libraries.isError
                assert libraries.structuredContent == {"databases": []}
                assert libraries.content

                page = await session.call_tool("list_documents", {"db_id": "shared"})
                assert not page.isError
                assert page.structuredContent["files"] == []
                assert page.structuredContent["limit"] == 20

                matches = await session.call_tool(
                    "search_documents", {"db_id": "shared", "query": "  水网  "}
                )
                assert not matches.isError
                assert matches.structuredContent == {"db_id": "shared", "matches": []}

                download = await session.call_tool(
                    "download_document", {"db_id": "shared", "file_id": "fixture"}
                )
                assert not download.isError
                assert download.structuredContent["file_name"] == "guide.pdf"
                assert download.structuredContent["expires_in_seconds"] == 300
                missing = await session.call_tool(
                    "download_document", {"db_id": "shared", "file_id": "missing"}
                )
                assert missing.isError

                for invalid in [
                    {"db_id": "other", "query": "水网"},
                    {"db_id": "shared", "query": "   "},
                    {"db_id": "shared", "query": "水网", "limit": 21},
                ]:
                    failed = await session.call_tool("search_documents", invalid)
                    assert failed.isError

    asyncio.run(exercise())


def test_postgres_outage_is_reported_as_tool_error():
    async def exercise(port):
        params = StdioServerParameters(
            command=sys.executable,
            args=["-m", "knowledge_mcp.server"],
            env={
                "WUXI_KG_DB_ID": "shared",
                "WUXI_KG_POSTGRES_DSN": f"postgresql://fixture:fixture@127.0.0.1:{port}/fixture",
                "WUXI_KG_MILVUS_URI": f"http://127.0.0.1:{port}",
                "WUXI_KG_MILVUS_DATABASE": "default",
                "WUXI_KG_MILVUS_TOKEN": "fixture:fixture",
                "WUXI_KG_EMBEDDING_URL": f"http://127.0.0.1:{port}/v1/embeddings",
            },
        )
        async with asyncio.timeout(20), stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                assert len((await session.list_tools()).tools) == 4
                failed = await session.call_tool("list_knowledge_bases")
                assert failed.isError
                assert "PostgreSQL" in failed.content[0].text
                assert "postgresql://" not in failed.content[0].text

    with socket.socket() as reserved_port:
        reserved_port.bind(("127.0.0.1", 0))
        asyncio.run(exercise(reserved_port.getsockname()[1]))
