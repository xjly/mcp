"""Neo4j MCP Server - 图数据库查询服务

提供 Neo4j 图数据库的只读查询能力
"""

import argparse
import json
from typing import Any

from mcp.server.fastmcp import FastMCP

from src.graph.neo4j_repository import Neo4jGraphRepository

# =============================================================================
# === MCP 服务器定义 ===
# =============================================================================

mcp = FastMCP(
    "neo4j-graph",
    instructions="""
## Neo4j 图数据库查询服务

### 服务能力
本服务提供 Neo4j 图数据库的只读查询能力，支持：
- **get_graph_schema**: 获取图谱 Schema（节点类型、关系类型、属性）
- **search_nodes_by_property**: 按属性精确/模糊查找实体
- **get_node_neighborhood**: 获取节点周围一阶/二阶关联子图
- **execute_read_cypher**: 执行自定义只读 Cypher 查询

### 典型工作流

**工作流1：了解图谱结构**
1. 调用 `get_graph_schema` 了解有哪些节点类型和关系

**工作流2：查找特定实体**
1. 调用 `search_nodes_by_property`，指定节点类型和属性
2. 获取匹配实体的详细信息

**工作流3：探索关联关系**
1. 已知节点 ID 或标识
2. 调用 `get_node_neighborhood` 获取周围节点和关系

**工作流4：自由查询**
1. 调用 `execute_read_cypher` 执行自定义 Cypher

### 安全限制
- 仅支持只读查询
- 禁止任何写操作（CREATE/DELETE/SET 等）
- 查询超时默认30秒
- 返回结果最多500条
""",
)


# =============================================================================
# === Neo4j Repository 实例 ===
# =============================================================================

_neo4j_repo: Neo4jGraphRepository | None = None


def get_neo4j_repo() -> Neo4jGraphRepository:
    """获取或创建 Neo4j repository 实例"""
    global _neo4j_repo
    if _neo4j_repo is None:
        _neo4j_repo = Neo4jGraphRepository()
    return _neo4j_repo


# =============================================================================
# === 辅助函数 ===
# =============================================================================


def _safe_result(result: Any) -> dict | list | str | int | float | bool | None:
    """安全地转换查询结果为 JSON 兼容格式"""
    if result is None:
        return {}
    if isinstance(result, dict):
        return {k: _safe_result(v) for k, v in result.items()}
    if isinstance(result, (list, tuple)):
        return [_safe_result(item) for item in result]
    if isinstance(result, (str, int, float, bool)):
        return result
    if isinstance(result, bytes):
        return "<binary_data>"
    return str(result)


def _build_schema_info(repo: Neo4jGraphRepository) -> dict:
    """构建完整的 Schema 信息"""
    try:
        labels = repo.get_all_labels()
        rel_types = repo.get_all_relationship_types()

        label_properties = {}
        for label in labels:
            try:
                query = f"""
                MATCH (n:{label})
                WITH keys(n) as keys
                UNWIND keys as key
                RETURN key, count(*) as count
                ORDER BY count DESC
                LIMIT 20
                """
                props = repo.execute_cypher(query)
                label_properties[label] = [
                    {"property": p["key"], "sampleCount": p["count"]}
                    for p in props
                ]
            except Exception:
                label_properties[label] = []

        return {
            "nodeLabels": labels,
            "relationshipTypes": rel_types,
            "labelProperties": label_properties,
            "totalLabels": len(labels),
            "totalRelationshipTypes": len(rel_types),
        }
    except Exception as e:
        return {"error": str(e)}


# =============================================================================
# === MCP 工具注册 ===
# =============================================================================


@mcp.tool()
async def get_graph_schema() -> str:
    """
    获取当前知识图谱的完整 Schema 信息，供 LLM 生成 Cypher 语句时参考。

    Returns:
        JSON 字符串，包含 nodeLabels、relationshipTypes、labelProperties 等
    """
    repo = get_neo4j_repo()
    schema = _build_schema_info(repo)
    return json.dumps(_safe_result(schema), ensure_ascii=False, indent=2)


