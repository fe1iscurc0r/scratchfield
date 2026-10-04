# ActGov / LeaseGuard SPEC — 轮23 授粉点①：Agent 治理模式 → 工单流水线的特权操作守卫

> 来源：卷151 任务C（2026-09-23 晨增量轮授粉点：ActGov 策略约束验证 + LeaseGuard 租约式准入）
> 落盘：砚 · 状态：**SPEC（未开工）** · 落点：`apiserver/event_bus/`（既有闸门体系之上）

## 1. 问题（本仓真实存在的风险）

本仓的 agent 已经在做**破坏性操作**：`git push`、外部 API 写、文件删除、设备动作。
现状是「有闸门但不成体系」：

| 已有模块 | 现状能力 | 缺口 |
|---|---|---|
| `apiserver/event_bus/confirm_gate.py` | 对特定工具的调用做**确认放行**（按会话签名确认/拒绝，记审计） | 确认**无时效**、**无范围**：一次确认后同类操作可反复放行 |
| `apiserver/event_bus/tool_gate.py` | 工具级准入判定 | 无"这一次授权覆盖哪些参数域"的概念 |
| `apiserver/event_bus/tool_pipeline.py` | 工具三段管道（guard / execute / 广播） | 策略校验可挂进 guard 段，但目前是零散规则 |
| `mcpserver/scope.py` | per-角色/会话 工具可见性（展示层+执行层双校验） | 只管**可见性**，不管**这次调用是否被授权** |
| `tools/skill_gate.py`、`tools/test_skill_gate.py` | 技能门控 | 与特权操作无关 |

**要补的两件事**：策略约束**可验证**（ActGov）、授权**有时效与范围**（LeaseGuard）。

## 2. ActGov：策略约束验证（声明式策略 + 执行前校验）

**核心**：策略不是散落在代码里的 `if`，而是**声明式清单**，在工具执行的 guard 段统一校验。

```yaml
# 建议落点：apiserver/event_bus/policies/actgov.yaml（新）
version: 1
rules:
  - id: git-push-protected
    match: { tool: shell, argv_regex: 'git\\s+push' }
    require: lease            # 必须有租约
    lease_scope: { branch: "!main" }   # 禁止直推 main
    on_violation: block
  - id: external-api-write
    match: { tool: http_request, method: "!GET" }
    require: lease
    lease_scope: { domain: allowlist }
    on_violation: block
  - id: fs-delete-bulk
    match: { tool: fs_delete, count_gt: 50 }
    require: confirm + lease
    on_violation: block
```

**验证（"约束验证"的含义）**：每条规则要有**反例测试** —— 用一条**应当被拒**的调用去跑，断言它真的被拒，并在审计流里留痕。没有反例测试的策略等于没有策略。

## 3. LeaseGuard：租约式准入（限时、限范围、过期即失效）

**核心**：把"一次性确认"升级成**带时空边界的租约**：

| 租约字段 | 含义 | 例 |
|---|---|---|
| `lease_id` | 租约标识 | `lz-2026-09-23-a3f1` |
| `granted_to` | 会话/角色 | `session:trae-agent` |
| `actions` | 允许的动作集 | `["git.push:branch=workorders-*"]` |
| `not_after` | 过期时刻（**硬上限**） | `+30min` |
| `max_uses` | 最大使用次数 | `1` |
| `budget` | 可选资源上限 | `bytes_written<=10MB` |
| `revoked` | 显式吊销位 | `false` |

规则：
1. **默认无租约 = 拒绝**（fail-closed，与本仓 `fail-closed` 既有口径一致）；
2. 租约**过期/超次/越界** → 立即失效并审计，**不静默续期**；
3. 高危动作（推送 main、生产 API 写）**必须人工**签发，不做自动续租。

## 4. 与工单流水线的结合（工单提示词守卫）

工单里已经天然标注了特权面（如「提交到 scratchpad main」「推送分支」）。据此：

1. 工单解析阶段：扫出**特权步骤**（push / 外部写 / 删）→ 生成**审批点清单**；
2. 执行阶段：特权步骤若无租约 → 停下并**输出申请文本**（要什么权限、范围、时长、为什么）；
3. 审批后签发租约 → 执行 → 审计落盘（`lease_id` + 动作 + 结果）；
4. 工单收尾时**盘点未使用的租约并吊销**（避免留活口）。

> 本仓已有先例可循：`docs/` 下多卷工单要求「对外动作先问、对内动作放手做」—— LeaseGuard 是把这条**口头规矩**变成**可执行闸门**。

## 5. 落地步骤

1. `actgov.yaml` 策略 schema + 加载器（放在 `apiserver/event_bus/policies/`）
2. 在 `tool_pipeline.py` 的 **guard 段**挂策略校验（不改已有确认门语义，叠加一层）
3. `LeaseGuard` 实现：签发/校验/过期/吊销 + 审计（复用 `event_bus/trace.py` 与 `event_store.py`）
4. 反例测试：每条规则至少 1 个"应拒"用例 + 1 个"持租约应放行"用例
5. 工单解析器：从工单文本抽特权步骤 → 审批点清单（可先人工，后自动化）

## 6. 验收

- [ ] `actgov.yaml` 有 ≥3 条规则，且每条有对应的**应拒**用例（测试全绿）
- [ ] 无租约时 `git push` 类调用被拒，且拒绝原因写入审计
- [ ] 租约过期后**同一调用**被拒（用 `not_after` 直接跑过期判定，不依赖 sleep）
- [ ] 滥用防护：租约范围外的分支/域名被拒（`lease_scope` 生效）
- [ ] 与既有 `confirm_gate` 的语义边界写成文档（谁先谁后、是否可能绕过）

## 7. 未决项 / 风险

1. **策略与既有闸门的关系**：`confirm_gate` 是"人确认"，ActGov 是"策略校验"，两者叠加顺序需拍板（建议：策略先行，策略要求确认时再进确认门）。
2. **绕过面**：agent 若能用 `shell` 直接调系统命令，闸门必须挂在**管道层**而不是某个工具壳上 —— 否则"换个工具名"就绕过了。
3. ActGov/LeaseGuard 这两个名字来自论文，本仓**不引入其实现代码**，只取"策略验证 + 租约准入"两个机制。

> 现状：**未开工**。本文件是把授粉点变成可施工清单，不含任何已完成的实现。
