# 水务报表 MCP

`reporter-mcp` 以 stdio 提供 PostgreSQL 闸站设备和水质监测查询。使用 `DATABASE_URL` 配置连接，支持 `postgresql://` 和 `postgresql+asyncpg://`。专用数据库账号需要业务表的 `SELECT` 权限。标准连接串可携带 `sslmode` 等 PostgreSQL 连接参数，密码中的保留字符按 URI 规则编码。

可从本目录运行 `uv run --locked reporter-mcp`，客户端配置参考 [mcp.example.json](mcp.example.json)。工具的数据库操作采用只读会话，包含连接、连接池等待和查询在内的操作时限为 30 秒。

## 历史数据和按时段统计

|工具|可选筛选|分组粒度|
|---|---|---|
|`get_gate_station_history`|`station_name`、`device_type`|按站点、设备和时段分别统计，包含样本数、活跃样本数和读数的最小值、最大值、平均值|
|`get_water_quality_history`|`station_name`|按监测站和时段分别统计 COD、氨氮、溶解氧的样本数、最小值、最大值、平均值|

两个工具均接受 `start_time` 和 `end_time`，开始时间包含在查询内，结束时间不包含。输入可以是 ISO 8601 日期或时间戳。无时区输入及数据库的无时区时间字段按上海业务时间解释，带时区输入会换算成上海时间。查询最多覆盖 366 天。

省略 `group_by` 返回原始监测记录，填写 `hour` 或 `day` 返回小时或自然日统计。空值和非有限读数不计入数值统计。无有效读数时，统计的 `count` 为 0，最小值、最大值、平均值为 `null`。

例如查询某天的水质日报，可将以下参数传给 `get_water_quality_history`。

```json
{
  "start_time": "2026-11-16",
  "end_time": "2026-11-17",
  "group_by": "day",
  "limit": 100,
  "offset": 0
}
```

新工具通过 `structuredContent` 返回 `rows` 和分页信息。`limit` 默认为 100，最大 1000。若 `has_more` 为 `true`，下一页以 `next_offset` 作为 `offset`。已有七个列表、最近数据和概览工具继续返回 JSON 文本。