@mcp.tool()
async def search_nodes_by_property(
    node_label: str,
    property_name: str,
    property_value: str,
    match_mode: str = "exact",
    limit: int = 20,
) -> str:
    """
    按节点属性进行精确匹配或模糊查找实体节点。

    Args:
        node_label: 节点类型/标签名，如 "River", "Area", "PumpStation"
        property_name: 属性名，如 "riverName", "areaName"
        property_value: 属性值（用于匹配）
        match_mode: 匹配模式 - exact(精确), contains(包含), starts_with(前缀), ends_with(后缀)
        limit: 返回结果数量上限，默认20，最大100

    Returns:
        JSON 字符串，包含匹配的节点列表
    """
    import time

    repo = get_neo4j_repo()
    limit = min(limit, 100)

    if match_mode == "exact":
        query = f"""
        MATCH (n:{node_label} {{{property_name}: $value}})
        RETURN n
        LIMIT $limit
        """
    elif match_mode == "contains":
        query = f"""
        MATCH (n:{node_label})
        WHERE n.{property_name} CONTAINS $value
        RETURN n
        LIMIT $limit
        """
    elif match_mode == "starts_with":
        query = f"""
        MATCH (n:{node_label})
        WHERE n.{property_name} STARTS WITH $value
        RETURN n
        LIMIT $limit
        """
    elif match_mode == "ends_with":
        query = f"""
        MATCH (n:{node_label})
        WHERE n.{property_name} ENDS WITH $value
        RETURN n
        LIMIT $limit
        """
    else:
        return json.dumps({"error": f"Unknown match_mode: {match_mode}"})

    start_time = time.time()
    results = repo.execute_cypher(query, {"value": property_value, "limit": limit})
    execution_time = int((time.time() - start_time) * 1000)

    nodes = [_safe_result(dict(record["n"])) for record in results]

    return json.dumps(
        {
            "node_label": node_label,
            "property_name": property_name,
            "property_value": property_value,
            "match_mode": match_mode,
            "nodes": nodes,
            "count": len(nodes),
            "execution_time_ms": execution_time,
        },
        ensure_ascii=False,
        indent=2,
    )


@mcp.tool()
async def get_node_neighborhood(
    node_label: str,
    node_identifier: str,
    node_value: str,
    depth: int = 1,
    direction: str = "outgoing",
    limit: int = 50,
) -> str:
    """
    获取指定节点周围的一阶或二阶关联子图。

    Args:
        node_label: 节点类型/标签名
        node_identifier: 节点标识属性名（用于定位节点）
        node_value: 节点标识值
        depth: 扩展深度，1 或 2
        direction: 关系方向 - outgoing(出), incoming(入), both(双向)
        limit: 每个方向返回结果上限

    Returns:
        JSON 字符串，包含中心节点、邻居节点和关系
    """
    import time

    repo = get_neo4j_repo()

    find_query = f"MATCH (n:{node_label}) WHERE n.{node_identifier} = $value RETURN n"
    center_results = repo.execute_cypher(find_query, {"value": node_value})

    if not center_results:
        return json.dumps(
            {"error": f"Node not found: {node_label}.{node_identifier} = {node_value}"}
        )

    center_node = _safe_result(dict(center_results[0]["n"]))

    if direction == "outgoing":
        rel_pattern = "-[r]->"
    elif direction == "incoming":
        rel_pattern = "<-[r]-"
    else:
        rel_pattern = "-[r]-"

    if depth == 1:
        query = f"""
        MATCH (center:{node_label} {{{node_identifier}: $value}})
        MATCH (center){rel_pattern}(neighbor)
        RETURN center, r, neighbor
        LIMIT $limit
        """
    else:
        query = f"""
        MATCH (center:{node_label} {{{node_identifier}: $value}})
        MATCH path = (center)-[r1*1..{depth}]-(neighbor)
        WHERE neighbor <> center
        RETURN center, relationships(path) as rels, nodes(path) as hops
        LIMIT $limit
        """

    start_time = time.time()
    results = repo.execute_cypher(query, {"value": node_value, "limit": limit})
    execution_time = int((time.time() - start_time) * 1000)

    relationships = []
    neighbor_nodes = []
    seen_nodes = set()
    seen_rels = set()

    for record in results:
        if depth == 1:
            r = record["r"]
            neighbor = record["neighbor"]
        else:
            rels = record.get("rels") or []
            hops = record.get("hops") or []
            continue

        rel_id = id(r) if hasattr(r, "__id__") else str(r)
        if rel_id not in seen_rels:
            rel_info = {
                "type": (
                    type(r).__name__
                    if not hasattr(r, "type")
                    else str(r.type) if hasattr(r, "type") else "RELATIONSHIP"
                ),
                "properties": (
                    _safe_result(dict(r)) if hasattr(r, "__properties__") else {}
                ),
            }
            relationships.append(rel_info)
            seen_rels.add(rel_id)

        node_id = neighbor.get("stationId") or neighbor.get("riverName") or str(
            hash(str(neighbor))
        )
        if node_id not in seen_nodes:
            neighbor_nodes.append(_safe_result(dict(neighbor)))
            seen_nodes.add(node_id)

    return json.dumps(
        {
            "center_node": center_node,
            "depth": depth,
            "direction": direction,
            "relationships": relationships,
            "neighbor_nodes": neighbor_nodes,
            "neighbor_count": len(neighbor_nodes),
            "relationship_count": len(relationships),
            "execution_time_ms": execution_time,
        },
        ensure_ascii=False,
        indent=2,
    )


