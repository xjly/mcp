"""File Template MCP Server - 公文模板填充服务

提供基于 Jinja2 和 LLM 的智能文档模板填充能力。
"""

import logging
import os
import sys
import json
from typing import Annotated, Optional, List, Dict, Any

import jinja2
from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP
from langchain_openai import ChatOpenAI

from file.config import get_llm_config

# 加载环境变量
load_dotenv()

# 配置日志到 stderr
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    stream=sys.stderr
)
logger = logging.getLogger("file-mcp")

# =============================================================================
# === MCP 服务器定义 ===
# =============================================================================

mcp = FastMCP(
    "file-template",
    instructions="""
## 公文模板填充服务

### 服务能力
本服务根据指定的模板和数据，填充内容并生成完整的公文。

### 核心特性
- **双引擎填充**: 
  - **Jinja2 引擎**: 支持 `{{变量}}` 格式的高效填充。
  - **LLM 智能引擎**: 智能识别 `____`、空格、下划线等非标准占位符。
- **模板来源**:
  - **内置模板**: 从服务器内置的模板库加载。
  - **动态模板**: 支持通过参数直接传递模板内容。

### 使用建议
1. 优先使用 `{{...}}` 语法以获得最高填充效率。
2. 对于非标准占位符或需要理解上下文的填充，请确保提供足够的上下文。
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
        temperature=0.0  # 模板填充通常需要更确定的结果
    )

# =============================================================================
# === MCP 工具注册 ===
# =============================================================================

@mcp.tool(name="fill_document_template")
async def fill_document_template(
    template_name: Annotated[str, "模板文件的名称，例如 'monthly_report.txt'"],
    data: Annotated[dict, "用于填充模板的键值对数据"],
    template_content_override: Annotated[Optional[str], "如果提供此项，将直接使用此内容作为模板，忽略 template_name"] = None
) -> str:
    """
    公文模板填充工具：智能双引擎，自动识别模板格式。
    - `{{...}}` -> Jinja2 引擎
    - `____` -> LLM 智能填充引擎
    """
    try:
        template_content = None
        source = ""

        if template_content_override:
            template_content = template_content_override
            source = "dynamic override"
        else:
            # 尝试从预置模板库加载
            template_dir = os.path.abspath(
                os.path.join(os.path.dirname(__file__), "..", "..", "config", "static", "templates")
            )
            
            if not os.path.exists(template_dir):
                os.makedirs(template_dir, exist_ok=True)
                
            env = jinja2.Environment(
                loader=jinja2.FileSystemLoader(template_dir),
                autoescape=jinja2.select_autoescape(),
            )

            try:
                template_content = env.loader.get_source(env, template_name)[0]
                source = f"pre-defined template: {template_name}"
            except jinja2.TemplateNotFound:
                return f"错误：找不到名为 '{template_name}' 的模板文件（且未提供覆盖内容）。已检查预置库路径: {template_dir}"

        if not template_content:
            return f"错误：模板内容为空。"

        # --- 智能双引擎判断 ---
        # 如果包含 Jinja2 占位符，使用 Jinja2 引擎（最高效）
        if "{{" in template_content:
            logger.info(f"Using Jinja2 engine for {source}")
            template = jinja2.Template(template_content)
            return template.render(data)

        # 否则，统一使用 LLM 智能填充引擎（处理 ____、空格、下划线等各种非标准占位符）
        logger.info(f"Using LLM engine for intelligent filling: {source}")
        system_prompt = (
            "你是一个严格执行指令的文档填充机器人。你的唯一任务是接收一个模板和一份JSON数据，然后输出填充后的文档。"
            "你绝不能添加任何解释、评论或与模板无关的文字。\n\n"
            "填充规则：\n"
            "1. **精准匹配**：根据模板中的上下文（如表格标题、段落标题），将JSON数据填入最合适的位置（如 `____`、空格或标题后的空白处）。\n"
            "2. **格式铁律**：必须100%保留模板的原始格式，包括Markdown、空格、换行和特殊字符。\n"
            "3. **绝对纯净输出**：你的输出**只能也必须是**填充后的文档本身。禁止任何形式的前言（如‘这是填充后的文档：’）或结尾。\n"
        )

        user_prompt = (
            f"待填充模板：\n---\n{template_content}\n---\n\n"
            f"填充数据：\n---\n{json.dumps(data, ensure_ascii=False, indent=2)}\n---\n\n"
            "请根据数据填充模板并输出最终文档。"
        )

        try:
            model = get_model()
            messages = [
                ("system", system_prompt),
                ("user", user_prompt)
            ]
            response = await model.ainvoke(messages)
            return response.content
        except Exception as e:
            logger.error(f"LLM-based template filling error: {e}")
            return f"智能填充模板失败: {str(e)}"

    except Exception as e:
        logger.error(f"Template filling error: {e}")
        return f"模板填充失败: {str(e)}"

# =============================================================================
# === 启动入口 ===
# =============================================================================

def main():
    """主入口函数"""
    mcp.run()
