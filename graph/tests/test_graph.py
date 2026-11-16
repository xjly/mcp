import json
import threading
import unittest
from unittest.mock import MagicMock, patch

from mcp.server.fastmcp.exceptions import ToolError
from neo4j import READ_ACCESS

from graph import server
from graph.repository import Neo4jGraphRepository


class Entity(dict):
    def __init__(self, element_id, **properties):
        super().__init__(properties)
        self.element_id = element_id


class Relationship(Entity):
    def __init__(self, element_id, start, end, **properties):
        super().__init__(element_id, **properties)
        self.start_node = start
        self.end_node = end
        self.type = "CONNECTED_TO"


class GraphRepositoryTests(unittest.TestCase):
    def test_query_timeout_and_row_cap_are_applied_to_the_driver(self):
        settings = {
            "NEO4J_URI": "bolt://127.0.0.1:7687",
            "NEO4J_USERNAME": "fixture",
            "NEO4J_PASSWORD": "fixture",
        }
        with patch.dict("os.environ", settings, clear=True):
            repository = Neo4jGraphRepository()

        driver = MagicMock()
        repository._driver = driver
        session = driver.session.return_value
        transaction = session.begin_transaction.return_value.__enter__.return_value
        result = transaction.run.return_value
        result.fetch.return_value = [{"value": 1}, {"value": 2}]

        rows = repository.execute_cypher(
            "RETURN $value", {"value": 1}, timeout=7, limit=2
        )

        self.assertEqual(rows, [{"value": 1}, {"value": 2}])
        self.assertEqual(
            driver.session.call_args.kwargs["default_access_mode"], READ_ACCESS
        )
        session.begin_transaction.assert_called_once_with(timeout=7)
        transaction.run.assert_called_once_with("RETURN $value", {"value": 1})
        result.fetch.assert_called_once_with(2)
        session.close.assert_called_once()


class GraphToolTests(unittest.IsolatedAsyncioTestCase):
    async def test_schema_loads_all_label_property_counts_in_one_read(self):
        repo = MagicMock()
        repo.get_all_labels.return_value = ["River", "Empty"]
        repo.get_all_relationship_types.return_value = ["CONNECTS"]
        repo.get_node_property_counts.return_value = {
            "River": [{"key": "name", "count": 3}],
        }
        with patch.object(server, "get_neo4j_repo", return_value=repo):
            schema = json.loads(await server.get_graph_schema())

        repo.get_node_property_counts.assert_called_once_with(["River", "Empty"])
        self.assertEqual(
            schema["labelProperties"],
            {"River": [{"property": "name", "sampleCount": 3}], "Empty": []},
        )

    async def test_registered_graph_tools_are_documented_and_do_not_accept_raw_cypher(
        self,
    ):
        tools = {tool.name: tool for tool in await server.mcp.list_tools()}
        self.assertNotIn("execute_read_cypher", tools)
        for name in (
            "get_graph_schema",
            "search_nodes_by_property",
            "get_node_neighborhood",
        ):
            self.assertTrue(tools[name].annotations.readOnlyHint)

    async def test_node_search_binds_identifiers_and_executes_outside_event_loop(self):
        main_thread = threading.get_ident()
        repo = MagicMock()

        def execute(query, params, **kwargs):
            self.assertNotIn("河 道", query)
            self.assertNotIn("河道 名称", query)
            self.assertEqual(params["label"], "河 道")
            self.assertEqual(params["property"], "河道 名称")
            self.assertEqual(params["value"], "运 河")
            self.assertNotEqual(threading.get_ident(), main_thread)
            return [{"n": Entity("1", riverName="运 河")}]

        repo.execute_cypher.side_effect = execute
        with patch.object(server, "get_neo4j_repo", return_value=repo):
            result = json.loads(
                await server.search_nodes_by_property("河 道", "河道 名称", "运 河")
            )
        self.assertEqual(result["nodes"], [{"riverName": "运 河"}])
        self.assertEqual(result["count"], 1)

    async def test_incoming_two_hop_results_preserve_storage_direction_and_identity(
        self,
    ):
        center = Entity("c", name="中心")
        near = Entity("n", name="同名节点")
        far = Entity("f", name="同名节点")
        first = Relationship("r1", near, center, weight=1)
        second = Relationship("r2", far, near, weight=2)

        repo = MagicMock()
        repo.execute_cypher.return_value = [
            {"center": center, "rels": [first], "hops": [center, near]},
            {"center": center, "rels": [first, second], "hops": [center, near, far]},
        ]
        with patch.object(server, "get_neo4j_repo", return_value=repo):
            result = json.loads(
                await server.get_node_neighborhood(
                    "Node", "name", "中心", depth=2, direction="incoming", limit=3
                )
            )

        query, params = repo.execute_cypher.call_args.args
        self.assertIn("(center)<-[*1..2]-(neighbor)", query)
        self.assertEqual(params["limit"], 3)
        self.assertEqual(result["center_node"], {"name": "中心"})
        self.assertEqual(result["center_node_id"], "c")
        self.assertEqual(result["neighbor_node_ids"], ["n", "f"])
        self.assertEqual(result["neighbor_count"], 2)
        self.assertEqual(result["relationship_count"], 2)
        self.assertEqual(
            result["relationships"][0],
            {
                "relationship_id": "r1",
                "start_node_id": "n",
                "end_node_id": "c",
                "type": "CONNECTED_TO",
                "properties": {"weight": 1},
            },
        )

    async def test_isolated_center_is_successful_and_missing_center_is_tool_error(self):
        repo = MagicMock()
        repo.execute_cypher.return_value = [
            {"center": Entity("c", name="中心"), "rels": None, "hops": None},
        ]
        with patch.object(server, "get_neo4j_repo", return_value=repo):
            payload = json.loads(
                await server.get_node_neighborhood("Node", "name", "中心")
            )
            self.assertEqual(payload["center_node_id"], "c")
            self.assertEqual(payload["neighbor_count"], 0)
            self.assertEqual(payload["relationship_count"], 0)
            repo.execute_cypher.return_value = []
            with self.assertRaises(ToolError):
                await server.get_node_neighborhood("Node", "name", "missing")

    async def test_driver_errors_do_not_expose_internal_details(self):
        repo = MagicMock()
        repo.execute_cypher.side_effect = RuntimeError("private driver diagnostic")
        with patch.object(server, "get_neo4j_repo", return_value=repo):
            with self.assertRaises(ToolError) as error:
                await server.search_nodes_by_property("Node", "name", "value")
        self.assertNotIn("private driver diagnostic", str(error.exception))
