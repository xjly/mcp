# Schedule MCP Server

这是一个用于定时任务和大屏消息推送的 MCP Server。它提供两个 MCP 工具：

- `schedule_task`：创建、取消、列出 cron 定时推送任务
- `push_to_screen`：立即把内容推送到大屏服务

任务默认使用 SQLite 持久化，MCP 服务重启后仍能恢复已经创建的定时任务。

## 当前项目路径

本机当前路径：

```text
D:\02_Projects\Source\mcp\schedule-mcp-server
```

如果你要使用本地目录开发，可以把 MCP 配置中的 `--from` 改成本地项目路径。

当前默认配置使用 Git 仓库子目录安装：

```text
git+https://github.com/xjly/mcp#subdirectory=schedule-mcp-server
```

注意：`SQLITE_DB_PATH` 不要改成 Git 地址。它必须是本机可写的 `.sqlite` 文件路径，用来长期保存定时任务。可以继续使用当前项目下的 `jobs.sqlite`，也可以改成其它稳定的数据目录，例如：

```text
D:\mcp-data\schedule-mcp\jobs.sqlite
```

如果 MCP 客户端没有传入 `SQLITE_DB_PATH`，服务会自动使用当前用户的本地数据目录，例如 Windows 下通常是：

```text
C:\Users\<你的用户名>\AppData\Local\schedule-mcp\jobs.sqlite
```

## MCP 客户端配置

在支持 MCP 的客户端中添加下面配置。这个仓库已经提供了同内容的 `mcp.json` 和 `mcp.example.json`。
```json
{
  "name": "schedule-mcp",
  "transport": "stdio",
  "command": "powershell",
  "args": [
    "-NoProfile",
    "-ExecutionPolicy",
    "Bypass",
    "-Command",
    "$env:PUSH_SERVICE_URL='http://127.0.0.1:8080/api/push'; $env:PUSH_TIMEOUT='30'; $env:SCHEDULER_TIMEZONE='Asia/Shanghai'; $env:JOB_STORE_TYPE='sqlite'; $env:SQLITE_DB_PATH='D:\\02_Projects\\Source\\mcp\\schedule-mcp-server\\jobs.sqlite'; uvx --refresh --reinstall --from 'D:\\02_Projects\\Source\\mcp\\schedule-mcp-server' schedule-mcp"
  ],
  "description": "定时任务和大屏推送 MCP 服务",
  "headers": {},
  "tags": ["定时任务", "推送", "cron", "大屏"]
}
```
```json
{
  "mcpServers": {
    "schedule": {
      "command": "uvx",
      "args": [
        "--refresh",
        "--reinstall",
        "--from",
        "git+https://github.com/xjly/mcp#subdirectory=schedule-mcp-server",
        "schedule-mcp"
      ],
      "env": {
        "PUSH_SERVICE_URL": "http://localhost:8080/api/push",
        "PUSH_TIMEOUT": "30",
        "SCHEDULER_TIMEZONE": "Asia/Shanghai",
        "JOB_STORE_TYPE": "sqlite",
        "SQLITE_DB_PATH": "D:\\02_Projects\\Source\\mcp\\schedule-mcp-server\\jobs.sqlite"
      }
    }
  }
}
```

### 环境变量说明

- `PUSH_SERVICE_URL`：大屏推送服务地址。默认 mock 大屏地址是 `http://localhost:8080/api/push`
- `PUSH_TIMEOUT`：推送请求超时时间，单位秒
- `SCHEDULER_TIMEZONE`：定时任务时区，默认 `Asia/Shanghai`
- `JOB_STORE_TYPE`：任务存储类型，建议使用 `sqlite`
- `SQLITE_DB_PATH`：SQLite 持久化数据库路径，必须是本机文件路径，不能是 Git URL

## 启动方式

### 方式一：作为 MCP Server 使用

配置好 MCP 客户端后，客户端会通过 `uvx` 自动启动：

```text
schedule-mcp
```

