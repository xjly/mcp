# 水网知识库 MCP

在每个 MCP 客户端本地通过 `uvx` 启动 `knowledge-mcp`，使用 stdio 通信。服务读取共享知识库的文档目录和语义检索片段。客户端主机需能通过内网、VPN 或受控隧道访问 PostgreSQL、Milvus 和嵌入服务。将专用只读凭据发放给获准访问整个知识库的使用者。这个接入方式以数据库角色为访问边界。

## 服务端准备

现有数据清单记录的「水网知识」ID 为 `kb_32676d6144484f6543972bb4d314db7b`，同时是 Milvus collection 名。部署前核对目标环境中的 ID、Milvus 数据库名和用于建索引的嵌入模型。

### PostgreSQL

请数据库管理员在存放 `public.knowledge_bases` 和 `public.knowledge_files` 的数据库中准备独立登录角色。该角色应无业务表权限和写权限，并且不继承其他业务角色。由拥有源表读取权限和建 schema 权限的部署账号执行脚本，通过 `-h` 和 `-U` 指定实际管理连接，或使用已有的 `PGHOST`、`PGUSER` 等设置。脚本依赖已有角色和目标 Milvus 知识库。

```powershell
psql -d 'knowledge-db' -v db_id=kb_32676d6144484f6543972bb4d314db7b -v reader_role=mcp_kb_reader -f setup_readonly_views.sql
```

脚本一次性创建 `mcp_kb` schema。两个视图都固定过滤到指定知识库，文档目录排除文件夹。脚本只向读取角色授予 schema 的 `USAGE` 和两个视图的 `SELECT`。首次部署后，用该角色验证能读取视图，并确认 PostgreSQL 拒绝读取源表和修改两个视图。 [PostgreSQL 视图权限](https://www.postgresql.org/docs/current/rules-privileges.html)

### Milvus 与嵌入服务

在已开启 Milvus 鉴权的实例上，为专用角色授予目标数据库、目标 collection 上的 `Search` 和 `DescribeCollection`。管理员提前加载该 collection，并把角色授予 MCP 使用的 Milvus 用户。Milvus 2.5 起可按下面的方式授权。 [Milvus 授权文档](https://milvus.io/docs/grant_privileges.md)

```python
for privilege in ('Search', 'DescribeCollection'):
    admin_client.grant_privilege_v2(
        role_name='mcp_kb_reader',
        privilege=privilege,
        db_name='yuxi_know',
        collection_name='kb_32676d6144484f6543972bb4d314db7b',
    )
```

用专用账号确认目标集合可搜索、其他集合的搜索请求被拒绝，并检查账号从其他角色继承的权限。Milvus 2.5 默认启用 `public` 权限，部署时按实际授权核对集合元数据的可见范围。 [Milvus 2.5 权限配置](https://milvus.io/docs/v2.5.x/configure_common.md)

嵌入服务必须提供原始索引使用的模型和维度。PostgreSQL 的 `embed_info` 需提供 `model_id`、`name` 和 `dimension`。`model_id` 以 `ollama/` 开头时，配置 Ollama 的完整 `/api/embed` URL。其余模型配置 OpenAI 兼容服务的完整 `/v1/embeddings` URL。查询文本会发送至这个嵌入服务。

## 客户端配置

将 [mcp.example.json](mcp.example.json) 中的 `knowledge` 配置复制到 MCP 客户端，并从本地秘密配置注入专用凭据。Git 安装地址需要包含服务代码的仓库版本。验证本地检出时，把 `--from` 后的参数换成 `knowledge-mcp-server` 的绝对路径。配置中的凭据和地址均为占位值。

| 环境变量 | 值 |
| --- | --- |
| `WUXI_KG_DB_ID` | PostgreSQL 视图限制的知识库 ID，与 Milvus collection 名一致 |
| `WUXI_KG_POSTGRES_DSN` | PostgreSQL 专用读取角色的 `postgresql://` DSN。使用 `sslmode=verify-full` 时，按部署环境配置可信 CA（如 DSN 的 `sslrootcert` 参数） |
| `WUXI_KG_MILVUS_URI` | MCP 客户端主机可访问的 Milvus URI |
| `WUXI_KG_MILVUS_DATABASE` | 目标 collection 所在数据库 |
| `WUXI_KG_MILVUS_TOKEN` | 该 collection 的专用凭据，自托管 Milvus 通常使用 `用户名:密码` |
| `WUXI_KG_EMBEDDING_URL` | 原索引模型的完整嵌入接口 URL |
| `WUXI_KG_EMBEDDING_API_KEY` | 可选，嵌入服务要求 Bearer 鉴权时提供 |

## 工具

| 工具 | 参数 | 用途 |
| --- | --- | --- |
| `list_knowledge_bases` | 无 | `databases` 包含已配置知识库的 ID、名称、描述和类型 |
| `list_documents` | `db_id` 和可选的 `file_name`（最多 200 字符）、`limit=20`（1–100）、`offset=0`（非负） | 用 `file_name` 对当前文件名和原文件名做不区分大小写的子串匹配。返回 `files`、`total` 和 `has_more` 等分页信息 |
| `search_documents` | `db_id` 和 `query`（去除首尾空白后 1–1000 字符），可选 `limit=5`（1–20） | `matches` 包含相关文档片段、`file_id`、`file_name` 和可用的 `chunk_id`、`chunk_index`、`score`。引用时保留文件名和可用的片段 ID。`truncated` 表示片段是否截断 |

建议先调用 `list_knowledge_bases` 取得 `db_id`。想确认文件是否收录时，调用 `list_documents`。根据问题找文档证据时，直接调用 `search_documents`。工具返回结构化结果，库中没有匹配项时返回空列表。调用失败由 MCP 客户端显示为工具错误。

## 联调

在 `knowledge-mcp-server` 目录准备一份本地 `mcp.json`，填入只读测试配置且使用绝对 `--from` 路径。用 MCP Inspector 连接客户端配置中的服务。 [MCP Inspector](https://github.com/modelcontextprotocol/inspector)

```powershell
npx @modelcontextprotocol/inspector@v1-latest --cli --config .\mcp.json --server knowledge --method tools/list
npx @modelcontextprotocol/inspector@v1-latest --cli --config .\mcp.json --server knowledge --method tools/call --tool-name list_knowledge_bases
npx @modelcontextprotocol/inspector@v1-latest --cli --config .\mcp.json --server knowledge --method tools/call --tool-name list_documents --tool-arg db_id=kb_32676d6144484f6543972bb4d314db7b
npx @modelcontextprotocol/inspector@v1-latest --cli --config .\mcp.json --server knowledge --method tools/call --tool-name search_documents --tool-arg db_id=kb_32676d6144484f6543972bb4d314db7b --tool-arg 'query=水网巡查要求'
```

用实际有权限的测试库 ID 替换命令中的示例 ID。确认列表只显示该库，文档可分页读取，检索片段的 `file_id` 与目录对应。分别传入另一个库 ID、空白查询和越界的 `limit`，确认 MCP 返回工具错误。
