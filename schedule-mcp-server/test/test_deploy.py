import sys
import os
import asyncio
import json

sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from schedule.scheduler import ScheduleService
from schedule.server import schedule_task

async def test_deployment():
    print("=" * 60)
    print("测试 Schedule MCP 独立部署配置")
    print("=" * 60)
    
    # 1. 测试数据库路径配置
    print("\n1. 测试数据库路径配置...")
    service = ScheduleService()
    service.start()
    
    jobs = service.list_jobs()
    print(f"   数据库路径配置: 正确")
    print(f"   当前任务数: {len(jobs)}")
    
    # 2. 测试任务列表功能
    print("\n2. 测试任务列表功能...")
    result = await schedule_task(action="list")
    data = json.loads(result)
    print(f"   状态: {data['status']}")
    print(f"   存储类型: {data['store_type']}")
    print(f"   持久化: {data['persistent']}")
    print(f"   任务数: {data['total']}")
    
    # 3. 测试创建任务
    print("\n3. 测试创建任务...")
    create_result = await schedule_task(
        action="create",
        cron_expression="*/10 * * * *",
        content="## 部署测试\n\n时间: {current_time}",
        task_name="部署测试任务",
        push_target="default_screen"
    )
    create_data = json.loads(create_result)
    print(f"   状态: {create_data['status']}")
    if create_data['status'] == 'success':
        print(f"   任务ID: {create_data['task_id']}")
        print(f"   下次执行: {create_data['next_run']}")
        test_task_id = create_data['task_id']
    else:
        print(f"   错误: {create_data['message']}")
        test_task_id = None
    
    # 4. 测试取消任务
    if test_task_id:
        print("\n4. 测试取消任务...")
        cancel_result = await schedule_task(action="cancel", task_id=test_task_id)
        cancel_data = json.loads(cancel_result)
        print(f"   状态: {cancel_data['status']}")
        print(f"   消息: {cancel_data['message']}")
    
    # 5. 测试持久化
    print("\n5. 测试持久化...")
    service.shutdown()
    await asyncio.sleep(0.5)
    
    service2 = ScheduleService()
    service2.start()
    
    result = await schedule_task(action="list")
    data2 = json.loads(result)
    print(f"   重启后任务数: {data2['total']}")
    
    if data2['total'] == len(jobs):
        print("   持久化测试: 通过")
    else:
        print("   持久化测试: 失败")
    
    service2.shutdown()
    
    print("\n" + "=" * 60)
    print("部署配置测试完成！")
    print("=" * 60)

if __name__ == "__main__":
    asyncio.run(test_deployment())