一般不需要你手动运行 `src/schedule/server.py`。

### 方式二：本地联调 mock 大屏

如果没有真实大屏服务，可以启动本项目自带的 mock 大屏服务：

```powershell
cd D:\02_Projects\Source\mcp\schedule-mcp-server
uv run python test\mock_screen_test.py
```

启动后可访问：

- 健康检查：`http://localhost:8080/health`
- 查看推送记录：`http://localhost:8080/api/records`
- 清空推送记录：`http://localhost:8080/api/clear`
- 接收推送接口：`http://localhost:8080/api/push/{screen_id}`

mock 大屏会在 `test/push_records.db` 中保存推送记录。这个文件是运行时自动生成的，不需要提交到仓库。

## 工具用法

### 1. 创建定时推送任务

让 MCP 客户端调用 `schedule_task`：

```json
{
  "action": "create",
  "cron_expression": "0 8 * * *",
  "content": "早上好，当前时间：{current_time}",
  "push_target": "default_screen",
  "task_name": "每日早报"
}
```

返回结果中会包含 `task_id` 和下一次执行时间。

### 2. 列出所有定时任务

```json
{
  "action": "list"
}
```

### 3. 取消定时任务

```json
{
  "action": "cancel",
  "task_id": "schedule_xxxxxxxx"
}
```

`task_id` 来自创建任务或列出任务的返回结果。

### 4. 立即推送内容

调用 `push_to_screen`：

```json
{
  "content": "这是一条立即推送测试消息",
  "screen_id": "default_screen",
  "title": "测试推送"
}
```

## Cron 表达式示例

- `*/5 * * * *`：每 5 分钟执行一次
- `0 8 * * *`：每天 8 点执行
- `0 8,18 * * *`：每天 8 点和 18 点执行
- `0 9 * * 1-5`：工作日 9 点执行
- `0 0 1 * *`：每月 1 日 0 点执行

## 动态内容变量

定时任务内容支持下面变量：

- `{current_time}`：任务触发时的当前时间
- `{now}`：同 `{current_time}`

示例：

```text
当前时间：{current_time}
```

## 本地验证

编译检查：

```powershell
python -m compileall -q src test
```

验证部署和持久化：

```powershell
uv run python test\test_deploy.py
```

验证 MCP 工具调用：

```powershell
uv run python test\test_mcp.py
```

验证推送连接前，需要先启动 mock 大屏：

```powershell
uv run python test\mock_screen_test.py
```

然后另开一个终端运行：

```powershell
uv run python test\test_push_connection.py
```

## 常见问题

### 创建了任务，但没有推送到大屏

先确认大屏服务是否可用：

```powershell
curl http://localhost:8080/health
```

如果没有真实大屏，请先启动：

```powershell
uv run python test\mock_screen_test.py
```

### 任务列表为空

检查 `SQLITE_DB_PATH` 是否指向一个真实可写的本机 `.sqlite` 文件。如果返回路径出现在 `uv\cache\archive-v0` 下面，说明 MCP 客户端没有把环境变量传给子进程，或者运行的是旧版本代码。Yuxi 中可以使用 PowerShell 启动命令显式设置 `$env:SQLITE_DB_PATH`。

### 推送返回 502 或连接异常

本项目已经在推送请求中禁用了环境代理，避免 localhost 被代理转发。如果仍然失败，优先检查：

- `PUSH_SERVICE_URL` 是否正确
- `test\mock_screen_test.py` 是否已启动
- 端口 `8080` 是否被其它程序占用

### 移动项目后无法启动

如果 `--from` 使用 Git 地址，一般不需要因为移动项目而修改它。需要重点检查 `SQLITE_DB_PATH` 是否仍然是你想保存任务的本机路径：

```text
D:\02_Projects\Source\mcp\schedule-mcp-server\jobs.sqlite
```

如果你把数据库放到独立数据目录，也可以写成：

```text
D:\mcp-data\schedule-mcp\jobs.sqlite
```
