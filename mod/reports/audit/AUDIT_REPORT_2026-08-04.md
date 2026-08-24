# 🔍 多智能体审查总报告

> 审查时间: 2026-08-04 | 5 Agent 并行 | 30包 → scratchpad

---

## 五维度汇总

| 维度 | 审查 Agent | 范围 | 通过率 | 关键发现 |
|------|-----------|------|--------|---------|
| 💻 代码质量 | review_code | 14 agent_*.py | 通过但有瑕疵 | 8 类 P0/P1 问题 |
| 📋 Manifest 合规 | review_manifests | 14 manifest.json | ⚠️ 需修 | 9 个重复 key |
| 📝 Skill 合规 | review_skills | 5 SKILL.md | **0/5 ❌** | 全员缺 4 字段 |
| 📚 参考笔记 | review_references | 9 份笔记 | 3✅ / 5⚠️ / 1❌ | anything-llm 严重超标 |
| ⚙️ 集成验证 | review_integration | 全链路 | ✅ 0致命错 | 16 警告 |

---

## 🔴 P0 — 必须立即修复

### 1. handler.keys() crash bug (agent_frida)
```python
# ❌ 原代码: agent_frida.py dispatcher
handler = dispatcher.get(tool)
if handler is None:
    result = {..., "message": f"Unknown tool: {tool}. Available: {list(handler.keys())}", ...}
    #                                                                  ^^^^^^ handler is None!
```
`handler` 为 `None` 时调 `.keys()` 导致 `AttributeError`。影响 frida 的未知 tool 路径。

### 2. manifest class 与代码不匹配 (8 个 agent)
| Manifest 声明 | 代码实际类名 | Agent |
|---|---|---|
| `FridaAgent` | `AgentFrida` | agent_frida |
| `LLMDecompileAgent` | `AgentLLMDecompile` | agent_llm_decompile |
| `PentestAgent` | `AgentPentest` | agent_pentest |
| `RuntimeAgent` | `AgentRuntime` | agent_runtime |
| `StrixAgent` | `AgentStrix` | agent_strix |
| `WafAgent` | `AgentWaf` | agent_waf |
| `AnimationAgent` | `AgentAnimation` | agent_animation |
| 多个 | 类名不统一 | A 组各 agent |

### 3. 返回值不一致 — 7 个 agent 返回 dict 而非 JSON string
manifest 规范 1.3 节要求 `handle_handoff` 返回 JSON 字符串。7 个 agent 返回 `dict`：
- agent_animation, agent_frida, agent_llm_decompile, agent_pentest, agent_runtime, agent_strix, agent_waf

另 7 个返回 `json.dumps(result)` 正确 ✅：nuclei, trivy, sbom, signing, osint, decompile, browser

---

## 🟡 P1 — 应尽快修复

### 4. Skill YAML 字段缺失 (5/5)
所有 5 个 Skill 均缺 `version`, `author`, `tags`, `enabled`

### 5. Manifest 重复 key: `entrypoint` vs `entryPoint` (9 个)
JSON 标准大小写敏感，但 PowerShell ConvertFrom-Json 会报错

### 6. agent_waf payload 注入风险
payload 直接拼入 SecLang 规则字符串，无转义

### 7. agent_runtime 硬编码 Linux 路径
`/tmp/_falco_rule_check.yaml`, `/var/log/`, `pgrep` — Windows 下不可用

### 8. anything-llm 架构笔记严重超标 (5.4KB > 3KB 限制)

---

## 🟢 P2 — 优化建议

### 9. 6 个 A 组 agent __init__.py 为空
nuclei, decompile, osint, sbom, signing, trivy — 不阻塞功能但不够规范

### 10. 7 个 agent __init__ 中 raise RuntimeError
CLI 缺失时模块完全不可 import — 应为 LazyInit 或 None

### 11. 5 份参考笔记擦线超标 (3.0~3.6KB)
pentest-agents, graphiti, mastra, flowise, dify

---

## 📊 修复优先级

| 优先级 | 问题数 | 预计工作量 |
|--------|--------|-----------|
| P0 立即 | 3 类 (8+ agent) | 1 Agent 并行修 |
| P1 尽快 | 5 类 | 2 Agent 并行修 |
| P2 优化 | 3 类 | 1 Agent 修 |
