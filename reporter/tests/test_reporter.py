import asyncio
import json
import unittest
from contextlib import asynccontextmanager
from datetime import datetime
from decimal import Decimal
from unittest.mock import AsyncMock, Mock, patch

from mcp.server.fastmcp.exceptions import ToolError

from reporter import config, server


class ReporterTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.fetch = AsyncMock(return_value=[])

        @asynccontextmanager
        async def fake_connection():
            yield Mock(fetch=self.fetch)

        connection = patch.object(server, "get_db_connection", fake_connection)
        connection.start()
        self.addCleanup(connection.stop)

    async def test_station_name_is_one_scalar_binding(self):
        await server.get_gate_station_devices("某闸站")
        self.assertEqual(self.fetch.await_args.args[1:], ("某闸站",))

    async def test_decimal_statistics_remain_json_numbers(self):
        self.fetch.return_value = [
            {
                "type_id": 1,
                "type_name": "gate",
                "device_count": 2,
                "active_count": 1,
                "avg_value": Decimal("1.25"),
                "min_value": None,
                "max_value": Decimal("2.5"),
                "latest_time": datetime(2026, 11, 16),
            }
        ]
        row = json.loads(await server.get_gate_station_overview())["overview"][0]
        self.assertEqual(row["avg_value"], 1.25)
        self.assertIsNone(row["min_value"])
        self.assertEqual(row["latest_time"], "2026-11-16T00:00:00")

    async def test_gate_history_converts_utc_and_stably_paginates(self):
        self.fetch.return_value = [
            dict(
                id=record_id,
                device_id=1,
                device_name="闸门",
                station_id=2,
                station_name="站点",
                type_id=3,
                type_name="gate",
                value=Decimal("1.25"),
                status=True,
                data_time=datetime(2026, 11, 16, 1),
            )
            for record_id in (12, 11)
        ]
        page = await server.get_gate_station_history(
            "2026-11-15T16:00:00Z", "2026-11-17", "站点", "gate", limit=1
        )
        query, *parameters = self.fetch.await_args.args
        self.assertIn("create_time >= $1::timestamp", query)
        self.assertIn("create_time < $2::timestamp", query)
        self.assertIn("ORDER BY data_time DESC, id DESC", query)
        self.assertEqual(
            parameters[:4],
            [datetime(2026, 11, 16), datetime(2026, 11, 17), "站点", "gate"],
        )
        self.assertEqual(parameters[-2:], [2, 0])
        self.assertEqual(
            page.rows[0].data_time.isoformat(), "2026-11-16T01:00:00+08:00"
        )
        self.assertEqual(page.rows[0].value, 1.25)
        self.assertTrue(page.has_more)
        self.assertEqual(page.next_offset, 1)

    async def test_grouped_water_history_keeps_missing_metrics_null(self):
        self.fetch.return_value = [
            dict(
                station_id=2,
                station_name="站点",
                station_code="S2",
                bucket_start=datetime(2026, 11, 16),
                sample_count=2,
                cod_count=0,
                cod_min=None,
                cod_max=None,
                cod_avg=None,
                ammonia_count=1,
                ammonia_min=Decimal("1.5"),
                ammonia_max=Decimal("1.5"),
                ammonia_avg=Decimal("1.5"),
                oxygen_count=1,
                oxygen_min=Decimal("5"),
                oxygen_max=Decimal("5"),
                oxygen_avg=Decimal("5"),
            )
        ]
        page = await server.get_water_quality_history(
            "2026-11-16", "2026-11-17", group_by="day"
        )
        self.assertIn("date_trunc", self.fetch.await_args.args[0])
        self.assertIn("day", self.fetch.await_args.args[1:])
        self.assertEqual(page.rows[0].sample_count, 2)
        self.assertIsNone(page.rows[0].cod.avg)
        self.assertEqual(page.rows[0].ammonia_nitrogen.avg, 1.5)
        self.assertIsNone(page.next_offset)

    async def test_history_rejects_invalid_windows_before_querying(self):
        for start, end in [
            ("november", "2026-11-17"),
            ("2026-11-17", "2026-11-16"),
            ("2024-01-01", "2026-11-16"),
        ]:
            with self.subTest(start=start, end=end), self.assertRaises(ToolError):
                await server.get_gate_station_history(start, end)
        self.fetch.assert_not_awaited()


