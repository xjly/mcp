# Chart MCP Server

图表理解和生成 MCP Server，提供图表 OCR 识别和数据可视化能力。
但是需要借助yuxi的前端，才能正常工作。
图表渲染是在yuxi前端进行的。（这个工具只负责处理图表数据，即转换为json格式的数据）

## 功能概述

| 工具 | 说明 |
|------|------|
| `explain_chart` | 解释已有图表（OCR + 分析） |
| `generate_chart` | 根据数据生成图表结构 |

## 快速开始

```bash
# 配置环境变量
# MinIO 配置（从主项目配置获取）
MINIO_ENDPOINT=114.66.47.144:9000
MINIO_ACCESS_KEY=minioadmin
MINIO_SECRET_KEY=minioadmin
MINIO_SECURE=False
MINIO_BUCKET=wuxi-data

# MinIO 路径配置
MINIO_KB_BUCKET=kb-images
MINIO_CHAT_IMAGES_PATH=chat-images

# OCR 配置
OCR_PROCESSOR=onnx_rapid_ocr

# LLM 配置（使用硅基流动）
LLM_MODEL_PROVIDER=siliconflow
LLM_API_KEY=your-siliconflow-api-key
LLM_MODEL=deepseek-ai/DeepSeek-V3

# 默认配置
DEFAULT_BUCKET=kb-images
DEFAULT_CHAT_IMAGES_PATH=chat-images

# MCP 服务器配置文件
{
  "mcpServers": {
    "chart": {
      "command": "uv",
      "args": [
        "run",
        "--directory",
        "e:\\mcp-master\\mcp-master\\chart-mcp-server",
        "chart-mcp"
      ],
     "env": {
        "MINIO_ENDPOINT": "114.66.47.144:9000",
        "MINIO_ACCESS_KEY": "minioadmin",
        "MINIO_SECRET_KEY": "minioadmin",
        "MINIO_SECURE": "False",
        "MINIO_KB_BUCKET": "kb-images",
        "MINIO_CHAT_IMAGES_PATH": "chat-images",
        "OCR_PROCESSOR": "deepseek_ocr",
        "OCR_MODEL": "deepseek-ai/DeepSeek-OCR",
        "LLM_API_URL": "https://api.siliconflow.cn/v1/chat/completions",
        "LLM_MODEL_PROVIDER": "siliconflow",
        "LLM_API_KEY": "your-siliconflow-api-key",# 从硅基流动获取的 API 密钥
        "LLM_MODEL": "deepseek-ai/DeepSeek-V3",
        "DEFAULT_BUCKET": "kb-images",
        "DEFAULT_CHAT_IMAGES_PATH": "chat-images"
      }
    }
  }
}