# Agentic Loop 对话流与迭代控制（卷121 W121-02 · 2026-09-17）

工单要求「画出当前调用链，核实工具结果是否回注」。核实结论先说：**回注本来就在**
（`apiserver/agentic_tool_loop.py` native 路径写 `role=tool` 消息、兼容期写 user 消息），
真正的缺口是 ①失败检测失真 ②迭代参数硬编码 ③收敛时不给模型「已完成/未完成」清单
④会话号没传进工具（按会话隔离形同虚设）。本卷把这四条补上，并在真实链路上验证。

## 调用链（改造后）

```
chat.py: /v1/chat/stream
  └─ run_agentic_loop(messages, session_id, tools=OpenAI schemas)      ← max_steps 默认 8（agent_loop 配置）
       ├─ 每轮：compress_context（超阈值才压）
       ├─ llm_service.stream_chat_with_context(tools=...)
       │     ├─ 原生 function calling → chunk type=tool_calls_native → _convert_native_to_dispatch
       │     └─ 兼容期：文本 ```tool``` 块 → parse_tool_calls_from_text
       ├─ 前端事件：round_start / tool_calls / tool_results / tool_retry / round_end
       ├─ execute_tool_calls(actionable_calls, session_id)
       │     ├─ _run_tool_gate ── TOOL_PRE_EXECUTE waterfall（卷119；确认门挂这里，W121-03）
       │     ├─ _dispatch_one_call
       │     │     ├─ mcp  → _inject_session_id（本卷新增）→ _execute_mcp_call → mcpserver 桥
       │     │     ├─ openclaw / tool → OpenClaw 网关
       │     │     └─ naga_control / live2d
       │     ├─ 失败重试（本卷新增，见下表）
       │     └─ trace span `tool:<name>`（重试时 `#retryN`，属性含 attempt / effective_status）
       ├─ ★ 结果回注：native → assistant(tool_calls) + role=tool 消息
       │              兼容期 → assistant + user("[工具结果 …]")
       ├─ 消息队列注入（排队消息并入最后一条 user 消息）
       └─ 收敛：max_steps 用尽 / 连续两轮全失败 → 注入 build_convergence_prompt(ledger) → 最后流式一轮（不带 tools）
```

## 失败检测：MCP 错误体修正

MCP 桥把业务错误包在返回体里（`{"status": "error", "message": …}`），而 dispatch 层对 MCP 调用
一律标 `status=success`。只看外层会出现「5 轮全是参数错误，循环却认为一切正常」——
真实 E2E 第一次跑就撞上了。

- 新增 `_effective_status(result)`：外层 `error`，或返回体命中 `"status": "error"` → `error`
- 使用范围：失败计数、重试判定、收敛摘要、`tool_results` 展示状态
- **不动** W119 的熔断与指标口径（那里仍用外层 ok，避免影响 32 个既有 agent）

## 失败重试（`agent_loop.max_retries`，默认 2）

| 判定 | 依据 | 行为 |
| --- | --- | --- |
| 可重试 | 返回文本含 timeout/超时/connection/network/429/502/503/504/执行异常 | 退避 `retry_backoff_s` 后重试，直到尝试次数 > max_retries |
| 不重试 | 含 hard_denied / not_allowlisted / shell_metachar_denied / path_\* / 等待用户确认 / 用户拒绝 / 被安全门拦截 / 权限 | 立即返回，`attempts=1` |
| 不重试 | 安全门 veto（确认门拦截等） | 压根不进执行器 |
| 全部失败 | `attempts > 1` 且仍失败 | 结果前缀「（已重试 N 次仍失败）」，前端收到 `tool_retry` 事件 |

## 收敛（`build_convergence_prompt`）

| 原因 | 触发 | 提示内容 |
| --- | --- | --- |
| `max_steps` | 轮数达上限（for-else） | 「工具迭代已达上限（N 步）」+ 已完成/未完成清单 |
| `consecutive_failures` | 连续 2 轮全部工具真实失败 | 「连续多轮工具调用全部失败」+ 失败原因逐条 |
| （无工具调用） | 本轮没有 actionable calls | 不收敛，直接结束 |

收敛轮**不传 tools**（禁止再调工具），可加 `agent_loop.converge_hint` 追加自定义要求。

## 会话号注入（W121-04 隔离前提）

`_inject_session_id`：只在**该工具 manifest 自己声明了 `session_id` 入参**时才注入当前会话号，
模型显式给值时不覆盖。否则 Code Workspace 的 `workspace/<session_id>/` 会全部塌到 `default/`，
「按会话隔离」名存实亡（实测抓到，已修）。

## 配置（`config.json` 的 `agent_loop` 段）

| 键 | 默认 | 说明 |
| --- | --- | --- |
| `max_steps` | `8` | 迭代轮数上限；显式传 `max_rounds` 参数时以参数为准（老调用不回退） |
| `max_retries` | `2` | 单次工具调用失败后的重试次数上限（0 = 不重试） |
| `retry_backoff_s` | `0.5` | 重试间隔 |
| `converge_hint` | 空 | 收敛轮附加提示 |

## 真实链路实测证据

驱动器：`tools/e2e_agentic_loop.py`（真实 LLM → 原生 function calling → 真实 code_workspace 沙箱）。

```bash
# 场景 A：写代码 → 跑测试 → 全绿
.venv/Scripts/python.exe tools/e2e_agentic_loop.py --max-steps 6 --session e2e-w121

