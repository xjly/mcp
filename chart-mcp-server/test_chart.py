"""直接测试 Chart MCP Server（不依赖 Trae）"""
import asyncio
import json
import sys
import os

# 添加 src 到路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

def test_generate_chart():  # 注意：这里是普通函数，不是 async
    """测试生成图表功能"""
    from chart.server import generate_chart  # generate_chart 是同步函数
    
    print("=" * 60)
    print("测试 1: generate_chart - 生成图表")
    print("=" * 60)
    
    # 测试数据
    test_cases = [
        {
            "name": "基本柱状图",
            "data_json": [{"name": "Q1", "value": 120}, {"name": "Q2", "value": 135}],
            "chart_type": "bar",
            "title": "季度销售数据"
        },
        {
            "name": "折线图",
            "data_json": [{"month": "1月", "sales": 100}, {"month": "2月", "sales": 150}],
            "chart_type": "line",
            "title": "月度销售趋势"
        },
        {
            "name": "饼图",
            "data_json": [{"category": "A", "value": 30}, {"category": "B", "value": 70}],
            "chart_type": "pie",
            "title": "市场份额"
        },
        {
            "name": "字符串格式数据",
            "data_json": '[{"name": "测试1", "value": 10}, {"name": "测试2", "value": 20}]',
            "chart_type": "bar",
            "title": "字符串解析测试"
        }
    ]
    
    for test in test_cases:
        print(f"\n📊 {test['name']}:")
        print(f"   参数: {json.dumps({k: v for k, v in test.items() if k != 'name'}, ensure_ascii=False)}")
        
        try:
            # 注意：这里没有 await！因为 generate_chart 是同步函数
            result = generate_chart(
                data_json=test['data_json'],
                chart_type=test.get('chart_type'),
                title=test.get('title')
            )
            data = json.loads(result)
            
            if data.get('ok'):
                print(f"   ✅ 成功!")
                print(f"   图表类型: {data.get('chart_type')}")
                print(f"   数据点数: {data.get('data_points')}")
                print(f"   说明: {data.get('explanation')}")
            else:
                print(f"   ❌ 失败: {data.get('error')}")
                
        except Exception as e:
            print(f"   ❌ 异常: {e}")

def test_explain_chart():
    """测试解释图表功能"""
    import asyncio
    from chart.server import explain_chart  # explain_chart 是异步函数
    
    print("\n" + "=" * 60)
    print("测试 2: explain_chart - 解释图表")
    print("=" * 60)
    
    async def run_tests():
        test_cases = [
            {
                "name": "正常URL",
                "chart_url": "http://114.66.47.144:9000/kb-images/chat-images/c555a97f10c6430595786f52b27b1402.png",
                "text": "水位监测数据"
            },
            {
                "name": "缺少URL",
                "chart_url": None,
                "text": "测试"
            }
        ]
        
        for test in test_cases:
            print(f"\n🖼️ {test['name']}:")
            print(f"   URL: {test['chart_url']}")
            
            try:
                result = await explain_chart(
                    chart_url=test['chart_url'],
                    text=test.get('text')
                )
                data = json.loads(result)
                
                if data.get('ok'):
                    print(f"   ✅ 成功!")
                    print(f"   识别文字: {data.get('ocr_text', '')[:50]}...")
                    print(f"   解释: {data.get('explanation', '')[:50]}...")
                else:
                    print(f"   ❌ 失败: {data.get('error')}")
                    
            except Exception as e:
                print(f"   ❌ 异常: {e}")
    
    asyncio.run(run_tests())

def test_edge_cases():
    """测试边界情况"""
    from chart.server import generate_chart
    
    print("\n" + "=" * 60)
    print("测试 3: 边界情况测试")
    print("=" * 60)
    
    edge_cases = [
        {
            "name": "空数据",
            "data_json": [],
            "chart_type": "bar"
        },
        {
            "name": "缺少 data_json",
            "data_json": None,
            "chart_type": "bar"
        },
        {
            "name": "无效 JSON 字符串",
            "data_json": "invalid json",
            "chart_type": "bar"
        },
        {
            "name": "单个数据点",
            "data_json": [{"name": "唯一项", "value": 100}],
            "chart_type": "pie"
        },
        {
            "name": "大量数据",
            "data_json": [{"name": f"项{i}", "value": i*10} for i in range(100)],
            "chart_type": "line"
        }
    ]
    
    for test in edge_cases:
        print(f"\n🔍 {test['name']}:")
        
        try:
            result = generate_chart(
                data_json=test['data_json'],
                chart_type=test.get('chart_type')
            )
            data = json.loads(result)
            
            if data.get('ok'):
                print(f"   ✅ 处理成功 (数据点: {data.get('data_points')})")
            else:
                print(f"   ⚠️ 返回错误: {data.get('error')}")
                
        except Exception as e:
            print(f"   ❌ 异常: {e}")

def test_performance():
    """性能测试"""
    from chart.server import generate_chart
    
    print("\n" + "=" * 60)
    print("测试 4: 性能测试")
    print("=" * 60)
    
    import time
    
    # 中等规模数据
    data = [{"name": f"项目{i}", "value": i * 100} for i in range(1000)]
    
    print(f"\n⏱️ 测试 1000 个数据点的处理时间...")
    
    start = time.time()
    result = generate_chart(
        data_json=data,
        chart_type="bar",
        title="性能测试"
    )
    elapsed = time.time() - start
    
    data = json.loads(result)
    if data.get('ok'):
        print(f"   ✅ 完成! 耗时: {elapsed*1000:.2f} ms")
        print(f"   数据点数: {data.get('data_points')}")
    else:
        print(f"   ❌ 失败: {data.get('error')}")

def main():
    """运行所有测试"""
    print("\n" + "🚀" * 30)
    print("Chart MCP Server 测试套件")
    print("🚀" * 30)
    
    try:
        # 运行测试（注意：generate_chart 是同步的，不需要 asyncio）
        test_generate_chart()
        test_explain_chart()  # explain_chart 是异步的，内部已处理
        test_edge_cases()
        test_performance()
        
        print("\n" + "✅" * 30)
        print("所有测试完成!")
        print("✅" * 30)
        
    except ImportError as e:
        print(f"\n❌ 导入失败: {e}")
        print("请确保在正确的目录运行，并且已安装依赖: uv sync")
    except Exception as e:
        print(f"\n❌ 测试失败: {e}")

if __name__ == "__main__":
    main()