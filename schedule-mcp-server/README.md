# Schedule MCP Server

定时任务和大屏推送的 MCP (Model Context Protocol) 服务。

## 功能概述

本工具为 Yuxi 平台提供定时任务管理和消息推送能力：
- 创建/取消/列出 cron 定时任务
- 定时自动推送内容到大屏
- 即时推送内容到大屏
- 支持内存存储和 SQLite 数据库持久化

## 配置使用

在 Yuxi 平台或其它 MCP 客户端配置中添加以下配置（参考 `mcp.example.json`）：

```json
{
  "mcpServers": {
    "schedule": {
      "command": "uvx",
      "args": [
        "--from",
        "git+https://github.com/your-repo/schedule-mcp-server",
        "schedule-mcp"
      ],
      "env": {
        "PUSH_SERVICE_URL": "http://localhost:8080/api/push",
        "PUSH_TIMEOUT": "30",
        "SCHEDULER_TIMEZONE": "Asia/Shanghai"
      }
    }
  }
}