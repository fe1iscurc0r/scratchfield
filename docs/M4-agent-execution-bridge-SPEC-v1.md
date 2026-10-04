# M4 Agent 执行桥接 SPEC · v1

> 制定：实验田维护者（Hermes）｜施工：待定（Trae/WorkBuddy）
> 日期：2026-08-16
> 前置：NEKO-Lumo-Fusion-Blueprint-v1.1.md M4 章节
> 规范：SPEC-Writing-Standard-v2.md（四问 + 不变量验收）

---

## 〇、一句话定位

让陆墨（脑）的 agent 决策能驱动 NEKO（手）执行 CUA/浏览器操作——scratchpad 侧新增 `neko_cua` 工具，HTTP 桥接 NEKO 已就位的 `/computer_use/run` / `/browser_use/run` 执行端点。

## 一、四问

| 问 | 答 |
|---|---|
| 边界 | **做**：scratchpad 侧 `neko_cua` 工具（HTTP 客户端 + 鉴权 + 分支接入）。**不做**：NEKO 侧沙箱（已收紧✅）、NEKO task_executor 实现（已就位✅）、Agent 指令源策略 |
| 层次 | 在「陆墨 agent 工具层」操作，复用现有 `agentic_tool_loop` 内置工具分支模式（openclaw 同款） |
| 关系 | `陆墨 agent 决策 → neko_cua 工具 --HTTP(Bearer NEKO_EXEC_TOKEN)--> NEKO /computer_use/run`。换 NEKO 地址只改环境变量，工具逻辑不变 |
| 目的 | `python -m pytest tests/test_neko_cua.py` 全过 + grep 验收非空 |

## 二、现状（已就位，无需改）

| 组件 | 位置 | 状态 |
|---|---|---|
| CUA 沙箱收紧 | `NEKO/N.E.K.O/brain/computer_use.py` | ✅ allowlist + AST 预检 + 审计 + 30s 超时 |
| 执行端点 | `NEKO/N.E.K.O/app/agent_server/api_routes.py:1277` `/computer_use/run`、`:1304` `/browser_use/run` | ✅ 已就位 |
| exec 鉴权 | `api_routes.py:196` `require_exec_token`（`NEKO_EXEC_TOKEN` env + `hmac.compare_digest` + fail-safe 503） | ✅ 已就位 |
| Agent Server | 蓝图 D：端口 48915 | ✅ |

## 三、架构

```
陆墨 agent 决策（agentic_tool_loop）
  └─ neko_cua 工具（新）
       ├─ action="computer_use" → POST /computer_use/run
       ├─ action="browser_use"  → POST /browser_use/run
       └─ 鉴权：Authorization: Bearer $NEKO_EXEC_TOKEN
             │
             ▼
NEKO Agent Server (127.0.0.1:48915) → task_executor → CUA 沙箱执行
```

**铁律**：指令源 = 陆墨。NEKO brain 不自决策，只执行陆墨 agent 决策下发的任务。

## 四、施工步骤

### 步骤 1：新建 `apiserver/neko_cua.py`

代码骨架（可直接运行，参考 `agentic_tool_loop.py:245` openclaw 客户端模式）：

```python
"""M4 桥接：陆墨 agent 决策 → NEKO CUA/浏览器执行。

只做 HTTP 客户端 + 鉴权 + 结果回传。NEKO 侧沙箱/端点已就位（蓝图 M4 前置已满足）。
鉴权：NEKO_EXEC_TOKEN 环境变量，Bearer header，fail-safe（未配置返 error 不调用）。
"""
from __future__ import annotations

import os
from typing import Any, Optional

import httpx

NEKO_AGENT_BASE = os.environ.get("NEKO_AGENT_BASE", "http://127.0.0.1:48915")
NEKO_EXEC_TOKEN = os.environ.get("NEKO_EXEC_TOKEN", "")

_client: Optional[httpx.AsyncClient] = None


def _get_client() -> httpx.AsyncClient:
    global _client
    if _client is None or _client.is_closed:
        _client = httpx.AsyncClient(base_url=NEKO_AGENT_BASE.rstrip("/"), timeout=60.0)
    return _client


async def run_neko_action(action: str, payload: dict[str, Any]) -> dict[str, Any]:
    """调用 NEKO 执行端点。action ∈ {"computer_use", "browser_use"}。"""
    if action not in ("computer_use", "browser_use"):
        return {"success": False, "error": f"未知 action: {action}"}
    if not NEKO_EXEC_TOKEN:
        return {"success": False, "error": "NEKO_EXEC_TOKEN 未配置，拒绝调用（fail-safe）"}

    headers = {"Authorization": f"Bearer {NEKO_EXEC_TOKEN}"}
    path = f"/{action}/run"
    try:
        resp = await _get_client().post(path, json=payload, headers=headers)
        resp.raise_for_status()
        return {"success": True, "status": resp.status_code, **resp.json()}
    except httpx.HTTPStatusError as e:
        return {"success": False, "error": f"NEKO {action} HTTP {e.response.status_code}"}
    except httpx.HTTPError as e:
        return {"success": False, "error": f"NEKO {action} 网络错误: {e}"}
```

