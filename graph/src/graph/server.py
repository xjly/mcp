"""Neo4j MCP 图谱结构、实体与关联查询。"""

import asyncio
import json
import time
from collections.abc import Callable
from contextlib import asynccontextmanager
from typing import Annotated, Any, Literal

from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.exceptions import ToolError
from mcp.types import ToolAnnotations
from pydantic import Field

from graph.native_query import register_native_query
from graph.repository import Neo4jGraphRepository


_neo4j_repo: Neo4jGraphRepository | None = None


@asynccontextmanager
async def _lifespan(_server: FastMCP):
    try:
        yield
    finally:
        global _neo4j_repo
        repo, _neo4j_repo = _neo4j_repo, None
        if repo is not None:
            await asyncio.to_thread(repo.close)


mcp = FastMCP(
    "neo4j-graph",
    lifespan=_lifespan,
    instructions=(
        "自然语言图谱问题优先用 query_native_graph。"
        "用 get_graph_schema 查看图谱结构，用 search_nodes_by_property 按已知属性查找实体。"
        "用 get_node_neighborhood 按方向展开一跳或二跳关系，端点 ID 表示图中关系的存储方向。"
    ),
)
_READ_ONLY = ToolAnnotations(
    readOnlyHint=True,
    destructiveHint=False,
    idempotentHint=True,
    openWorldHint=True,
)
_MATCH_OPERATORS = {
    "exact": "=",
    "contains": "CONTAINS",
    "starts_with": "STARTS WITH",
    "ends_with": "ENDS WITH",
}
_RELATIONSHIP_PATTERNS = {
    "outgoing": ("-[]->", "-[*1..2]->"),
    "incoming": ("<-[]-", "<-[*1..2]-"),
    "both": ("-[]-", "-[*1..2]-"),
}


def get_neo4j_repo() -> Neo4jGraphRepository:
    """按需创建 Neo4j repository。"""
    global _neo4j_repo
    if _neo4j_repo is None:
        _neo4j_repo = Neo4jGraphRepository()
    return _neo4j_repo


async def _read[T](operation: Callable[[Neo4jGraphRepository], T]) -> T:
    try:
        repo = get_neo4j_repo()
        return await asyncio.to_thread(operation, repo)
    except Exception:
        raise ToolError("图谱查询失败，请检查 Neo4j 配置、连接或查询超时。") from None


def _safe_result(result: Any) -> Any:
    """转换 Neo4j 属性值为 JSON 兼容值。"""
    if result is None or isinstance(result, (str, int, float, bool)):
        return result
    if isinstance(result, dict):
        return {key: _safe_result(value) for key, value in result.items()}
    if isinstance(result, (list, tuple)):
        return [_safe_result(value) for value in result]
    if isinstance(result, bytes):
        return "<binary_data>"
    return str(result)


def _build_schema_info(repo: Neo4jGraphRepository) -> dict[str, Any]:
    labels = repo.get_all_labels()
    relationship_types = repo.get_all_relationship_types()
    property_counts = repo.get_node_property_counts(labels)
    properties = {
        label: [
            {"property": row["key"], "sampleCount": row["count"]}
            for row in property_counts.get(label, [])
        ]
        for label in labels
    }
    return {
        "nodeLabels": labels,
        "relationshipTypes": relationship_types,
        "labelProperties": properties,
        "totalLabels": len(labels),
        "totalRelationshipTypes": len(relationship_types),
    }


@mcp.tool(annotations=_READ_ONLY)
async def get_graph_schema() -> str:
    """获取图谱的节点标签、关系类型及每个标签的常见属性。"""
    schema = await _read(_build_schema_info)
    return json.dumps(schema, ensure_ascii=False, indent=2)


