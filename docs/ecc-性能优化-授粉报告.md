# WO-03: ECC 性能优化提取报告

> 日期：2026-08-22 晚 | 委托：实验田维护者自做 | 状态：✅ 完成
> 输入：affaan-m/ECC（MIT，241k★）| 模式：API 直读（硬约束：不整包 clone）
> 结构：.agents/skills（43 个 agent）+ .claude/homunculus/instincts + agents/ + commands/

## 一、instincts 机制（ECC 核心创新）

### 1. 数据格式（YAML）

```yaml
---
id: everything-claude-code-conventional-commits
trigger: "when making a commit in everything-claude-code"   # 触发条件（自然语言）
confidence: 0.9                                               # 置信度
domain: git                                                   # 领域分类
source: repo-curation
source_repo: affaan-m/everything-claude-code
---
# 标题
## Action   ← 具体行动指令
## Evidence ← 证据（为什么这么干）
```

### 2. 存储层次（instinct-status 命令揭示）

- 项目级：`~/.claude/homunculus/projects/<project-id>/instincts/`
- 全局级：`~/.claude/homunculus/instincts/`
- **冲突规则：项目级覆盖全局级（ID 碰撞时）**

### 3. 生命周期命令

- `/instinct-import` — 导入 YAML 规则集
- `/instinct-export` — 导出当前规则
- `/instinct-status` — 按领域分组显示 + 置信度条 + 观察统计

### 4. 机制本质

instincts = **"仓库级行为规范"的可插拔规则库**——把隐性知识（提交风格/命名规范/代码风格）编码成 `trigger+action+evidence+confidence` 结构，随仓库分发，导入即生效。

## 二、harness-optimizer（性能优化 Agent）

### 工作流（5 步）

```
1. Run /harness-audit → 收集基线分数
2. 找 top3 杠杆区（hooks / evals / routing / context / safety）
3. 提出最小可逆配置变更
4. 应用 + 验证
5. 报告 before/after delta
```

### 关键设计

- **改 harness 配置，不改产品代码**（"Raise agent completion quality by improving harness configuration, not by rewriting product code"）
- 偏好小变更 + 可测效果
- 跨平台兼容（Claude Code / Cursor / OpenCode / Codex）
- 带 **Prompt Defense Baseline**（防注入基线，每个 agent 必带）

### performance-optimizer（性能分析专家）

- 角色化 agent（profiling/bundle/运行时/React/数据库/内存 六域）
- 提供直接可跑的分析命令（node --prof / lighthouse / webpack-bundle-analyzer）
- 带性能指标表（metric/target/超限动作）

## 三、与 scratchpad 对照（重点：context_compressor）

| 维度 | ECC instincts | scratchpad context_compressor | 互补性 |
|------|--------------|------------------------------|--------|
| 管什么 | **何时做什么**（行为触发） | **压缩什么**（上下文瘦身） | 正交互补 |
| 触发 | trigger 自然语言规则 + confidence | 无主动触发（被动调用） | ECC 补触发 |
| 存储 | YAML + 项目/全局两级 + 冲突覆盖 | Python 代码内 | ECC 格式更可插拔 |
| 来源 | repo-curation（从仓库历史提炼） | 手写 | ECC 可自动化 |

**边界图**：
```
ECC instincts ──决定──> "现在该做 X（触发）"
                              │
                              ▼
                context_compressor ──决定──> "为做 X 腾出哪些上下文（压缩）"
```

## 四、授粉建议

1. **instincts 机制 → 云服工作流**（高价值，低成本）：
   - 给 Hermes/NEKO 加 `instincts.yaml` 规则库：提交规范/文件命名/代码风格/射频频段规范
   - 实现轻量 `instinct-status`（读 YAML → 分组展示）≈ 100 行 Python
2. **harness-audit 模式**：定期跑"配置审计"（hooks/cron/mcp 注册表健康检查），输出基线分数+杠杆点
3. **Prompt Defense Baseline 抄进 mcpserver**：现有 security_utils 已做模块白名单，补"agent 提示词防注入基线"（untrusted data 处理规则）
4. **置信度优先级**：context_compressor 的压缩策略可加 confidence 字段，高置信才自动压缩

## 五、硬约束检查

- ✅ API 直读未 clone 大仓（tree API + contents API）
- ✅ 报告含 instinct 触发条件清单（trigger 字段结构 + 3 例）
- ✅ 与 context_compressor 边界图（第三节）
