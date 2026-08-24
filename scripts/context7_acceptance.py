"""B2 Context7 适配层验收脚本。

验收标准（工单）：
1. context7_query_docs("fastapi", "streaming response", 3) 返回真实文档片段
2. 无网络/超时返回空 docs 且不报错（用不可达 CONTEXT7_API_BASE 模拟）
3. 工具注册进 mcp_server + 能力卡片含 license 字段

用法:
    python scripts/context7_acceptance.py
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from mcpserver import mcp_registry  # noqa: E402
from mcpserver.adapters import context7  # noqa: E402


class FakeServer:
    """捕获 add_tool 注册的假 mcp_server。"""

    def __init__(self):
        self.captured: dict[str, object] = {}

    def add_tool(self, fn, name=None):
        self.captured[name or getattr(fn, "__name__", "?")] = fn


def check_1_registration() -> bool:
    server = FakeServer()
    mcp_registry.clear_registry()
    context7.register(server, mcp_registry=mcp_registry)
    assert "context7_query_docs" in server.captured, "工具未注册进 mcp_server"
    caps = [c for c in mcp_registry.list_registered_capabilities() if c["name"] == "context7"]
    assert caps, "能力卡片未登记"
    assert caps[0].get("license"), "能力卡片缺 license 字段"
    print("[PASS] 1/3 注册：context7_query_docs 已挂载，能力卡含 license =", caps[0]["license"])
    return True


def check_2_live_docs() -> bool:
    result = asyncio.run(context7.context7_query_docs("fastapi", "streaming response", 3))
    assert result.get("ok") is True, f"实网调用应成功，实际: {result}"
    docs = result.get("docs") or []
    assert len(docs) == 3, f"应返回 3 段文档，实际 {len(docs)}"
    assert any("StreamingResponse" in d or "stream" in d.lower() for d in docs), "片段应与 streaming 主题相关"
    print(f"[PASS] 2/3 实网：lib={result['lib']} → {result['library_id']}，"
          f"{len(docs)} 段片段，首段 {len(docs[0])} 字符")
    print("      首段预览:", docs[0].splitlines()[0][:80])
    return True


def check_3_degrade() -> bool:
    os.environ["CONTEXT7_API_BASE"] = "https://127.0.0.1:9/api/v1"  # 不可达地址模拟无网络
    try:
        result = asyncio.run(context7.context7_query_docs("fastapi", "streaming response", 3))
    finally:
        os.environ.pop("CONTEXT7_API_BASE", None)
    assert result.get("ok") is False, "不可达端点应返回 ok=False"
    assert result.get("docs") == [], "降级时 docs 必须为空列表"
    assert "error" in result, "降级结果应附 error 原因"
    print(f"[PASS] 3/3 降级：无网络 → ok=False, docs=[], error={result['error'][:60]}")
    return True


def main() -> int:
    checks = [
        ("注册+license", check_1_registration),
        ("实网文档片段", check_2_live_docs),
        ("无网络降级", check_3_degrade),
    ]
    failed = 0
    for title, fn in checks:
        try:
            fn()
        except AssertionError as e:
            failed += 1
            print(f"[FAIL] {title}: {e}")
        except Exception as e:  # 验收脚本自身异常也计失败
            failed += 1
            print(f"[FAIL] {title}: 未预期异常 {type(e).__name__}: {e}")
    print(json.dumps({"passed": len(checks) - failed, "failed": failed}, ensure_ascii=False))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
