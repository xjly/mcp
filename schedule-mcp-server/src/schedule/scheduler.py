"""Schedule Service - 调度器服务层（支持任务持久化）"""

import os
import uuid
from datetime import datetime
from typing import Callable, Optional, Dict
from dataclasses import dataclass, field

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.jobstores.base import JobLookupError
from apscheduler.jobstores.memory import MemoryJobStore
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from croniter import croniter
import arrow

@dataclass
class ScheduledJob:
    """定时任务数据模型"""
    job_id: str
    name: str
    cron_expr: str
    content: str                    # 保存推送内容模板
    push_target: str                # 保存推送目标
    next_run_time: Optional[datetime] = None
    created_at: str = field(default_factory=lambda: arrow.now().isoformat())
    callback: Optional[Callable] = None


class ScheduleService:
    """调度服务 - 管理 cron 定时任务（支持持久化）"""

    def __init__(self):
        
        # 从环境变量读取配置（MCP 客户端通过 env 传递）
        self._timezone = os.getenv("SCHEDULER_TIMEZONE", "Asia/Shanghai")
        self._job_store_type = os.getenv("JOB_STORE_TYPE", "sqlite")
        self._db_path = None  # ← 新增：保存数据库路径

        print(f"[ScheduleService] ========== 初始化调试信息 ==========")
        print(f"[ScheduleService] JOB_STORE_TYPE = {self._job_store_type}")
        print(f"[ScheduleService] SCHEDULER_TIMEZONE = {self._timezone}")
        print(f"[ScheduleService] SQLITE_DB_PATH = {os.getenv('SQLITE_DB_PATH', '未设置')}")
        print(f"[ScheduleService] PWD = {os.getcwd()}")
        print(f"[ScheduleService] __file__ = {__file__}")
        print(f"[ScheduleService] ========================================")
        # 根据配置选择任务存储方式
        jobstores = self._create_jobstores()
        
        self._scheduler = AsyncIOScheduler(
            jobstores=jobstores,
            timezone=self._timezone,
            job_defaults={
                'coalesce': True,      # 合并错过的任务
                'max_instances': 1,    # 最多同时运行一个实例
                'misfire_grace_time': 60  # 错过任务的宽容时间（秒）
            }
        )
        self._jobs: Dict[str, ScheduledJob] = {}
        self._running = False


    def _create_jobstores(self) -> dict:
        """根据配置创建任务存储"""

        # 调试信息
        print(f"[_create_jobstores] ========== 路径调试 ==========")
        print(f"[_create_jobstores] SQLITE_DB_PATH 环境变量: {os.getenv('SQLITE_DB_PATH', '未设置')}")
        print(f"[_create_jobstores] JOB_STORE_TYPE 环境变量: {os.getenv('JOB_STORE_TYPE', '未设置')}")
        print(f"[_create_jobstores] 当前工作目录 (cwd): {os.getcwd()}")
        print(f"[_create_jobstores] 当前文件位置 (__file__): {__file__}")

        
        if self._job_store_type == "sqlite":
            # 方法1: 优先使用环境变量（MCP 客户端会设置）
            db_path = os.getenv("SQLITE_DB_PATH")
        
            if not db_path:
                # 方法2: 基于 __file__ 计算项目根目录
                # __file__ = E:\...\src\schedule\scheduler.py
                # 上两级 = E:\...\src
                # 上三级 = E:\...\  (项目根目录)
                current_file = os.path.abspath(__file__)
                # 从 src/schedule/scheduler.py 向上找到项目根目录
                src_dir = os.path.dirname(os.path.dirname(os.path.dirname(current_file)))
                # 再上一级就是项目根目录
                project_root = os.path.dirname(src_dir) if os.path.basename(src_dir) == 'src' else src_dir
                db_path = os.path.join(project_root, "jobs.sqlite")
                print(f"[_create_jobstores] 自动计算路径: {db_path}")
                self._db_path = db_path  # ← 新增：保存数据库路径
        
            # 转换为绝对路径
            db_path = os.path.abspath(db_path)
            print(f"[_create_jobstores] 最终数据库路径: {db_path}")

            # 确保目录存在
            db_dir = os.path.dirname(db_path)
            if db_dir:
                os.makedirs(db_dir, exist_ok=True)
                print(f"[_create_jobstores] 已确保目录存在: {db_dir}")
  
            sqlalchemy_url = f'sqlite:///{db_path}'
            print(f"[_create_jobstores] SQLAlchemy URL: {sqlalchemy_url}")
            print(f"[_create_jobstores] ================================")
            
            return {
                'default': SQLAlchemyJobStore(
                    url=sqlalchemy_url,
                    tablename='apscheduler_jobs'
                )
            }
        elif self._job_store_type == "postgresql":
            postgresql_url = os.getenv("POSTGRESQL_URL")
            if not postgresql_url:
                raise ValueError("使用 postgresql 存储需要配置 POSTGRESQL_URL")
            print(f"[_create_jobstores] 使用 PostgreSQL: {postgresql_url}")
            return {
                'default': SQLAlchemyJobStore(url=postgresql_url)
            }
        else:
            print(f"[_create_jobstores] 使用内存存储（任务不会持久化）")
            return {
                'default': MemoryJobStore()
            }

    def get_db_path(self) -> str:
        """获取数据库存储路径"""
        if self._db_path:
            return self._db_path
        return "内存存储（无持久化）"

    def _load_jobs_from_store(self):
        """从持久化存储加载任务信息到内存缓存"""
        try:
            from schedule.server import on_timer_triggered  # 导入回调函数,第一处

            # 获取调度器中所有已存储的任务
            jobs = self._scheduler.get_jobs()
            print(f"[_load_jobs_from_store] 从调度器获取到 {len(jobs)} 个任务")

            for job in jobs:
                # 强制重新绑定回调函数为正确的模块引用
                job.func = on_timer_triggered  #第二处
                job.func_ref = 'schedule.server:on_timer_triggered'
                # 从 job 的 kwargs 中恢复自定义字段
                job_info = ScheduledJob(
                    job_id=job.id,
                    name=job.name,
                    cron_expr=str(job.trigger),
                    content=job.kwargs.get('content', ''),
                    push_target=job.kwargs.get('push_target', 'default_screen'),
                    callback=job.func  # 保存回调函数引用
                )
                self._jobs[job.id] = job_info
                print(f"[_load_jobs_from_store] 加载任务: {job.id} - {job.name}")
                
            if self._job_store_type != "memory" and self._jobs:
                print(f"[_load_jobs_from_store] 从持久化存储加载了 {len(self._jobs)} 个定时任务")
            elif self._job_store_type != "memory":
                print(f"[_load_jobs_from_store] 持久化存储中没有任务")
        except Exception as e:
            print(f"[_load_jobs_from_store] 加载持久化任务失败: {e}")
            import traceback
            traceback.print_exc()

    def start(self):
        """启动调度器"""
        if not self._running:
            print(f"[start] 正在启动调度器...")
            self._scheduler.start()
            self._running = True
            print(f" 调度器已启动 (存储类型: {self._job_store_type})")
            # 添加心跳任务，保持调度器活跃
            try:
                self._scheduler.add_job(
                    lambda: print("[心跳] 调度器运行中"),
                    trigger=CronTrigger.from_crontab('* * * * *'),
                    id='heartbeat',
                    name='心跳检测',
                    replace_existing=True
                )
            except:
                pass
            # 启动后从数据库加载任务信息到内存缓存
            print(f"[start] 正在从数据库加载任务信息...")
            self._load_jobs_from_store()

    def get_store_type(self) -> str:
        """获取当前存储类型"""
        return self._job_store_type

    def is_persistent(self) -> bool:
        """是否使用持久化存储"""
        return self._job_store_type != "memory"

    def shutdown(self):
        """关闭调度器"""
        if self._running:
            self._scheduler.shutdown()
            self._running = False
            print("[ScheduleService] 调度器已关闭")

    async def add_cron_job(
        self,
        job_id: str,
        cron_expr: str,
        callback: Callable,
        task_name: str,
        content: str = "",
        push_target: str = "default_screen"
    ) -> bool:
        """
        添加 cron 定时任务（支持持久化）

        Args:
            job_id: 唯一任务ID
            cron_expr: cron 表达式
            callback: 回调函数（async）
            task_name: 任务名称
            content: 推送内容模板
            push_target: 推送目标

        Returns:
            是否添加成功
        """
        try:
            print(f"[add_cron_job] 添加任务: {job_id}")
            print(f"  - cron: {cron_expr}")
            print(f"  - name: {task_name}")
            print(f"  - target: {push_target}")

            trigger = CronTrigger.from_crontab(cron_expr, timezone=self._timezone)

            # 确保使用完整的模块路径
            import schedule.server
            callback = schedule.server.on_timer_triggered
            self._scheduler.add_job(
                callback,
                trigger=trigger,
                id=job_id,
                name=task_name,
                replace_existing=True,
                kwargs={
                    'content': content,
                    'push_target': push_target,
                    'job_id': job_id,
                    'task_name': task_name
                }
            )

            # 计算下次执行时间
            base_time = arrow.now()
            cron = croniter(cron_expr, base_time.datetime)
            next_run = cron.get_next(datetime)

            # 保存到内存缓存
            self._jobs[job_id] = ScheduledJob(
                job_id=job_id,
                name=task_name,
                cron_expr=cron_expr,
                content=content,
                push_target=push_target,
                next_run_time=next_run,
                callback=callback
            )
            print(f"[add_cron_job] 任务添加成功: {job_id}")
            print(f"  - 下次执行: {next_run.strftime('%Y-%m-%d %H:%M:%S')}")
            return True

        except Exception as e:
            print(f"[add_cron_job] 添加定时任务失败: {e}")
            import traceback
            traceback.print_exc()
            return False

    def remove_job(self, job_id: str) -> bool:
        """移除定时任务（同时从持久化存储删除）"""
        try:
            self._scheduler.remove_job(job_id)
            if job_id in self._jobs:
                del self._jobs[job_id]
            print(f"[remove_job]任务移除成功: {job_id}")
            return True
        except JobLookupError:
            print(f"[remove_job]任务移除失败: 未找到任务 {job_id}")
            return False
        except Exception as e:
            print(f"[remove_job]任务移除失败: {e}")
            import traceback
            traceback.print_exc()
            return False

    def list_jobs(self) -> list[dict]:
        """列出所有定时任务"""
        jobs = []
        try:
            # 直接从调度器获取最新状态
            aps_jobs = self._scheduler.get_jobs()
            print(f"[list_jobs] 调度器中有 {len(aps_jobs)} 个任务")
            
            for aps_job in aps_jobs:
                job_id = aps_job.id
                job_info = self._jobs.get(job_id)
                
                next_run = aps_job.next_run_time
                name = aps_job.name
                cron_expr = str(aps_job.trigger) if hasattr(aps_job, 'trigger') else "未知"
                content = job_info.content if job_info else ""
                push_target = job_info.push_target if job_info else "default_screen"
                created_at = job_info.created_at if job_info else ""
                
                jobs.append({
                    "job_id": job_id,
                    "name": name,
                    "cron_expr": cron_expr,
                    "content_preview": content[:50] + "..." if len(content) > 50 else content,
                    "push_target": push_target,
                    "next_run": next_run.strftime("%Y-%m-%d %H:%M:%S") if next_run else "未计算",
                    "created_at": created_at
                })
        except Exception as e:
            print(f"[list_jobs] 获取任务列表失败: {e}")
            import traceback
            traceback.print_exc()
            
        return jobs

    def get_job(self, job_id: str) -> Optional[dict]:
        """获取单个任务信息"""
        try:
            aps_job = self._scheduler.get_job(job_id)
            if not aps_job:
                return None
                
            job_info = self._jobs.get(job_id)
            next_run = aps_job.next_run_time

            return {
                "job_id": job_id,
                "name": aps_job.name,
                "cron_expr": str(aps_job.trigger) if hasattr(aps_job, 'trigger') else "未知",
                "content": job_info.content if job_info else "",
                "push_target": job_info.push_target if job_info else "default_screen",
                "next_run": next_run.strftime("%Y-%m-%d %H:%M:%S") if next_run else None,
                "created_at": job_info.created_at if job_info else ""
            }
        except Exception as e:
            print(f"[get_job] 获取任务失败: {e}")
            return None

    def get_job_count(self) -> int:
        """获取任务总数"""
        return len(self._scheduler.get_jobs())

    def clear_all_jobs(self) -> int:
        """清除所有任务（谨慎使用）"""
        count = len(self._scheduler.get_jobs())
        for job in self._scheduler.get_jobs():
            self.remove_job(job.id)
        self._jobs.clear()
        return count

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.shutdown()


# 全局实例
_schedule_service: ScheduleService | None = None


def get_schedule_service() -> ScheduleService:
    """获取或创建 ScheduleService 实例（单例）"""
    global _schedule_service
    if _schedule_service is None:
        _schedule_service = ScheduleService()
        _schedule_service.start()
    return _schedule_service


def reset_schedule_service():
    """重置调度服务（用于测试）"""
    global _schedule_service
    if _schedule_service:
        _schedule_service.shutdown()
        _schedule_service = None