"""Word Polish MCP Server - 文字润色服务

提供基于 LLM 的专业文字润色能力
"""

import logging
import sys
from typing import Annotated

from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP
from langchain_openai import ChatOpenAI

from word.config import get_llm_config

# 加载环境变量
load_dotenv()

# 配置日志到 stderr，避免干扰 MCP 的 stdout 通讯
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    stream=sys.stderr
)
logger = logging.getLogger("word-mcp")

# =============================================================================
# === MCP 服务器定义 ===
# =============================================================================

mcp = FastMCP(
    "word-polish",
    instructions="""
## 文字润色服务

### 服务能力
本服务提供专业的文字润色能力，能够将粗糙的文本转换为符合特定规范的表达。

### 支持风格
- **政府公文**: 严谨、庄重、规范。
- **业务报告**: 专业、客观、逻辑性强。
- **技术文档**: 精确、清晰、无歧义。
- **简明扼要**: 剔除冗余，直击重点。

### 使用建议
1. 提供清晰的原始文本。
2. 指定目标风格以获得最准确的结果。
3. 如果有特殊术语或语气要求，请在 requirements 中说明。
""",
)

# =============================================================================
# === LLM 客户端初始化 ===
# =============================================================================

def get_model():
    """使用统一配置初始化 ChatOpenAI 模型"""
    config = get_llm_config()
    
    return ChatOpenAI(
        model=config.default_model,
        openai_api_key=config.api_key,
        openai_api_base=config.base_url,
        request_timeout=config.timeout_seconds,
        temperature=0.3
    )
# =============================================================================
# === MCP 工具注册 ===
# =============================================================================

@mcp.tool(name="polish_text")
async def polish_text(
    text: Annotated[str, "需要润色的原始文字内容"],
    style: Annotated[str, "润色风格，可选：'政府公文'、'业务报告'、'技术文档'、'简明扼要'"] = "政府公文",
    requirements: Annotated[str, "额外的润色要求，如：'增加专业术语'、'语气更委婉'等"] = ""
) -> str:
    """
    文字润色工具：将输入的文字转换为符合特定规范（如政府公文、业务报告）的专业表达。
    """
    system_prompt = (
        f"你是一个严格执行指令的文字润色机器人。你的唯一任务是根据用户的要求，将输入的文字润色成指定的风格。\n"
        f"当前润色风格目标：{style}\n"
        f"额外要求：{requirements}\n\n"
        f"润色原则：\n"
        f"1. 保持原意：不要改变作者想要传达的核心信息。\n"
        f"2. 规范表达：使用符合{style}规范的术语和句式。\n"
        f"3. 逻辑严密：增强文字的逻辑性和条理性。\n"
        f"4. 简洁凝练：去除冗余信息，用词精准。\n\n"
        f"格式铁律：\n"
        f"你的输出**只能也必须是**润色后的最终文本本身。\n"
        f"禁止任何形式的解释、评论、前言或结尾（例如，不要说‘这是润色后的版本：’）。"
    )

    user_prompt = f"请对以下文字进行润色：\n\n{text}"

    try:
        model = get_model()
        # 使用 standard langchain 调用方式
        messages = [
            ("system", system_prompt),
            ("user", user_prompt)
        ]
        response = await model.ainvoke(messages)
        return response.content
    except Exception as e:
        logger.error(f"Polish text error: {e}")
        return f"文字润色失败: {str(e)}"

# =============================================================================
# === 启动入口 ===
# =============================================================================

def main():
    """主入口函数"""
    mcp.run()