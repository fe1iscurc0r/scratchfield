"""
快速测试 API 服务器是否能正常导入和启动
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

print("正在导入 API 服务器...")
try:
    from apiserver.api_server import app
    print("✅ 导入成功！")
    print(f"路由数量: {len(app.routes)}")
    
    # 列出所有路由
    for route in app.routes:
        if hasattr(route, 'methods'):
            print(f"  {route.methods} {route.path}")
except Exception as e:
    print(f"❌ 导入失败: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

print("\n测试完成！")
