"""Schedule MCP Server - 定时任务和大屏推送服务"""

import asyncio
import json
import logging
import sys
import uuid
from datetime import datetime

import arrow
from croniter import croniter
from mcp.server.fastmcp import FastMCP

from schedule.scheduler import get_schedule_service
from schedule.pusher import get_push_service
from schedule.utils import safe_result

logger = logging.getLogger(__name__)

# ============================================================================
# MCP 服务器定义
# ============================================================================

mcp = FastMCP(
    "schedule-mcp",
    instructions="""
## 定时任务和大屏推送服务

### 服务能力
本服务提供定时任务管理和消息推送能力：
- **schedule_task**: 管理定时任务（创建/取消/列出）
- **push_to_screen**: 推送内容到大屏

### 持久化特性 
- 任务存储在 SQLite 数据库中，MCP 服务重启后任务不会丢失
- 支持查看历史创建的所有定时任务
- 任务状态在服务器重启后自动恢复

### 典型工作流

**工作流1：创建定时推送任务**
1. 调用 `schedule_task`，action="create"
2. 提供 cron_expression 和 content
3. 系统会在指定时间自动推送内容

**工作流2：查看所有定时任务**
1. 调用 `schedule_task`，action="list"

**工作流3：取消定时任务**
1. 调用 `schedule_task`，action="cancel"
2. 提供 task_id

**工作流4：即时推送**
1. 调用 `push_to_screen` 立即推送

### Cron 表达式示例
- `*/2 * * * *` - 每2分钟执行
- `0 8 * * *` - 每天上午8点
- `0 8,18 * * *` - 每天8点和18点
- `0 9 * * 1-5` - 工作日9点
- `0 0 1 * *` - 每月1号凌晨

### 注意事项
-  任务持久化：服务重启后任务依然存在
-  推送内容支持 Markdown 格式
-  使用 `{current_time}` 动态插入当前时间
""",
)


# ============================================================================
# 全局回调函数（需要独立定义以便序列化）
# ============================================================================

def on_timer_triggered(
    content: str,
    push_target: str,
    job_id: str,
    task_name: str
):
    """
    定时器触发时的回调函数（同步函数，内部创建异步任务）
    注意：必须是同步函数！APScheduler 不会 await 异步函数。
    """
    async def _do_push():
        try:
            current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            dynamic_content = content.replace("{current_time}", current_time).replace("{now}", current_time)
            
            logger.info("开始执行定时任务 %s", job_id)
            push_svc = get_push_service()
            push_result = await push_svc.push_to_screen(
                content=dynamic_content,
                screen_id=push_target,
                title=task_name
            )
            
            logger.info("定时任务 %s 推送结果 %s", job_id, push_result.get("status", "unknown"))
        except Exception as exc:
            logger.error("定时任务 %s 执行失败 (%s)", job_id, type(exc).__name__)
    
    # 在现有事件循环中创建任务
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(_do_push())
    except RuntimeError:
        # 没有运行中的事件循环，创建新的
        asyncio.run(_do_push())



# ============================================================================
# MCP 工具注册
# ============================================================================


