# File Template MCP Server

公文模板填充服务，基于 Jinja2 和 LLM 智能填充引擎。

## 功能特性

- **双引擎填充**:
  - **Jinja2 引擎**: 支持 `{{变量}}` 格式的高效填充
  - **LLM 智能引擎**: 智能识别 `____`、空格、下划线等非标准占位符
- **多源模板**: 支持内置模板库和动态模板内容覆盖
- **格式保留**: 保留模板原始格式


## 配置使用

在 Claude Desktop 或其它 MCP 客户端配置中添加以下内容（参考 `mcp.example.json`）：

```json
{
  "mcpServers": {
    "file-polish": {
      "command": "uvx",
      "args": [
        "--from",
        "git+https://github.com/xjly/mcp#subdirectory=file",
        "file-mcp"
      ],
      "env": {
        "POLISH_API_KEY": "你的硅基流动API密钥",
        "POLISH_BASE_URL": "https://api.siliconflow.cn/v1",
        "POLISH_TIMEOUT_SECONDS": "60",
        "POLISH_MODEL": "deepseek-ai/DeepSeek-V3"
      }
    }
  }
}
