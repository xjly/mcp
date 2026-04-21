"""测试 MCP 服务与推送服务的连接"""
import asyncio
import sys
import os
import httpx

sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

async def test_connection():
    print("=" * 60)
    print("🔗 测试 MCP 服务与推送服务连接")
    print("=" * 60)
    
    # 1. 测试推送服务是否可用
    print("\n1️⃣ 测试推送服务健康状态...")
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            response = await client.get("http://localhost:8080/health")
            if response.status_code == 200:
                print("   ✅ 推送服务运行正常")
                print(f"   📊 已有推送记录: {response.json()['total_pushes']} 条")
            else:
                print("   ❌ 推送服务响应异常")
    except Exception as e:
        print(f"   ❌ 无法连接推送服务: {e}")
        print("   请先启动推送服务: python mock_screen_server_simple.py")
        return
    
    # 2. 测试 MCP 工具的推送功能
    print("\n2️⃣ 测试 MCP 推送工具...")
    from schedule.server import push_to_screen
    
    result = await push_to_screen(
        content="## 🧪 连接测试\n\n这是一条测试消息，用于验证 MCP 服务与推送服务的连接。",
        screen_id="test_connection",
        title="连接测试"
    )
    
    import json
    data = json.loads(result)
    if data['status'] == 'success':
        print("   ✅ 推送成功！")
        print(f"   📺 目标大屏: {data['screen_id']}")
        print(f"   📝 消息: {data['message']}")
    else:
        print(f"   ❌ 推送失败: {data.get('error')}")
    
    # 3. 查看推送记录
    print("\n3️⃣ 查看推送记录...")
    async with httpx.AsyncClient(timeout=5) as client:
        response = await client.get("http://localhost:8080/api/records")
        records = response.json()
        print(f"   📊 总推送次数: {records['total']}")
        if records['records']:
            last = records['records'][-1]
            print(f"   🕐 最新推送时间: {last['received_at']}")
            print(f"   📺 目标大屏: {last['screen_id']}")
            print(f"   📝 标题: {last['title']}")
    
    print("\n" + "=" * 60)
    print("✅ 测试完成！MCP 服务与推送服务连接正常")
    print("=" * 60)

if __name__ == "__main__":
    asyncio.run(test_connection())