@mcp.tool()
async def schedule_task(
    action: str,
    cron_expression: str = None,
    content: str = None,
    push_target: str = "default_screen",
    task_name: str = "定时任务",
    task_id: str = None,
) -> str:
    """
    管理定时任务。支持创建、取消和列出定时任务。
    任务会持久化存储，服务重启后不会丢失。

    Args:
        action: 操作类型 - "create"(创建), "cancel"(取消), "list"(列出)
        cron_expression: cron 表达式，如 "0 8 * * *"（创建时必需）
        content: 定时到达时要推送的内容，可使用 {current_time} 动态替换时间（创建时必需）
        push_target: 目标大屏 ID，默认为 "default_screen"
        task_name: 任务显示名称，默认为 "定时任务"
        task_id: 取消任务时需要的任务 ID（取消时必需）

    Returns:
        JSON 字符串，包含操作结果
    """

    schedule_svc = get_schedule_service()

    # ========== 列出所有任务 ==========
    if action == "list":
        jobs = schedule_svc.list_jobs()
        result = {
            "status": "success",
            "action": "list",
            "total": len(jobs),
            "store_type": schedule_svc.get_store_type(),
            "persistent": schedule_svc.is_persistent(),
            "db_path": schedule_svc.get_db_path(),
            "tasks": jobs
        }
        logger.debug("列出 %d 个定时任务", len(jobs))
        return json.dumps(result, ensure_ascii=False, indent=2)

    # ========== 创建定时任务 ==========
    elif action == "create":
        if not cron_expression or not content:
            error_msg = "创建任务缺少必要参数: cron_expression 和 content"
            return json.dumps({
                "status": "error",
                "message": error_msg
            }, ensure_ascii=False, indent=2)

        # 验证 cron 表达式
        try:
            base_time = arrow.now()
            cron = croniter(cron_expression, base_time.datetime)
            next_run_dt = cron.get_next(datetime)
        except Exception as e:
            error_msg = f"无效的 cron 表达式: {cron_expression}, 错误: {str(e)}"
            return json.dumps({
                "status": "error",
                "message": error_msg
            }, ensure_ascii=False, indent=2)

        # 生成唯一任务 ID
        job_id = f"schedule_{uuid.uuid4().hex[:8]}"

        # 添加到调度器（使用独立定义的全局回调函数）
        success = await schedule_svc.add_cron_job(
            job_id=job_id,
            cron_expr=cron_expression,
            callback=on_timer_triggered,
            task_name=task_name,
            content=content,
            push_target=push_target
        )

        if success:
            
            result = {
                "status": "success",
                "action": "create",
                "task_id": job_id,
                "task_name": task_name,
                "cron_expression": cron_expression,
                "next_run": next_run_dt.strftime("%Y-%m-%d %H:%M:%S"),
                "push_target": push_target,
                "content_preview": content[:100] + "..." if len(content) > 100 else content,
                "store_type": schedule_svc.get_store_type(),
                "persistent": schedule_svc.is_persistent(),
                "db_path": schedule_svc.get_db_path(),
                "message": f" 定时任务「{task_name}」已创建，下次执行时间: {next_run_dt.strftime('%Y-%m-%d %H:%M:%S')}"
            }
            return json.dumps(result, ensure_ascii=False, indent=2)
        else:
            error_msg = f"创建定时任务失败: {task_name}"
            return json.dumps({
                "status": "error",
                "action": "create",
                "message": error_msg
            }, ensure_ascii=False, indent=2)

    # ========== 取消定时任务 ==========
    elif action == "cancel":
        if not task_id:
            error_msg = "取消任务需要提供 task_id"
            return json.dumps({
                "status": "error",
                "message": error_msg
            }, ensure_ascii=False, indent=2)

        success = schedule_svc.remove_job(task_id)

        if success:
            result = {
                "status": "success",
                "action": "cancel",
                "task_id": task_id,
                "message": f" 定时任务 {task_id} 已成功取消"
            }
            return json.dumps(result, ensure_ascii=False, indent=2)
        else:
            error_msg = f"未找到任务或取消失败: {task_id}"
            return json.dumps({
                "status": "error",
                "action": "cancel",
                "task_id": task_id,
                "message": error_msg
            }, ensure_ascii=False, indent=2)

    else:
        error_msg = f"不支持的操作: {action}，支持: create, cancel, list"
        return json.dumps({
            "status": "error",
            "message": error_msg
        }, ensure_ascii=False, indent=2)


@mcp.tool()
async def push_to_screen(
    content: str,
    screen_id: str = "default_screen",
    title: str = None,
) -> str:
    """
    推送内容到大屏显示。

    Args:
        content: 需要推送的文本或数据，支持 Markdown 格式
        screen_id: 大屏的标识符，默认为 "default_screen"
        title: 推送标题，可选

    Returns:
        JSON 字符串，包含推送结果
    """
    push_svc = get_push_service()
    result = await push_svc.push_to_screen(
        content=content,
        screen_id=screen_id,
        title=title
    )
    logger.info("即时推送结果 %s", result.get("status", "unknown"))
    return json.dumps(safe_result(result), ensure_ascii=False, indent=2)


# ============================================================================
# 启动入口
# ============================================================================

def main():
    """主入口函数"""
    logging.basicConfig(level=logging.INFO, stream=sys.stderr)
    logger.info("Schedule MCP Server 启动中")
    try:
        mcp.run()
    except KeyboardInterrupt:
        logger.info("服务被用户中断")
    except Exception as exc:
        logger.error("Schedule MCP Server 异常退出 (%s)", type(exc).__name__)


if __name__ == "__main__":
    main()