### 步骤 2：`agentic_tool_loop.py` 加 `neko_cua` 分支

在工具分发处（openclaw 分支旁）追加：

```python
    if tool_name == "neko_cua":
        from apiserver.neko_cua import run_neko_action
        action = arguments.get("action", "computer_use")
        payload = arguments.get("payload", {})
        result = await run_neko_action(action, payload)
        return result
```

同时 `intent_router.py:28` 的 `BUILTIN_TOOLS` 加 `"neko_cua"`。

### 步骤 3：环境变量

```bash
export NEKO_AGENT_BASE="http://127.0.0.1:48915"   # NEKO Agent Server
export NEKO_EXEC_TOKEN="<强随机值>"                # 与 NEKO 侧一致
```

## 五、关键假设与 fallback

| 假设 | 验证 | fallback |
|---|---|---|
| NEKO Agent Server 在 48915，`/computer_use/run` 可 POST | curl 探活（带 token） | `NEKO_AGENT_BASE` 环境变量改地址 |
| `NEKO_EXEC_TOKEN` 两端一致 | curl 带 token 返回非 401/503 | 对齐两端 env 值 |
| 沙箱已收紧（前置已满足） | 蓝图勘误 E1「✅ 已改」+ 代码 `_SAFE_BUILTINS` 已确认 | 无，前置不满足则阻断 M4 |

## 六、已知限制

1. **不做指令源策略**：本 SPEC 只做「传输桥」，陆墨「何时、为什么」派 CUA 任务，是 agent 决策层的事，不在本 SPEC。
2. **不做结果流式回传**：首版用「POST 一次 + 返回 JSON」同步模式，不接 task_update 事件流（`list_tasks` 轮询留后续）。
3. **单机假设**：NEKO Agent Server 默认 127.0.0.1 本地回环，跨机部署需重写鉴权（蓝图铁律 4）。

## 七、测试用例（云服可跑，mock httpx）

```python
# tests/test_neko_cua.py
import asyncio
from unittest import mock
from apiserver.neko_cua import run_neko_action, NEKO_EXEC_TOKEN

class _FakeResp:
    def __init__(self, status, data): self.status_code = status; self._d = data
    def raise_for_status(self):
        if self.status_code >= 400: raise Exception("http")
    def json(self): return self._d

# 1. 未配置 token → fail-safe 拒绝
def test_no_token_failsafe():
    with mock.patch.object(__import__("apiserver.neko_cua", fromlist=["NEKO_EXEC_TOKEN"]), "NEKO_EXEC_TOKEN", ""):
        r = asyncio.run(run_neko_action("computer_use", {}))
    assert r["success"] is False and "fail-safe" in r["error"]

# 2. 未知 action 拒绝
# 3. HTTP 200 → success=True 透传 JSON
# 4. HTTP 401 → success=False 带状态码
```

## 八、验收标准（可执行不变量）

```bash
# 1. 模块可编译
python -m py_compile apiserver/neko_cua.py

# 2. 测试全过（mock，不依赖真 NEKO）
python -m pytest tests/test_neko_cua.py -q

# 3. 分支已接入
grep -n "neko_cua" apiserver/agentic_tool_loop.py apiserver/intent_router.py   # 非空

# 4. 鉴权走环境变量（零硬编码密钥）
grep -c "os.environ.get(\"NEKO_EXEC_TOKEN\"" apiserver/neko_cua.py             # ≥1

# 5. 不碰 NEKO 源码（沙箱已收紧，桥接只加 scratchpad 侧）
git diff --stat -- NEKO | wc -l                                               # 0
```

## 九、提交规范

```
feat(m4): neko_cua 工具桥接 NEKO CUA/浏览器执行（Bearer 鉴权 + fail-safe）
```

---

*前置已满足确认：CUA 沙箱收紧（`_SAFE_BUILTINS` + allowlist + AST 预检 + 审计 + 30s 超时）✅；`/computer_use/run`、`/browser_use/run` 端点 + `require_exec_token` 鉴权 ✅。本 SPEC 只补 scratchpad 侧桥接。*
