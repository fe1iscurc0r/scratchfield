# Trace Integrity 审计清单（七项标准）

> 目标：多 Agent 协作中「答案正确但 trace 非法」是部署可靠性盲区。
> 本清单把 schema-valid / replayable / auditable 拆成七项可判定标准，
> 每项给出判定方法，与 `audit.py` 的七个 criterion 一一对应。

| # | 标准 | 英文 | 判定方法 |
|---|------|------|----------|
| 1 | schema 合法 | schema-valid | 必需字段（id/timestamp/source/type/owner）齐全且类型正确；`check_schema()` 返回空列表 |
| 2 | 时间戳齐全 | timestamp complete | 每条记录 `timestamp` 存在且可解析（epoch 秒或 ISO-8601） |
| 3 | id 唯一 | id unique | 跨记录 `id` 不重复；重复即 FAIL |
| 4 | 来源可溯 | source traceable | `source` 非空，能回溯到出处 |
| 5 | 回放无缺口 | replayable | 记录按时间线可回放：时间戳单调不减、无 None 断链 |
| 6 | 边界明确 | boundary clear | `type` 属于已知边界（workorder/delivery/memory/report/spec/log/config）或带显式 `scope` |
| 7 | 责任人明确 | owner identified | `owner` 非空，责任可追到人/agent |

## 判定输出

- 七项全 PASS → 整体 `PASS`
- 任一项 FAIL → 整体 `FAIL`，`ISSUE:` 行列出具体记录与原因
- 报告为纯文本，可 `grep -E "CRITERION|ISSUE|VERDICT"` 检索

## 对应代码

- 字段定义：`schema.py`（`REQUIRED_FIELDS` / `KNOWN_TYPES` / `parse_timestamp`）
- 审计器：`audit.py`（`check_schema` / `audit` / `AuditReport`）
- CLI：`python -m mcpserver.trace_audit audit --check-file FILE`

## 与供应链铁律的关系

七项标准是供应链铁律「外来文件默认不信任」的工程化落地：只有 schema 合法、
时间线可回放、来源与责任人可追溯的 trace，才允许进入后续 workflow；缺任何一项，
交付物即使在业务上「答案正确」，其 trace 也不具备可部署可靠性。
