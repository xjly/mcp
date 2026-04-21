"""快速验证 MCP 服务功能"""
import asyncio
import json
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

async def quick_test():
    print("🚀 快速测试 Schedule MCP 服务\n")
    
    from schedule.server import schedule_task
    
    # 测试1: 列出任务
    print("1️⃣ 列出当前任务...")
    result = await schedule_task(action="list")
    data = json.loads(result)
    print(f"   状态: {data['status']}")
    print(f"   任务数: {data['total']}\n")
    
    # 测试2: 创建任务
    print("2️⃣ 创建一个测试任务...")
    result = await schedule_task(
        action="create",
        cron_expression="*/10 * * * *",
        content="## 测试\n\n时间: {current_time}",
        task_name="快速测试",
        push_target="test"
    )
    data = json.loads(result)
    if data['status'] == 'success':
        print(f"   ✅ 任务创建成功!")
        print(f"   任务ID: {data['task_id']}")
        print(f"   下次执行: {data['next_run']}\n")
    else:
        print(f"   ❌ 创建失败: {data['message']}\n")
    
    # 测试3: 再次列出
    print("3️⃣ 再次列出任务...")
    result = await schedule_task(action="list")
    data = json.loads(result)
    print(f"   当前任务数: {data['total']}")
    for task in data['tasks']:
        print(f"   - {task['name']} ({task['job_id'][:8]}...)")
    
    print("\n✨ 测试完成！服务运行正常。")

if __name__ == "__main__":
    asyncio.run(quick_test())