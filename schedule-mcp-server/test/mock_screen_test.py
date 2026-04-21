"""模拟大屏推送服务 - SQLite 持久化"""
from http.server import HTTPServer, BaseHTTPRequestHandler
import json
from datetime import datetime
import urllib.parse
import signal
import sys
import sqlite3
import os

DB_FILE = "push_records.db"

def init_database():
    """初始化数据库"""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS push_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            screen_id TEXT NOT NULL,
            content TEXT,
            title TEXT,
            timestamp TEXT,
            received_at TEXT
        )
    ''')
    conn.commit()
    conn.close()

def save_record(record):
    """保存记录到数据库"""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO push_records (screen_id, content, title, timestamp, received_at)
        VALUES (?, ?, ?, ?, ?)
    ''', (record['screen_id'], record['content'], record['title'], 
          record['timestamp'], record['received_at']))
    conn.commit()
    record_id = cursor.lastrowid
    conn.close()
    return record_id

def get_records(limit=100, screen_id=None):
    """获取记录"""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    if screen_id:
        cursor.execute('''
            SELECT id, screen_id, content, title, timestamp, received_at
            FROM push_records
            WHERE screen_id = ?
            ORDER BY id DESC
            LIMIT ?
        ''', (screen_id, limit))
    else:
        cursor.execute('''
            SELECT id, screen_id, content, title, timestamp, received_at
            FROM push_records
            ORDER BY id DESC
            LIMIT ?
        ''', (limit,))
    
    records = []
    for row in cursor.fetchall():
        records.append({
            "id": row[0],
            "screen_id": row[1],
            "content": row[2],
            "title": row[3],
            "timestamp": row[4],
            "received_at": row[5]
        })
    
    # 获取总数
    cursor.execute('SELECT COUNT(*) FROM push_records')
    total = cursor.fetchone()[0]
    
    conn.close()
    return total, records

def clear_records():
    """清空所有记录"""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('DELETE FROM push_records')
    count = cursor.rowcount
    conn.commit()
    conn.close()
    return count

# 初始化数据库
init_database()

class PushHandler(BaseHTTPRequestHandler):
    
    def do_POST(self):
        if self.path.startswith('/api/push/'):
            screen_id = self.path.replace('/api/push/', '')
            
            content_length = int(self.headers.get('Content-Length', 0))
            if content_length == 0:
                self.send_response(400)
                self.end_headers()
                return
                
            post_data = self.rfile.read(content_length)
            
            try:
                data = json.loads(post_data.decode('utf-8'))
                
                record = {
                    "screen_id": screen_id,
                    "content": data.get('content', ''),
                    "title": data.get('title', ''),
                    "timestamp": datetime.now().isoformat(),
                    "received_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                }
                
                record_id = save_record(record)
                
                print(f"\n📺 收到推送请求")
                print(f"   目标大屏: {screen_id}")
                print(f"   标题: {record['title']}")
                print(f"   内容预览: {record['content'][:100]}...")
                print(f"   时间: {record['received_at']}")
                print(f"   记录ID: {record_id}")
                
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                
                response = {
                    "status": "success",
                    "message": f"内容已推送到大屏 {screen_id}",
                    "record_id": record_id
                }
                self.wfile.write(json.dumps(response).encode())
                
            except Exception as e:
                print(f"❌ 处理推送失败: {e}")
                self.send_response(500)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                response = {"status": "error", "message": str(e)}
                self.wfile.write(json.dumps(response).encode())
        else:
            self.send_response(404)
            self.end_headers()
    
    def do_GET(self):
        parsed_path = urllib.parse.urlparse(self.path)
        
        if parsed_path.path == '/api/records':
            query = urllib.parse.parse_qs(parsed_path.query)
            limit = int(query.get('limit', [100])[0])
            screen_id = query.get('screen_id', [None])[0]
            
            total, records = get_records(limit, screen_id)
            
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            
            response = {
                "total": total,
                "records": records
            }
            self.wfile.write(json.dumps(response, indent=2, ensure_ascii=False).encode())
            
        elif parsed_path.path == '/api/clear':
            count = clear_records()
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            response = {"status": "success", "message": f"已清空 {count} 条记录"}
            self.wfile.write(json.dumps(response).encode())
            
        elif parsed_path.path == '/health':
            total, _ = get_records(1)
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            
            response = {
                "status": "ok",
                "timestamp": datetime.now().isoformat(),
                "total_pushes": total,
                "database": DB_FILE
            }
            self.wfile.write(json.dumps(response).encode())
        else:
            self.send_response(404)
            self.end_headers()
    
    def log_message(self, format, *args):
        pass

def run_server(port=8080):
    server_address = ('', port)
    httpd = HTTPServer(server_address, PushHandler)
    
    def signal_handler(signum, frame):
        print("\n\n👋 服务已停止")
        httpd.shutdown()
        sys.exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)
    
    total, _ = get_records(1)
    print("=" * 60)
    print("📺 模拟大屏推送服务启动 (SQLite持久化)")
    print("=" * 60)
    print(f"推送接口: http://localhost:{port}/api/push/{{screen_id}}")
    print(f"查看记录: http://localhost:{port}/api/records")
    print(f"清空记录: http://localhost:{port}/api/clear")
    print(f"健康检查: http://localhost:{port}/health")
    print("=" * 60)
    print(f"\n💾 数据库文件: {DB_FILE}")
    print(f"📊 历史记录: {total} 条")
    print("\n💡 提示: 重启服务后记录不会丢失！\n")
    print("等待接收推送...\n")
    
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n\n👋 服务已停止")
        httpd.shutdown()

if __name__ == '__main__':
    run_server(8080)