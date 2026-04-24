# Schedule MCP Server

定时任务和大屏推送的 MCP (Model Context Protocol) 服务。

## 功能概述

本工具为 Yuxi 平台提供定时任务管理和消息推送能力：

- 创建/取消/列出 cron 定时任务
- 定时自动推送内容到大屏
- 即时推送内容到大屏
- 支持内存存储和 SQLite 数据库持久化（一定一定要注意数据库的地址）

- 在yuxi前端配置好mcp后，需要运行两个窗口
- 一个是src/schedule/push_server_combined.py(确保能持久化服务,之后应该会改进这个持久化)
- 一个是test/mock_screen_test.py(确保能正常推送,即大屏上显示)
- 记得修改路径
## 配置使用

在 Yuxi 平台或其它 MCP 客户端配置中添加以下配置（参考 `mcp.example.json`）：

```json
{
  "mcpServers": {
    "schedule": {
      "command": "uvx",
      "args": [
        "--from",
        "git+https://github.com/your-repo/schedule-mcp-server",#服务的代码仓库
        "schedule-mcp"
      ],
      "env": {
        "PUSH_SERVICE_URL": "http://localhost:8080/api/push",#推送服务的 URL，即大屏url
        "PUSH_TIMEOUT": "30",
        "SCHEDULER_TIMEZONE": "Asia/Shanghai"
      }
    }
  }
}
```

```JSON
yuxi配置

{
  "name": "schedule-mcp",
  "transport": "stdio",
  "command": "uvx",
  "args": [
    "--force-reinstall",
    "--from",
    "E:/mcp-master/mcp-master/schedule-mcp-server",#服务的安装路径
    "schedule-mcp"
  ],
  "description": "定时任务和大屏推送服务",
  "headers": {},
  "env": {
    "JOB_STORE_TYPE": "sqlite",
    "SQLITE_DB_PATH": "E:/mcp-master/mcp-master/schedule-mcp-server/jobs.sqlite",#数据库路径
    "SCHEDULER_TIMEZONE": "Asia/Shanghai",
    "PUSH_SERVICE_URL": "http://localhost:8080/api/push",#推送服务的 URL，即大屏url，目前是要运行test目录下的mock_screen_test.py文件
    "PUSH_TIMEOUT": "30"
  },
  "tags": ["定时任务", "推送", "cron", "大屏"]
}
```

