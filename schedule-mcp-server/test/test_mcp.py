import sys
import os
import asyncio
import json

sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from schedule.server import schedule_task, push_to_screen

async def test_mcp_service():
    print("=" * 60)
    print("测试 Schedule MCP 服务功能")
    print("=" * 60)
    
    # 1. 测试列出任务
    print("\n1. 测试列出任务...")
    result = await schedule_task(action="list")
    data = json.loads(result)
    print(f"   状态: {data['status']}")
    print(f"   任务数: {data['total']}")
    print(f"   存储类型: {data['store_type']}")
    print(f"   持久化: {data['persistent']}")
    
    if data['tasks']:
        print("   任务列表:")
        for task in data['tasks']:
            print(f"     - {task['job_id']}: {task['name']}")
    
    # 2. 测试创建任务
    print("\n2. 测试创建任务...")
    create_result = await schedule_task(
        action="create",
        cron_expression="*/10 * * * *",
        content="## 测试任务\n\n时间: {current_time}",
        task_name="MCP 测试任务",
        push_target="test"
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
    
    # 3. 再次列出任务
    print("\n3. 再次列出任务...")
    result = await schedule_task(action="list")
    data = json.loads(result)
    print(f"   当前任务数: {data['total']}")
    
    # 4. 测试即时推送
    print("\n4. 测试即时推送...")
    push_result = await push_to_screen(
        content="## 即时推送测试\n\n这是一个测试消息",
        screen_id="test",
        title="测试推送"
    )
    push_data = json.loads(push_result)
    print(f"   推送状态: {push_data.get('status', 'unknown')}")
    
    # 5. 测试取消任务
    if test_task_id:
        print(f"\n5. 测试取消任务...")
        cancel_result = await schedule_task(
            action="cancel",
            task_id=test_task_id
        )
        cancel_data = json.loads(cancel_result)
        print(f"   状态: {cancel_data['status']}")
        print(f"   消息: {cancel_data['message']}")
    
    # 6. 最终状态
    print("\n6. 最终状态...")
    result = await schedule_task(action="list")
    data = json.loads(result)
    print(f"   最终任务数: {data['total']}")
    
    print("\n" + "=" * 60)
    print("MCP 服务测试完成！")
    print("=" * 60)

if __name__ == "__main__":
    asyncio.run(test_mcp_service())
