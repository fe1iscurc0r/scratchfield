# W73-08 Agent 权限内核 + Guardrails 评估

> 上游：Talos 权限内核（HN 14p）+ Conduct guardrails（HN 22p）+ Trail of Bits VM 隔离研究（HN 192p）· 许可待核（混合）
> 安全类：只写防御。

## 1. 项目定位

三道安全护栏：①模型与 shell 之间加**权限内核**（权限最小化）；②MCP 工具调用**护栏/白名单**；③Trail of Bits 研究发现「VM 无法隔离网络 agent」（隔离边界重估）。

## 2. 架构拆解

- **Talos 权限内核**：模型动作先过权限内核，按最小权限放行到 shell。
- **Conduct guardrails**：MCP 工具调用白名单 + 行为护栏。
- **VM 隔离研究**：网络 agent 仍可经网络侧信道逃逸，VM 隔离不足——需应用层护栏而非仅 VM。

## 3. 与本仓对照

| 维度 | 上游 | 本仓 |
|---|---|---|
| 权限 | 权限内核 + 工具白名单 | Sandboxed Execution（SPEC-R3）+ W60-02 ContextLeak 防御 + 安全编排 |
| 隔离 | VM 隔离不足 | 应用层护栏 |

## 4. 可落地借鉴点（≥3）

1. **权限内核（模型↔shell 之间）**：动作先过确定性权限校验再达 shell，比「模型自觉」可靠——与我们的 skill_gate（tools/skill_gate.py）同向，可补权限最小化层。
2. **MCP 工具调用白名单**：工具调用显式白名单 + 行为护栏，作为 W60-02 ContextLeak 防御的补充。
3. **「VM 隔离不足」的启示**：网络 agent 不能只靠 VM 隔离，需应用层确定性护栏（呼应 A34 ROPE 起源门控）。

## 5. 许可裁定 + 结论

- **许可**：混合来源，无统一开源许可 → **许可待核**；安全类只参考防御设计。
- **与 SPEC-R3 协同**：权限内核 + 工具白名单可落到 SPEC-R3 Sandboxed Execution 的权限最小化层；skill_gate 已有基础，可在此基础上补「模型↔shell 权限内核」。
