# 水网图谱 MCP

用 `neo4j-mcp` 通过 stdio 启动本地服务。已知实体的精确查询走 Neo4j 固定查询。自然语言问题交给 `wuxi_kg` 现有的确定性模板和 BYOKG 风格多策略检索。

## 工具

| 工具 | 用途 |
| --- | --- |
| `query_native_graph` | 输入完整自然语言问题和可选 `top_k`（1–50，默认 20），查询实体、统计、最短路径、多跳子图。返回 `answer_text`、节点、边、歧义候选和查询元数据。 |
| `get_graph_schema` | 获取节点标签、关系类型和样本属性。 |
| `search_nodes_by_property` | 使用节点标签、属性和值查找实体。支持精确、包含、前缀和后缀匹配。 |
| `get_node_neighborhood` | 使用实体标识查询一跳或二跳关系，支持出边、入边和双向。返回节点 ID、边的起止节点与属性。 |

图谱问答优先使用 `query_native_graph`。按确切属性和节点读关系时使用直接查询工具。原 `execute_read_cypher` 入口由自然语言查询和固定查询工具接替。

## 客户端配置

参考 [mcp.example.json](mcp.example.json)。在 WorkBuddy 等客户端通过 `uvx` 加载代码。验证本地版本时，把 `--from` 的值改为本目录的绝对路径。

| 环境变量 | 用途 |
| --- | --- |
| `NEO4J_URI`、`NEO4J_USERNAME`、`NEO4J_PASSWORD` | 直接查询 Neo4j 的连接配置。部署支持数据库只读角色时，使用专用读账号。 |
| `WUXI_KG_API_BASE_URL` | `wuxi_kg` 服务地址，可带部署路径前缀，填写到 `/api` 之前。 |
| `WUXI_KG_ACCESS_TOKEN` | 现有 `wuxi_kg` 登录接口颁发的有效访问令牌，供自然语言图谱查询使用。 |

部署包含 `POST /api/native-graph/mcp/query` 的 `wuxi_kg` 后端版本，才能使用自然语言查询。分别配置两个数据源即可使用各自的工具。

## 验证

```powershell
uv sync --locked
uv run --locked python -m unittest discover -s tests
```

连接后可以询问「与大溪港直接相连的河道有哪些？」。保留返回的 `answer_text` 中的数字和实体名，使用 `nodes` 和 `edges` 展示查询证据。
