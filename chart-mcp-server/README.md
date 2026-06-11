# Chart MCP Server

这是一个用于“图表理解”和“图表结构生成”的 MCP Server。

它主要提供两个工具：

| 工具 | 用途 |
| --- | --- |
| `generate_chart` | 根据 JSON、数组或键值对象生成前端可渲染的 `chart_spec` |
| `explain_chart` | 从 MinIO 图片中下载图表，OCR 识别文字后生成图表解释 |

> 这个 MCP 只负责处理数据和图表理解，不直接渲染图表。真正的图表渲染需要由接入方前端根据返回的 `chart_spec` 完成。

## 安装要求

需要本机已安装：

- Python 3.12+
- `uv`

本地开发时，在项目目录执行：

```bash
uv sync
```

## MCP 客户端配置

### 方式一：本地源码运行

适合你正在本机开发这个仓库时使用。

```json
{
  "mcpServers": {
    "chart": {
      "command": "uv",
      "args": [
        "run",
        "--directory",
        "D:\\02_Projects\\Source\\mcp\\chart-mcp-server",
        "chart-mcp"
      ],
      "env": {
        "MINIO_ENDPOINT": "your-minio-host:9000",
        "MINIO_ACCESS_KEY": "your-minio-access-key",
        "MINIO_SECRET_KEY": "your-minio-secret-key",
        "MINIO_SECURE": "false",
        "DEFAULT_BUCKET": "kb-images",
        "DEFAULT_CHAT_IMAGES_PATH": "chat-images",
        "OCR_PROCESSOR": "deepseek_ocr",
        "OCR_MODEL": "deepseek-ai/DeepSeek-OCR",
        "LLM_API_URL": "https://api.siliconflow.cn/v1/chat/completions",
        "LLM_API_KEY": "your-llm-api-key",
        "LLM_MODEL": "deepseek-ai/DeepSeek-V3"
      }
    }
  }
}
```

### 方式二：从 Git 仓库安装运行

适合给别人使用，或者不想保留本地源码目录时使用。

```json
{
  "mcpServers": {
    "chart": {
      "command": "uvx",
      "args": [
        "--from",
        "git+https://github.com/xjly/mcp#subdirectory=chart-mcp-server",
        "chart-mcp"
      ],
      "env": {
        "MINIO_ENDPOINT": "your-minio-host:9000",
        "MINIO_ACCESS_KEY": "your-minio-access-key",
        "MINIO_SECRET_KEY": "your-minio-secret-key",
        "MINIO_SECURE": "false",
        "DEFAULT_BUCKET": "kb-images",
        "DEFAULT_CHAT_IMAGES_PATH": "chat-images",
        "OCR_PROCESSOR": "deepseek_ocr",
        "OCR_MODEL": "deepseek-ai/DeepSeek-OCR",
        "LLM_API_URL": "https://api.siliconflow.cn/v1/chat/completions",
        "LLM_API_KEY": "your-llm-api-key",
        "LLM_MODEL": "deepseek-ai/DeepSeek-V3"
      }
    }
  }
}
```

不要把真实的 `MINIO_ACCESS_KEY`、`MINIO_SECRET_KEY`、`LLM_API_KEY` 提交到仓库。建议只放在你本机 MCP 客户端配置或 `.env` 文件里。

## 环境变量说明

| 变量 | 必填 | 说明 |
| --- | --- | --- |
| `MINIO_ENDPOINT` | 是 | MinIO 服务地址，例如 `127.0.0.1:9000` |
| `MINIO_ACCESS_KEY` | 是 | MinIO access key |
| `MINIO_SECRET_KEY` | 是 | MinIO secret key |
| `MINIO_SECURE` | 否 | 是否使用 HTTPS，默认 `false` |
| `DEFAULT_BUCKET` | 否 | 默认图片 bucket，默认 `kb-images` |
| `DEFAULT_CHAT_IMAGES_PATH` | 否 | 默认图片路径前缀，默认 `chat-images` |
| `OCR_PROCESSOR` | 否 | OCR 处理器，默认 `deepseek_ocr` |
| `OCR_MODEL` | 否 | OCR 模型，默认 `deepseek-ai/DeepSeek-OCR` |
| `LLM_API_URL` | 否 | OpenAI 兼容接口地址 |
| `LLM_API_KEY` | 是 | LLM/OCR API key |
| `LLM_MODEL` | 否 | 图表解释模型，默认 `deepseek-ai/DeepSeek-V3` |

