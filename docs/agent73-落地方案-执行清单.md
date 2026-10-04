# agent-73 落地方案（SPEC-R1~R4 · 评估转落地）

> 智能体 73 · 4 项落地 · 对应 agent-72 的 W72-07~10 评估（Graphiti/Feedback-Sensors/Sandboxed/SLM）
> 性质：落地为「方案级」设计（跨会话记忆层/质量门升级/沙箱执行层/降本路由层），实现路径见各条。

## SPEC-R1 · Graphiti 时序知识图谱 → 跨会话持久记忆层

- **目标**：把 bi-temporal 图记忆引入 memory_maas，旧事实失效而非覆盖。
- **路径**：memory_maas 增加 `temporal_edges`（事实带 valid_from/valid_until），检索时过滤失效事实；不引 Neo4j 重依赖（自研 SQLite 时序边）。
- **验收**：旧事实失效后可检索到新事实、旧事实不覆盖。
- **借鉴**：Graphiti 的 bi-temporal 语义 + sub-second 检索（Apache-2.0 可借鉴）。

## SPEC-R2 · Feedback Sensors → skill_gate 质量门升级

- **目标**：把编译器/linter/测试等确定性质量门接入 skill_gate 产出管道，失败自动自纠正。
- **路径**：扩展 `tools/skill_gate.py`——产出后跑确定性质量门（pytest/lint），失败则注入自纠正指令（呼应 BREAK-LOOP）。
- **验收**：质量门失败 → 任务不通过；自纠正后重跑通过。
- **借鉴**：Thoughtworks Radar 的「确定性质量门」方法论。

## SPEC-R3 · Sandboxed Execution → Agent 沙箱执行层

- **目标**：隔离环境（microVM/container）运行 Agent，限制文件/网络/资源。
- **路径**：复用权限内核（tools/permission_kernel.py，agent-74 已原型）+ 沙箱执行（container/microVM 方案）。确定性门控优先于 VM 隔离（呼应 W73-08「VM 无法隔离网络 agent」）。
- **验收**：未授权动作被拦截；正常调用通过率 ≥90%。
- **借鉴**：Trail of Bits「VM 隔离不足，需应用层护栏」结论。

## SPEC-R4 · SLM 小模型路由 → 降本路由层

- **目标**：小模型（Phi-4-mini/Qwen3-0.6B）路由替代大模型 + 语义熵幻觉检测。
- **路径**：路由层——简单任务走 SLM，高语义熵（不确定）任务升级大模型；对接 K40 端上推理 + 熵引导蒸馏（W73-09）。
- **验收**：简单任务命中 SLM（省 token），复杂任务升级大模型（精度不降）。
- **借鉴**：Thoughtworks Radar SLM Assess + 语义熵 Assess。

## 执行清单

- **完成**：4/4 落地方案。
- **性质**：方案级（设计 + 实现路径），未写代码——与 agent-74 已有原型（permission_kernel/skill_gate）衔接，实现留待后续接入。
- **依赖**：SPEC-R2/R3 复用已有 skill_gate + permission_kernel；SPEC-R4 复用 K40 端上推理。
