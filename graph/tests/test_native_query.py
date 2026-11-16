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


class NativeQueryTests(unittest.IsolatedAsyncioTestCase):
    async def test_native_query_calls_wuxi_endpoint_and_preserves_answer(self):
        def respond(request):
            self.assertEqual(request.method, "POST")
            self.assertEqual(
                str(request.url),
                "https://wuxi.example/gateway/api/native-graph/mcp/query",
            )
            self.assertEqual(request.headers["Authorization"], "Bearer test-token")
            self.assertEqual(
                json.loads(request.content),
                {"user_query": "有多少条河道？", "top_k": 12},
            )
            return httpx.Response(200, json=RESULT)

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
            transport=httpx.MockTransport(lambda _: httpx.Response(200, json=body))
        )
        with (
            patch.dict("os.environ", SETTINGS, clear=True),
            patch("graph.native_query.httpx.AsyncClient", return_value=client),
        ):
            result = await query_native_graph("同名河道在哪里？", 20)
        self.assertEqual(result.status, "clarification")
        self.assertEqual(result.candidates, body["candidates"])

    async def test_api_errors_are_protocol_tool_errors_without_response_details(self):
        for response, message in [
            (httpx.Response(401, json={"detail": "internal fixture"}), "令牌"),
            (httpx.Response(404), "接口"),
            (httpx.Response(200, json=RESULT | {"status": "error"}), "图谱查询失败"),
            (httpx.Response(200, json={"detail": "internal fixture"}), "响应格式"),
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
        self.assertTrue(tool.annotations.readOnlyHint)
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
                body = json.dumps(RESULT, ensure_ascii=False).encode("utf-8")
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
                    "/api/native-graph/mcp/query",
                    "Bearer test-token",
                    {"user_query": "河道一共有多少？", "top_k": 20},
                )
            ],
        )