兼容旧变量名：如果没有设置 `DEFAULT_BUCKET` / `DEFAULT_CHAT_IMAGES_PATH`，程序会尝试读取 `MINIO_KB_BUCKET` / `MINIO_CHAT_IMAGES_PATH`。

## 工具用法

### generate_chart

根据输入数据生成图表结构。

参数：

| 参数 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `data_json` | object / array / string | 是 | 图表数据，可以是数组、对象或 JSON 字符串 |
| `chart_type` | string | 否 | 图表类型，例如 `bar`、`line`、`pie`、`area` |
| `title` | string | 否 | 图表标题 |
| `text` | string | 否 | 补充说明，也可作为标题后备 |
| `threshold` | number | 否 | 阈值线 |

示例输入：

```json
{
  "data_json": [
    { "name": "Q1", "value": 120 },
    { "name": "Q2", "value": 135 },
    { "name": "Q3", "value": 160 }
  ],
  "chart_type": "bar",
  "title": "季度销售数据"
}
```

示例返回：

```json
{
  "type": "chart",
  "mode": "generate",
  "ok": true,
  "chart_type": "bar",
  "data_points": 3,
  "chart_spec": {
    "type": "bar",
    "title": "季度销售数据",
    "x_field": "name",
    "y_field": "value",
    "values": [
      { "name": "Q1", "value": 120 },
      { "name": "Q2", "value": 135 },
      { "name": "Q3", "value": 160 }
    ]
  },
  "explanation": "已成功生成季度销售数据。数据点共 3 个。"
}
```

### explain_chart

从 MinIO 图片地址中下载图表图片，调用 OCR 提取文字，再调用 LLM 生成解释。

参数：

| 参数 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `chart_url` | string | 是 | 图表图片 URL 或对象路径 |
| `text` | string | 否 | 用户提供的背景说明 |
| `ocr_processor` | string | 否 | OCR 处理器，默认读取 `OCR_PROCESSOR` |

示例输入：

```json
{
  "chart_url": "http://your-minio-host:9000/kb-images/chat-images/example.png",
  "text": "这是水位监测图表"
}
```

示例返回：

```json
{
  "mode": "explain",
  "ok": true,
  "ocr_text": "识别出的图表文字...",
  "image_url": "http://your-minio-host:9000/kb-images/chat-images/example.png",
  "explanation": "这张图展示了..."
}
```

## 本地验证

运行基础测试：

```bash
uv run python test_chart.py
```

手动测试 OCR：

```bash
set LLM_API_KEY=your-llm-api-key
set OCR_TEST_IMAGE_URL=http://your-minio-host:9000/kb-images/chat-images/example.png
uv run python test_real_ocr.py
```

PowerShell 中可以写成：

```powershell
$env:LLM_API_KEY="your-llm-api-key"
$env:OCR_TEST_IMAGE_URL="http://your-minio-host:9000/kb-images/chat-images/example.png"
uv run python test_real_ocr.py
```

## 常见问题

### 客户端连不上 MCP

确认 MCP 配置中的 `command` 和 `args` 正确。如果使用本地源码运行，`--directory` 必须指向这个项目目录。

### 不要向 stdout 打印日志

MCP 默认使用 stdio 通信，stdout 会被 JSON-RPC 协议占用。服务内部日志应通过 logging 输出到 stderr，避免污染协议流。

### OCR 返回未设置 API Key

检查 `LLM_API_KEY` 是否已经配置。`explain_chart` 的 OCR 和图表解释都依赖这个 key。

### 图片下载失败

检查：

- `MINIO_ENDPOINT` 是否正确
- `MINIO_ACCESS_KEY` / `MINIO_SECRET_KEY` 是否有效
- `DEFAULT_BUCKET` 和 `DEFAULT_CHAT_IMAGES_PATH` 是否与图片实际路径一致
- `chart_url` 是否能在 MinIO 中找到对应对象
