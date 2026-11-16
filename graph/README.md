# 水网图谱 MCP

用 `neo4j-mcp` 通过 stdio 启动本地服务。已知实体的精确查询走 Neo4j 固定查询。自然语言问题交给 `wuxi_kg` 已有的图谱助手，由它调用 `NativeGraph工具` 使用确定性模板和 BYOKG 风格多策略检索。

## 工具

| 工具 | 用途 |
| --- | --- |
| `query_native_graph` | 向图谱助手询问实体、统计、最短路径和多跳关系。调用图谱查询工具时返回答案和子图证据，调用实时统计工具时保留统计数值和来源。助手直接作答时，`kind` 为 `agent_answer`。可选 `top_k`（1–50，默认 20）限制 MCP 返回的节点数。 |
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
| `WUXI_KG_ACCESS_TOKEN` | 现有 `wuxi_kg` 登录接口颁发的有效访问令牌。令牌对应的账号须已绑定部门。 |

自然语言查询使用现有的 `POST /api/chat/agent/MiniAgent` 接口，无需为 MCP 部署新的 `wuxi_kg` 后端版本。图谱助手使用登录账号所在部门的默认配置。分别配置两个数据源即可使用各自的工具。

每次调用会按 `wuxi_kg` 的对话流程运行图谱助手。服务端会为独立请求生成会话标识，可能创建部门的默认助手配置，并按现有设置记录问题和对话状态。在 `wuxi_kg` 配置外部工具时，应避免给同一个图谱助手配置 `query_native_graph`，以免循环调用。

## 验证

```powershell
uv sync --locked
uv run --locked python -m unittest discover -s tests
```

连接后可以询问「与大溪港直接相连的河道有哪些？」。保留返回的 `answer_text` 中的数字和实体名，使用 `nodes` 和 `edges` 展示查询证据。
