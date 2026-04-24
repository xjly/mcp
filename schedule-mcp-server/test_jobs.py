import asyncio, sys
sys.path.insert(0, 'src')

async def main():
    from schedule.scheduler import get_schedule_service
    svc = get_schedule_service()
    
    jobs = svc.list_jobs()
    print(f'任务数: {len(jobs)}')
    for j in jobs:
        print(f'  {j["name"]}: {j["cron_expr"]} -> {j["next_run"]}')
    
    aps_jobs = svc._scheduler.get_jobs()
    print(f'\nAPScheduler任务数: {len(aps_jobs)}')
    for j in aps_jobs:
        print(f'  {j.id}: next_run={j.next_run_time}')

asyncio.run(main())