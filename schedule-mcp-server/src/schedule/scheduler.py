"""Schedule Service - 调度器服务层（支持任务持久化）"""

import os
import uuid
import asyncio
from datetime import datetime
from typing import Callable, Optional, Dict, Any
from dataclasses import dataclass, field

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.jobstores.base import JobLookupError
from apscheduler.jobstores.memory import MemoryJobStore
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from croniter import croniter
import arrow
from dotenv import load_dotenv

# 加载 .env 配置
load_dotenv()


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
        self._timezone = os.getenv("SCHEDULER_TIMEZONE", "Asia/Shanghai")
        self._job_store_type = os.getenv("JOB_STORE_TYPE", "memory")
        
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
        
        # 启动时从数据库加载任务信息到内存缓存
        self._load_jobs_from_store()

    def _create_jobstores(self) -> dict:
        """根据配置创建任务存储"""
        if self._job_store_type == "sqlite":
            db_path = os.getenv("SQLITE_DB_PATH", "./jobs.sqlite")
            # 确保目录存在
            os.makedirs(os.path.dirname(os.path.abspath(db_path)) if os.path.dirname(db_path) else '.', exist_ok=True)
            
            return {
                'default': SQLAlchemyJobStore(
                    url=f'sqlite:///{db_path}',
                    tablename='apscheduler_jobs'
                )
            }
        elif self._job_store_type == "postgresql":
            postgresql_url = os.getenv("POSTGRESQL_URL")
            if not postgresql_url:
                raise ValueError("使用 postgresql 存储需要配置 POSTGRESQL_URL")
            return {
                'default': SQLAlchemyJobStore(url=postgresql_url)
            }
        else:
            # 默认使用内存存储
            return {
                'default': MemoryJobStore()
            }

    def _load_jobs_from_store(self):
        """从持久化存储加载任务信息到内存缓存"""
        try:
            # 获取调度器中所有已存储的任务
            jobs = self._scheduler.get_jobs()
            for job in jobs:
                # 从 job 的 kwargs 中恢复自定义字段
                job_info = ScheduledJob(
                    job_id=job.id,
                    name=job.name,
                    cron_expr=str(job.trigger),
                    content=job.kwargs.get('content', ''),
                    push_target=job.kwargs.get('push_target', 'default_screen'),
                    callback=None  # 回调函数无法序列化，需要重新绑定
                )
                self._jobs[job.id] = job_info
                
            if self._job_store_type != "memory":
                print(f" 从持久化存储加载了 {len(self._jobs)} 个定时任务")
        except Exception as e:
            print(f" 加载持久化任务失败: {e}")

    def start(self):
        """启动调度器"""
        if not self._running:
            self._scheduler.start()
            self._running = True
            print(f" 调度器已启动 (存储类型: {self._job_store_type})")

    def shutdown(self):
        """关闭调度器"""
        if self._running:
            self._scheduler.shutdown()
            self._running = False
            print(" 调度器已关闭")

    async def add_cron_job(
        self,
        job_id: str,
        cron_expr: str,
        callback: Callable,
        task_name: str = "定时任务",
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
            trigger = CronTrigger.from_crontab(cron_expr, timezone=self._timezone)

            # 将任务添加到调度器（会同时保存到持久化存储）
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

            return True

        except Exception as e:
            print(f"添加定时任务失败: {e}")
            return False

    def remove_job(self, job_id: str) -> bool:
        """移除定时任务（同时从持久化存储删除）"""
        try:
            self._scheduler.remove_job(job_id)
            if job_id in self._jobs:
                del self._jobs[job_id]
            return True
        except JobLookupError:
            return False
        except Exception as e:
            print(f"移除任务失败: {e}")
            return False

    def list_jobs(self) -> list[dict]:
        """列出所有定时任务"""
        jobs = []
        for job_id, job_info in self._jobs.items():
            aps_job = self._scheduler.get_job(job_id)
            next_run = aps_job.next_run_time if aps_job else job_info.next_run_time

            jobs.append({
                "job_id": job_id,
                "name": job_info.name,
                "cron_expr": job_info.cron_expr,
                "content_preview": job_info.content[:50] + "..." if len(job_info.content) > 50 else job_info.content,
                "push_target": job_info.push_target,
                "next_run_time": next_run.strftime("%Y-%m-%d %H:%M:%S") if next_run else None,
                "created_at": job_info.created_at
            })
        return jobs

    def get_job(self, job_id: str) -> Optional[dict]:
        """获取单个任务信息"""
        if job_id in self._jobs:
            job_info = self._jobs[job_id]
            aps_job = self._scheduler.get_job(job_id)
            next_run = aps_job.next_run_time if aps_job else job_info.next_run_time

            return {
                "job_id": job_id,
                "name": job_info.name,
                "cron_expr": job_info.cron_expr,
                "content": job_info.content,
                "push_target": job_info.push_target,
                "next_run_time": next_run.strftime("%Y-%m-%d %H:%M:%S") if next_run else None,
                "created_at": job_info.created_at
            }
        return None

    def get_job_count(self) -> int:
        """获取任务总数"""
        return len(self._jobs)

    def clear_all_jobs(self) -> int:
        """清除所有任务（谨慎使用）"""
        count = len(self._jobs)
        for job_id in list(self._jobs.keys()):
            self.remove_job(job_id)
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