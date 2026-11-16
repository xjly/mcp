import asyncio
import json
import sys
import unittest
from datetime import timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
from unittest.mock import patch

import httpx
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.exceptions import ToolError

from graph.native_query import query_native_graph, register_native_query


SETTINGS = {
    "WUXI_KG_API_BASE_URL": "https://wuxi.example/gateway/",
    "WUXI_KG_ACCESS_TOKEN": "test-token",
}
RESULT = {
    "kind": "graph_query_result",
    "status": "ok",
    "intent": "statistics",
    "answer_text": "共 12 条河道。",
    "nodes": [],
    "edges": [],
    "candidates": [],
    "meta": {
        "strategy": "template",
        "node_count": 0,
        "edge_count": 0,
        "truncated": False,
    },
}


def graph_frame(result, name="NativeGraph工具"):
    return {
        "status": "loading",
        "response": None,
        "msg": {
            "type": "tool",
            "name": name,
            "content": json.dumps(result),
        },
    }


def text_frame(text):
    return {
        "status": "loading",
        "response": text,
        "msg": {"type": "AIMessageChunk", "content": text},
    }


def stream_body(*frames):
    return "".join(json.dumps(frame, ensure_ascii=False) + "\n" for frame in frames)


FINISHED = {"status": "finished", "response": None}


