import sqlite3
from datetime import datetime

db_path = r'E:\mcp-master\mcp-master\schedule-mcp-server\jobs.sqlite'
print("=" * 60)
print("检查数据库内容")
print("=" * 60)

conn = sqlite3.connect(db_path)
cursor = conn.cursor()

# 检查数据库表结构
print("\n1. 数据库表结构...")
cursor.execute('PRAGMA table_info(apscheduler_jobs)')
columns = cursor.fetchall()
print("   表字段:")
for column in columns:
    print(f"     - {column[1]} ({column[2]})")

# 统计任务数量
print("\n2. 任务统计...")
cursor.execute('SELECT COUNT(*) FROM apscheduler_jobs')
count = cursor.fetchone()[0]
print(f"   总任务数: {count}")

# 查看任务详情
if count > 0:
    print("\n3. 任务详情...")
    cursor.execute('SELECT id, next_run_time FROM apscheduler_jobs')
    jobs = cursor.fetchall()
    
    for i, (job_id, next_run) in enumerate(jobs):
        print(f"\n   任务 {i+1}:")
        print(f"     ID: {job_id}")
        if next_run:
            # 转换时间戳为可读格式
            next_run_date = datetime.fromtimestamp(next_run)
            print(f"     下次执行: {next_run_date.strftime('%Y-%m-%d %H:%M:%S')}")
        else:
            print(f"     下次执行: 无")

conn.close()
print("\n" + "=" * 60)
print("数据库检查完成！")
print("=" * 60)
