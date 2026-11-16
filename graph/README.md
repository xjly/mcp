# Neo4j Graph MCP Server

Neo4j 图数据库的 MCP (Model Context Protocol) 查询服务，提供只读访问能力。

## 功能概述

本工具为 Neo4j 图数据库提供 MCP 接口，使 LLM 能够：
- 查询图谱 Schema（节点类型、关系类型、属性）
- 按属性查找实体节点
- 探索节点周围的关联子图
- 执行自定义只读 Cypher 查询

## 配置使用

在 Claude Code 或其它 MCP 客户端配置中添加以下配置（参考 `mcp.example.json`）：

```json
{
  "mcpServers": {
    "neo4j": {
      "command": "uvx",
      "args": [
        "--from",
        "git+https://github.com/xjly/mcp#subdirectory=graph",
        "neo4j-mcp"
      ],
      "env": {
        "NEO4J_URI": "bolt://xxxxx:7687",
        "NEO4J_USERNAME": "your_username",
        "NEO4J_PASSWORD": "your_password"
      }
    }
  }
}
```

## 工具列表

| 工具 | 说明 |
|------|------|
| `get_graph_schema` | 获取完整图谱 Schema（节点标签、关系类型、属性） |
| `search_nodes_by_property` | 按属性精确/模糊查找节点 |
| `get_node_neighborhood` | 获取节点周围一阶/二阶关联子图 |
| `execute_read_cypher` | 执行自定义只读 Cypher 查询 |

## 安全限制

- 仅支持只读查询
- 禁止写操作（CREATE/DELETE/SET 等）
- 查询超时默认 30 秒，最大 120 秒
- 返回结果最多 500 条