class DatabaseTests(unittest.IsolatedAsyncioTestCase):
    async def test_pool_keeps_uri_options_and_applies_read_only_deadlines(self):
        uri = "postgresql+asyncpg://reader:sample%23%3F@localhost:5432/sample?sslmode=require"
        pool = Mock(close=AsyncMock())

        async def create_pool(**_):
            await asyncio.sleep(0)
            return pool

        with (
            patch.dict("os.environ", {"DATABASE_URL": uri}, clear=True),
            patch.object(config, "_pool", None),
            patch.object(
                config.asyncpg, "create_pool", new=AsyncMock(side_effect=create_pool)
            ) as factory,
        ):
            one, two = await asyncio.gather(config.get_pool(), config.get_pool())
            self.assertIs(one, two)
            factory.assert_awaited_once()
            options = factory.await_args.kwargs
            self.assertEqual(
                options["dsn"], uri.replace("postgresql+asyncpg", "postgresql", 1)
            )
            self.assertEqual(options["timeout"], 30)
            self.assertEqual(options["command_timeout"], 30)
            self.assertEqual(
                options["server_settings"]["default_transaction_read_only"], "on"
            )
            await config.close_pool()
        pool.close.assert_awaited_once()

    async def test_pool_supports_legacy_literal_reserved_password_characters(self):
        uri = "postgresql+asyncpg://reader:sample#?@localhost:5432/sample"
        with (
            patch.dict("os.environ", {"DATABASE_URL": uri}, clear=True),
            patch.object(config, "_pool", None),
            patch.object(config.asyncpg, "create_pool", new=AsyncMock()) as factory,
        ):
            await config.get_pool()
        self.assertEqual(
            factory.await_args.kwargs["dsn"],
            "postgresql://reader:sample%23%3F@localhost:5432/sample",
        )

    async def test_pool_supports_legacy_literal_slash_in_password(self):
        for password, encoded in [
            ("sample/a", "sample%2Fa"),
            ("sample/a#?", "sample%2Fa%23%3F"),
        ]:
            uri = f"postgresql+asyncpg://reader:{password}@localhost:5432/sample?sslmode=require"
            with (
                self.subTest(password=password),
                patch.dict("os.environ", {"DATABASE_URL": uri}, clear=True),
                patch.object(config, "_pool", None),
                patch.object(config.asyncpg, "create_pool", new=AsyncMock()) as factory,
            ):
                await config.get_pool()
                self.assertEqual(
                    factory.await_args.kwargs["dsn"],
                    f"postgresql://reader:{encoded}@localhost:5432/sample?sslmode=require",
                )

    async def test_pool_preserves_slash_and_at_sign_in_uri_query(self):
        for scheme in ("postgresql", "postgresql+asyncpg"):
            tail = "localhost:5432/sample?application_name=one/two@host/three"
            with (
                self.subTest(scheme=scheme),
                patch.dict(
                    "os.environ", {"DATABASE_URL": f"{scheme}://{tail}"}, clear=True
                ),
                patch.object(config, "_pool", None),
                patch.object(config.asyncpg, "create_pool", new=AsyncMock()) as factory,
            ):
                await config.get_pool()
                self.assertEqual(
                    factory.await_args.kwargs["dsn"], f"postgresql://{tail}"
                )

    async def test_unavailable_database_hides_raw_connection_errors(self):
        with patch.object(
            config, "get_pool", new=AsyncMock(side_effect=OSError("private endpoint"))
        ):
            with self.assertRaises(ToolError) as error:
                async with config.get_db_connection():
                    self.fail("A broken pool should not yield a connection")
        self.assertNotIn("private endpoint", str(error.exception))