class NativeQueryTests(unittest.IsolatedAsyncioTestCase):
    async def test_native_query_calls_existing_graph_agent_and_preserves_evidence(self):
        def respond(request):
            self.assertEqual(request.method, "POST")
            self.assertEqual(
                str(request.url),
                "https://wuxi.example/gateway/api/chat/agent/MiniAgent",
            )
            self.assertEqual(request.headers["Authorization"], "Bearer test-token")
            self.assertEqual(
                json.loads(request.content),
                {"query": "有多少条河道？"},
            )
            return httpx.Response(
                200,
                content=stream_body(
                    {"status": "init"},
                    graph_frame(RESULT),
                    text_frame("助手的概述"),
                    FINISHED,
                ),
            )

        client = httpx.AsyncClient(transport=httpx.MockTransport(respond))
        with (
            patch.dict("os.environ", SETTINGS, clear=True),
            patch("graph.native_query.httpx.AsyncClient", return_value=client),
        ):
            response = await query_native_graph("  有多少条河道？  ", 12)
        self.assertEqual(response.model_dump(), RESULT)

    async def test_native_query_keeps_clarification_as_a_business_result(self):
        body = RESULT | {
            "status": "clarification",
            "candidates": [{"name": "同名河道"}],
        }
        client = httpx.AsyncClient(
            transport=httpx.MockTransport(
                lambda _: httpx.Response(
                    200, content=stream_body(graph_frame(body), FINISHED)
                )
            )
        )
        with (
            patch.dict("os.environ", SETTINGS, clear=True),
            patch("graph.native_query.httpx.AsyncClient", return_value=client),
        ):
            result = await query_native_graph("同名河道在哪里？", 20)
        self.assertEqual(result.status, "clarification")
        self.assertEqual(result.candidates, body["candidates"])

    async def test_answer_only_stream_is_marked_as_agent_text(self):
        body = stream_body(text_frame("图谱助手"), text_frame("的回答。"), FINISHED)
        client = httpx.AsyncClient(
            transport=httpx.MockTransport(lambda _: httpx.Response(200, content=body))
        )
        with (
            patch.dict("os.environ", SETTINGS, clear=True),
            patch("graph.native_query.httpx.AsyncClient", return_value=client),
        ):
            result = await query_native_graph("查询河道")
        self.assertEqual(result.answer_text, "图谱助手的回答。")
        self.assertEqual(result.kind, "agent_answer")
        self.assertEqual(result.intent, "agent_answer")
        self.assertEqual(result.nodes, [])

    async def test_statistics_preserve_the_tool_facts_and_source(self):
        statistics = {
            "kind": "graph_statistics",
            "source": "Neo4j 实时业务图谱",
            "as_of": "2026-11-16T00:00:00+00:00",
            "facts": {"节点总数": 12},
            "answer_text": "共有 12 个节点。",
        }
        body = stream_body(
            graph_frame(statistics, name="图谱节点实时统计"),
            text_frame("约有十几个节点。"),
            FINISHED,
        )
        client = httpx.AsyncClient(
            transport=httpx.MockTransport(lambda _: httpx.Response(200, content=body))
        )
        with (
            patch.dict("os.environ", SETTINGS, clear=True),
            patch("graph.native_query.httpx.AsyncClient", return_value=client),
        ):
            result = await query_native_graph("图谱一共有多少节点？")
        self.assertEqual(result.kind, "graph_statistics")
        self.assertEqual(result.answer_text, statistics["answer_text"])
        self.assertEqual(result.meta["source"], statistics["source"])
        self.assertEqual(result.meta["facts"], statistics["facts"])

    async def test_top_k_caps_nodes_and_excludes_dangling_edges(self):
        body = RESULT | {
            "nodes": [{"id": "a"}, {"id": "b"}, {"id": "c"}],
            "edges": [{"source": "a", "target": "b"}, {"source": "b", "target": "c"}],
        }
        client = httpx.AsyncClient(
            transport=httpx.MockTransport(
                lambda _: httpx.Response(
                    200, content=stream_body(graph_frame(body), FINISHED)
                )
            )
        )
        with (
            patch.dict("os.environ", SETTINGS, clear=True),
            patch("graph.native_query.httpx.AsyncClient", return_value=client),
        ):
            result = await query_native_graph("查相邻河道", 2)
        self.assertEqual(result.nodes, body["nodes"][:2])
        self.assertEqual(result.edges, body["edges"][:1])
        self.assertEqual(result.meta["node_count"], 2)
        self.assertTrue(result.meta["truncated"])

    async def test_api_errors_are_protocol_tool_errors_without_response_details(self):
        for response, message in [
            (httpx.Response(401, json={"detail": "internal fixture"}), "令牌"),
            (httpx.Response(404), "接口"),
            (
                httpx.Response(
                    200,
                    content=stream_body(
                        graph_frame(RESULT | {"status": "error"}), FINISHED
                    ),
                ),
                "图谱查询失败",
            ),
            (
                httpx.Response(
                    200,
                    content=stream_body(
                        graph_frame(
                            {"kind": "graph_statistics_error"}, name="图谱节点实时统计"
                        ),
                        text_frame("暂时无法统计。"),
                        FINISHED,
                    ),
                ),
                "图谱统计失败",
            ),
            (
                httpx.Response(
                    200,
                    content=stream_body(
                        {"status": "error", "error_type": "no_department"}
                    ),
                ),
                "部门",
            ),
            (
                httpx.Response(
                    200,
                    content=stream_body(graph_frame(RESULT), {"status": "interrupted"}),
                ),
                "中断",
            ),
            (httpx.Response(200, content=stream_body(text_frame("未收完"))), "未结束"),
            (httpx.Response(200, content="<html>internal fixture</html>"), "响应格式"),
        ]:
            with self.subTest(status=response.status_code, message=message):
                client = httpx.AsyncClient(
                    transport=httpx.MockTransport(lambda _: response)
                )
                with (
                    patch.dict("os.environ", SETTINGS, clear=True),
                    patch("graph.native_query.httpx.AsyncClient", return_value=client),
                    self.assertRaisesRegex(ToolError, message) as raised,
                ):
                    await query_native_graph("有多少条河道？", 20)
                self.assertNotIn("internal fixture", str(raised.exception))

    async def test_mcp_schema_validates_before_outbound_requests(self):
        mcp = FastMCP("test")
        register_native_query(mcp)
        tool = (await mcp.list_tools())[0]
        self.assertEqual(tool.name, "query_native_graph")
        self.assertFalse(tool.annotations.readOnlyHint)
        self.assertFalse(tool.annotations.idempotentHint)
        with patch("graph.native_query.httpx.AsyncClient") as client:
            with self.assertRaises(ToolError):
                await mcp.call_tool(
                    "query_native_graph", {"user_query": "   ", "top_k": 10}
                )
            client.assert_not_called()

    async def test_invalid_origin_does_not_make_an_outbound_request(self):
        settings = SETTINGS | {
            "WUXI_KG_API_BASE_URL": "https://wuxi.example/?key=ignored"
        }
        with (
            patch.dict("os.environ", settings, clear=True),
            patch("graph.native_query.httpx.AsyncClient") as client,
            self.assertRaisesRegex(ToolError, "WUXI_KG_API_BASE_URL"),
        ):
            await query_native_graph("问一下图谱")
        client.assert_not_called()

    async def test_stdio_dispatches_natural_language_to_the_configured_http_service(
        self,
    ):
        request_log = []

        class GraphEndpoint(BaseHTTPRequestHandler):
            def do_POST(self):
                payload = json.loads(
                    self.rfile.read(int(self.headers["Content-Length"]))
                )
                request_log.append(
                    (self.path, self.headers.get("Authorization"), payload)
                )
                body = stream_body(graph_frame(RESULT), FINISHED).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *_):
                pass

        with ThreadingHTTPServer(("127.0.0.1", 0), GraphEndpoint) as endpoint:
            worker = Thread(target=endpoint.serve_forever, daemon=True)
            worker.start()
            try:
                params = StdioServerParameters(
                    command=sys.executable,
                    args=["-B", "-c", "from graph.server import main; main()"],
                    env=SETTINGS
                    | {
                        "WUXI_KG_API_BASE_URL": f"http://127.0.0.1:{endpoint.server_port}"
                    },
                )
                async with asyncio.timeout(20), stdio_client(params) as (read, write):
                    async with ClientSession(
                        read, write, read_timeout_seconds=timedelta(seconds=15)
                    ) as session:
                        await session.initialize()
                        tools = {
                            tool.name for tool in (await session.list_tools()).tools
                        }
                        self.assertIn("query_native_graph", tools)
                        self.assertNotIn("execute_read_cypher", tools)
                        success = await session.call_tool(
                            "query_native_graph", {"user_query": "河道一共有多少？"}
                        )
                        self.assertFalse(success.isError)
                        self.assertEqual(success.structuredContent, RESULT)
            finally:
                await asyncio.to_thread(endpoint.shutdown)
                worker.join(timeout=2)
        self.assertEqual(
            request_log,
            [
                (
                    "/api/chat/agent/MiniAgent",
                    "Bearer test-token",
                    {"query": "河道一共有多少？"},
                )
            ],
        )
