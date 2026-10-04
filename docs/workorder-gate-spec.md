# 工单 phase/gate 状态机 + 审批门 SPEC（W66-03）

> 来源 docs/多agent协作-对照报告.md · 不可逆 action 需显式批准

## 状态机

```
in_review ──gate.resolved──> 推进
   │
   └──revision_requested（打回）
```

- gate **永不自动 resolve**，只能显式批准令牌 `APPROVED` 触发。
- 工单模板新增 `approval_gates: []` 字段；不可逆 action 返回 `PENDING_APPROVAL`。

## BREAK-LOOP

同一 tool+意图 3 轮无进展 → 注入 `BREAK-LOOP: ...` 破环指令。

## 实现

`tools/workorder_state_machine.py`：`WorkOrder`（gate 审批）+ `LoopDetector`（破环）。