# 场景 B：预置「实现有 bug + 测试失败」→ 跑 → 定位 → 改 → 再跑（工单要求的闭环）
.venv/Scripts/python.exe tools/e2e_agentic_loop.py --seed --max-steps 8 --session e2e-w121-fix
```

场景 B 实录（节选）：

```
[E2E] 第 1 次工具调用: ['code_workspace:test_run', 'code_workspace:file_read', 'code_workspace:file_read']
[E2E]   结果 test_run status=success: {'ok': False, 'exit_code': 1,
         'summary': {'passed': 0, 'failed': 1, 'failed_tests': ['tests/test_calc.py::test_add']}}
[E2E]   结果 file_read: 'def add(a, b):\n    return a - b  # BUG: 应该是加法\n'
[E2E] 第 2 次工具调用: ['code_workspace:file_edit']
[E2E]   结果 file_edit: {'diff': '@@ -1,2 +1,2 @@\n def add(a, b):\n-    return a - b  # BUG: 应该是加法\n+    return a + b'}
[E2E] 第 3 次工具调用: ['code_workspace:test_run']
[E2E]   结果 test_run: {'ok': True, 'exit_code': 0, 'summary': {'passed': 1, 'failed': 0}}
===== 最终答复 =====
- 定位到的 bug：calc.py 里 add(a, b) 写成了 return a - b，导致 add(1, 1) 返回 0。
- 修复：改为 return a + b。
最终测试结果：passed: 1 / failed: 0
===== 工作区 …/code_workspace/workspace/e2e-w121-fix =====
- calc.py (34B) / tests/test_calc.py (65B)
```

> 注：`test_run` 对「测试失败」返回 `status=success` + `ok=false`（工具本身跑成功了，是测试没过），
> 结果体里 passed/failed/exit_code 齐全，模型据此自行决定下一步——这是刻意的语义区分。

## 测试

```bash
.venv/Scripts/python.exe -m pytest tests -k "code_workspace or agentic_loop_flow" -q
# 23 passed
```

覆盖：结果回注、两轮闭环、max_steps 收敛、连续失败收敛、MCP 错误体修正、可重试/不可重试分类、
重试上限与关闭、会话号注入（只注入声明过的工具）、收敛提示词与 handoff 契约。

## 回滚

`agent_loop` 配置删掉即用内置默认；`run_agentic_loop(max_rounds=N)` 参数优先级最高，
回退到旧行为只需调用方继续显式传 `max_rounds`。
