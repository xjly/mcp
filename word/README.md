# Word Polish MCP Server

专业文字润色服务，提供基于 LLM 的专业表达转换能力，使其符合业务或政府报告的规范要求。

## 功能概述

本工具为文字润色提供 MCP 接口，支持多种风格转换：
- **政府公文**: 严谨、庄重、规范
- **业务报告**: 专业、客观、逻辑性强
- **技术文档**: 精确、清晰、无歧义
- **简明扼要**: 剔除冗余，直击重点

## 配置使用

在 Claude Desktop 或其它 MCP 客户端配置中添加以下内容（参考 `mcp.example.json`）：

```json
{
  "mcpServers": {
    "word-polish": {
      "command": "uv",
      "args": [
        "--directory",
        "e:/mcp-master/word",
        "run",
        "word-mcp"
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
```

## 工具列表

| 工具 | 说明 |
|------|------|
| `polish_text` | 对输入的文字进行润色，支持指定风格和额外要求 |

### `polish_text` 参数说明
- `text`: (必填) 需要润色的原始文字内容
- `style`: (可选) 润色风格，默认为 "政府公文"
- `requirements`: (可选) 额外的润色要求，如 "增加专业术语"、"语气更委婉" 等

## 安全与限制

- 仅进行文字处理，不存储用户数据
- 依赖外部 LLM 服务（推荐使用硅基流动，API 兼容 OpenAI），需配置有效的 API Key
- 默认查询超时时间为 60 秒
