import sqlite3
from datetime import datetime

db_path = r'e:\mcp-master\mcp-master\schedule-mcp-server\test\push_records.db'
print("=" * 60)
print("查看推送记录")
print("=" * 60)

conn = sqlite3.connect(db_path)
cursor = conn.cursor()

# 检查推送记录
print("\n1. 检查推送记录...")
cursor.execute('SELECT COUNT(*) FROM push_records')
count = cursor.fetchone()[0]
print(f"   总推送记录数: {count}")

# 查看所有推送记录
if count > 0:
    print("\n2. 推送记录详情...")
    cursor.execute('SELECT id, screen_id, title, content, received_at FROM push_records ORDER BY id DESC')
    records = cursor.fetchall()

    for i, (record_id, screen_id, title, content, received_at) in enumerate(records):
        print(f"\n   记录 {i+1}:")
        print(f"     ID: {record_id}")
        print(f"     目标大屏: {screen_id}")
        print(f"     标题: {title}")
        print(f"     内容: {content[:100]}..." if len(content) > 100 else f"     内容: {content}")
        print(f"     接收时间: {received_at}")

# 查看最新推送
print("\n3. 最新推送...")
cursor.execute('SELECT id, screen_id, title, received_at FROM push_records ORDER BY id DESC LIMIT 1')
latest = cursor.fetchone()
if latest:
    print(f"   最新推送 ID: {latest[0]}")
    print(f"   目标大屏: {latest[1]}")
    print(f"   标题: {latest[2]}")
    print(f"   时间: {latest[3]}")

conn.close()
print("\n" + "=" * 60)
print("推送记录检查完成！")
print("=" * 60)