@mcp.tool()
async def execute_read_cypher(
    cypher: str,
    params: dict | None = None,
    timeout: int = 30,
) -> str:
    """
    执行自定义的只读 Cypher 查询语句。

    Args:
        cypher: Cypher 查询语句
        params: 查询参数字典
        timeout: 查询超时秒数，默认30，最大120

    Returns:
        JSON 字符串，包含查询结果列名和数据
    """
    import time

    repo = get_neo4j_repo()
    params = params or {}
    timeout = min(timeout, 120)

    write_keywords = [
        "CREATE", "DELETE", "SET", "REMOVE", "MERGE",
        "DETACH", "DROP", "ALTER", "INSERT", "UPDATE",
    ]
    upper_cypher = cypher.upper()
    for keyword in write_keywords:
        if keyword in upper_cypher:
            return json.dumps({"error": f"Write operations are not allowed: {keyword}"})

    read_prefixes = ["MATCH", "WITH", "RETURN", "EXPLAIN", "COUNT", "CALL"]
    if not any(upper_cypher.strip().startswith(prefix) for prefix in read_prefixes):
        return json.dumps(
            {"error": "Query must start with MATCH, WITH, RETURN, EXPLAIN, COUNT, or CALL"}
        )

    start_time = time.time()
    results = repo.execute_cypher(cypher, params, timeout=timeout)
    execution_time = int((time.time() - start_time) * 1000)

    if not results:
        return json.dumps(
            {
                "columns": [],
                "data": [],
                "row_count": 0,
                "execution_time_ms": execution_time,
            }
        )

    columns = list(results[0].keys())
    data = [_safe_result(list(record.values())) for record in results]

    return json.dumps(
        {
            "columns": columns,
            "data": data,
            "row_count": len(data),
            "execution_time_ms": execution_time,
        },
        ensure_ascii=False,
        indent=2,
    )


# =============================================================================
# === 启动入口 ===
# =============================================================================


async def main():
    """主入口函数"""
    parser = argparse.ArgumentParser(description="Neo4j MCP Server")
    parser.add_argument(
        "--transport",
        choices=["stdio", "http"],
        default="stdio",
        help="Transport mode",
    )
    parser.add_argument("--port", type=int, default=8765, help="HTTP server port")
    parser.add_argument("--host", default="0.0.0.0", help="HTTP server host")
    args = parser.parse_args()

    if args.transport == "http":
        import uvicorn

        app = mcp.streamable_http_app()
        config = uvicorn.Config(
            app, host=args.host, port=args.port, log_level="info"
        )
        server = uvicorn.Server(config)
        await server.serve()
    else:
        await mcp.run_stdio_async()
