"""合并的大屏推送 + 调度服务"""
import asyncio
import sys
import os
import threading

sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from schedule.scheduler import ScheduleService

def run_http_server():
    """在独立线程中运行大屏 HTTP 服务"""
    import mock_screen_test
    mock_screen_test.run_server(8080)

async def main():
    # 启动大屏 HTTP 服务（独立线程）
    http_thread = threading.Thread(target=run_http_server, daemon=True)
    http_thread.start()
    await asyncio.sleep(1)
    print("[组合服务] 大屏 HTTP 服务已启动 (端口8080)")
    
    # 启动调度器
    svc = ScheduleService()
    svc.start()
    print(f"[组合服务] 调度器已启动")
    print(f"[组合服务] 数据库: {svc.get_db_path()}")
    print(f"[组合服务] 任务数: {svc.get_job_count()}")
    print("=" * 60)
    print("[组合服务] 等待定时任务触发...")
    print()
    
    # 持续运行
    while True:
        await asyncio.sleep(30)
        svc._load_jobs_from_store()
        jobs = svc._scheduler.get_jobs()
        if jobs:
            for j in jobs:
                print(f"[心跳] {j.name}: next_run={j.next_run_time}")
        else:
            print("[心跳] 当前无任务")

if __name__ == '__main__':
    asyncio.run(main())