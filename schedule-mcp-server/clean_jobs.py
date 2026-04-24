"""清空任务数据库"""
import sqlite3
import os

db_path = os.path.join(os.path.dirname(__file__), "jobs.sqlite")

if os.path.exists(db_path):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # 查看当前任务
    cursor.execute("SELECT COUNT(*) FROM apscheduler_jobs")
    count = cursor.fetchone()[0]
    print(f"当前任务数: {count}")
    
    if count > 0:
        confirm = input("确认清空所有任务？(y/N): ")
        if confirm.lower() == 'y':
            cursor.execute("DELETE FROM apscheduler_jobs")
            conn.commit()
            print(f"✅ 已清空 {count} 个任务")
        else:
            print("取消操作")
    else:
        print("数据库已为空")
    
    conn.close()
else:
    print(f"数据库文件不存在: {db_path}")