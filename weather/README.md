# Weather MCP Server

和风天气 MCP 服务，提供城市/区名解析、预报和历史气象数据查询。

## 功能概述

- `search_location_id_by_name`：根据城市名或区名查找候选 `location_id`
- `get_weather_forecast`：按 `location_id` 查询未来天气（`hourly` / `daily`）
- `get_weather_history`：按 `location_id` 查询历史天气（`hourly` / `daily`，支持 `date`）
- `get_minutely_precipitation`：按经纬度查询分钟级降水预报（5 分钟步长）
- `get_weather_alert_current`：按经纬度查询实时天气预警（仅返回 `alerts` 原始列表）

## 环境变量

- `QWEATHER_API_KEY`（必填）
- `QWEATHER_BASE_URL`（可选，默认 `https://devapi.qweather.com`，专属 key 请改为专属域名）
- `QWEATHER_TIMEOUT_SECONDS`（可选，默认 `30`）

> 提示：如果你的 key 是和风专属项目 key，`QWEATHER_BASE_URL` 需配置为类似
> `https://<your-host>.re.qweatherapi.com` 的专属 host。

## 本地运行

```bash
uv sync
uv run python -m weather.server
```

## MCP 客户端配置示例

```json
{
  "mcpServers": {
    "weather": {
      "command": "uvx",
      "args": [
        "--from",
        "git+https://github.com/xjly/mcp#subdirectory=weather",
        "weather-mcp"
      ],
      "env": {
        "QWEATHER_API_KEY": "your_api_key"
      }
    }
  }
}
```

## 推荐调用流程

1. 先调用 `search_location_id_by_name` 获取候选 `location_id`
2. 调用 `get_weather_forecast` 或 `get_weather_history` 查询按小时/按天数据
3. 需要临近降水时，调用 `get_minutely_precipitation`
4. 需要灾害/大风等预警时，调用 `get_weather_alert_current`

历史天气建议显式传入 `date`（`YYYYMMDD` 或 `YYYY-MM-DD`），例如：

```json
{
  "name": "get_weather_history",
  "arguments": {
    "location_id": "101190401",
    "granularity": "daily",
    "days": 1,
    "date": "2026-04-23"
  }
}
```

## 分钟级降水工具示例

```json
{
  "name": "get_minutely_precipitation",
  "arguments": {
    "lon": 120.31189,
    "lat": 31.49106,
    "minutes": 30
  }
}
```

## 实时天气预警工具示例

```json
{
  "name": "get_weather_alert_current",
  "arguments": {
    "lon": 116.40,
    "lat": 39.90,
    "lang": "zh",
    "local_time": true
  }
}
```

## 常见问题

- `QWEATHER_API_KEY is required`：未配置 API Key
- `granularity must be 'hourly' or 'daily'`：粒度参数非法
- 历史数据为空或报错：和风历史接口权限可能受套餐限制
