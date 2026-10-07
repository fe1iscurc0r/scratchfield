"""
测试 API 路由映射
"""
import os

import httpx

BASE_URL = "http://127.0.0.1:8000"

# 1. 获取 OpenAPI schema
r = httpx.get(f"{BASE_URL}/openapi.json", timeout=5)
schema = r.json()
paths = schema.get("paths", {})

print("=== 所有 API 路径 ===")
for path in sorted(paths.keys()):
    methods = list(paths[path].keys())
    print(f"  {path}")
    # 只显示前几个方法
    for method in methods[:2]:
        print(f"    {method.upper()}")

# 2. 直接测试系统信息接口
print("\n=== 测试系统信息 ===")
# 尝试不同的路径
for path in ["/system/info", "/api/system/info", "/system/config", "/api/system/config"]:
    r = httpx.get(f"{BASE_URL}{path}", timeout=5)
    print(f"{path}: {r.status_code} - {r.text[:100]}")

# 3. 带 token 测试（token 从环境变量读取，不入库）
print("\n=== 带 Token 测试 ===")
token = os.environ.get("SCRATCHPAD_TOKEN", "")
if not token:
    print("未设置 SCRATCHPAD_TOKEN 环境变量，跳过带 token 测试")
headers = {"Authorization": f"Bearer {token}"} if token else {}

# 测试 persona 列表
for path in ["/api/persona/list", "/persona/list", "/api/persona/list/"]:
    r = httpx.get(f"{BASE_URL}{path}", headers=headers, timeout=5)
    print(f"{path}: {r.status_code}")
    if r.status_code != 404:
        print(f"  Body: {r.text[:200]}")