@mcp.tool(annotations=_READ_ONLY)
async def search_nodes_by_property(
    node_label: Annotated[
        str, Field(min_length=1, max_length=255, description="节点标签，如 River")
    ],
    property_name: Annotated[
        str, Field(min_length=1, max_length=255, description="属性名称，如 riverName")
    ],
    property_value: Annotated[
        str, Field(max_length=2000, description="用来匹配属性的字符串")
    ],
    match_mode: Annotated[
        Literal["exact", "contains", "starts_with", "ends_with"],
        Field(description="匹配方式，默认为精确匹配"),
    ] = "exact",
    limit: Annotated[int, Field(ge=1, le=100, description="返回的节点数量上限")] = 20,
) -> str:
    """按标签及属性值查找实体，返回匹配节点的属性。"""
    operator = _MATCH_OPERATORS[match_mode]
    query = f"""
        MATCH (n)
        WHERE $label IN labels(n) AND n[$property] {operator} $value
        RETURN n
        LIMIT $limit
    """
    params = {
        "label": node_label,
        "property": property_name,
        "value": property_value,
        "limit": limit,
    }
    started = time.monotonic()
    rows = await _read(lambda repo: repo.execute_cypher(query, params, limit=limit))
    nodes = [_safe_result(dict(row["n"])) for row in rows]
    return json.dumps(
        {
            "node_label": node_label,
            "property_name": property_name,
            "property_value": property_value,
            "match_mode": match_mode,
            "nodes": nodes,
            "count": len(nodes),
            "execution_time_ms": int((time.monotonic() - started) * 1000),
        },
        ensure_ascii=False,
        indent=2,
    )


@mcp.tool(annotations=_READ_ONLY)
async def get_node_neighborhood(
    node_label: Annotated[
        str, Field(min_length=1, max_length=255, description="中心节点标签")
    ],
    node_identifier: Annotated[
        str,
        Field(min_length=1, max_length=255, description="用来定位中心节点的属性名称"),
    ],
    node_value: Annotated[
        str, Field(max_length=2000, description="中心节点标识属性的精确值")
    ],
    depth: Annotated[Literal[1, 2], Field(description="关系展开深度")] = 1,
    direction: Annotated[
        Literal["outgoing", "incoming", "both"],
        Field(description="从中心出发的关系方向"),
    ] = "outgoing",
    limit: Annotated[int, Field(ge=1, le=100, description="最多读取的路径数")] = 50,
) -> str:
    """展开实体的一跳或二跳关系，返回节点属性、关系属性和关系端点。"""
    pattern = _RELATIONSHIP_PATTERNS[direction][depth - 1]
    query = f"""
        MATCH (center)
        WHERE $label IN labels(center) AND center[$property] = $value
        WITH center ORDER BY elementId(center) LIMIT 1
        OPTIONAL MATCH path = (center){pattern}(neighbor)
        RETURN center, relationships(path) AS rels, nodes(path) AS hops
        LIMIT $limit
    """
    params = {
        "label": node_label,
        "property": node_identifier,
        "value": node_value,
        "limit": limit,
    }
    started = time.monotonic()
    rows = await _read(lambda repo: repo.execute_cypher(query, params, limit=limit))
    if not rows:
        raise ToolError("未找到符合指定标签和标识属性的中心节点。")

    center = rows[0]["center"]
    neighbor_nodes = {}
    relationships = {}
    for row in rows:
        for node in row["hops"] or ():
            if node.element_id != center.element_id:
                neighbor_nodes[node.element_id] = _safe_result(dict(node))
        for rel in row["rels"] or ():
            if rel.element_id not in relationships:
                relationships[rel.element_id] = {
                    "relationship_id": rel.element_id,
                    "start_node_id": rel.start_node.element_id,
                    "end_node_id": rel.end_node.element_id,
                    "type": rel.type,
                    "properties": _safe_result(dict(rel)),
                }

    return json.dumps(
        {
            "center_node": _safe_result(dict(center)),
            "center_node_id": center.element_id,
            "depth": depth,
            "direction": direction,
            "relationships": list(relationships.values()),
            "neighbor_nodes": list(neighbor_nodes.values()),
            "neighbor_node_ids": list(neighbor_nodes),
            "neighbor_count": len(neighbor_nodes),
            "relationship_count": len(relationships),
            "execution_time_ms": int((time.monotonic() - started) * 1000),
        },
        ensure_ascii=False,
        indent=2,
    )


def main() -> None:
    """启动 stdio MCP 服务。"""
    mcp.run()


register_native_query(mcp)


if __name__ == "__main__":
    main()
