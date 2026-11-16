import json
import sys
import unittest
from datetime import timedelta
from pathlib import Path
from tempfile import TemporaryDirectory

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.types import TextContent


class ScheduleStdioTest(unittest.IsolatedAsyncioTestCase):
    async def test_schedule_stdout_contains_only_mcp_messages(self):
        protocol_errors: list[Exception] = []

        async def collect_protocol_errors(message):
            if isinstance(message, Exception):
                protocol_errors.append(message)

        with TemporaryDirectory() as directory:
            db_path = Path(directory) / "jobs.sqlite"
            server = StdioServerParameters(
                command=sys.executable,
                args=["-B", "-u", "-c", "from schedule.server import main; main()"],
                cwd=directory,
                env={
                    "JOB_STORE_TYPE": "sqlite",
                    "SQLITE_DB_PATH": str(db_path),
                    "SCHEDULER_TIMEZONE": "UTC",
                    "PYTHONIOENCODING": "utf-8",
                },
            )
            async with stdio_client(server) as (reader, writer):
                async with ClientSession(
                    reader,
                    writer,
                    read_timeout_seconds=timedelta(seconds=15),
                    message_handler=collect_protocol_errors,
                ) as session:
                    self.assertEqual((await session.initialize()).serverInfo.name, "schedule-mcp")
                    tools = await session.list_tools()
                    self.assertEqual({tool.name for tool in tools.tools}, {"schedule_task", "push_to_screen"})
                    result = await session.call_tool("schedule_task", {"action": "list"})
                    await session.send_ping()

            self.assertFalse(result.isError)
            item = result.content[0]
            self.assertIsInstance(item, TextContent)
            payload = json.loads(item.text)
            self.assertEqual(payload["status"], "success")
            self.assertEqual(payload["action"], "list")
            self.assertEqual(Path(payload["db_path"]).resolve(), db_path.resolve())

        self.assertEqual(len(protocol_errors), 0, "Schedule logs or other non-MCP lines were sent to stdout")
