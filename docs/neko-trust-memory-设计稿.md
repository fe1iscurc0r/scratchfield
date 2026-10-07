# NEKO trust 模块 · 记忆投毒防护设计稿

> 2026-08-29 · 沈遥线完成（原 AC-05）· 论文依据：记忆投毒 2608.21230/21159、InjecMEM 2608.23471、SkillBloat 2608.21929、AgentFlow 2608.22868
> 对齐：docs/memory_maas-design-spec.md（provenance 字段 P0 必填）
> 范围：只写防御设计稿 + 检测启发式，不写攻击 PoC

## 1. 威胁模型（记忆=攻击面）

| 攻击 | 机制 | 后果 |
|------|------|------|
| 记忆投毒（08-25） | 少量伪造记忆混入语料 | 1.2% 投毒 → 检索准确率 0.850→0.300 |
| InjecMEM（08-26） | 一次交互定向污染，retriever-agnostic anchor + 梯度搜索命令 | 后续检索持续输出攻击者内容 |
| SkillBloat | 技能文件当可信指令通道，token 放大 | 平均 5.4-10.1x 资源消耗 |
| 源注入（多端共享） | weixin/qqbot/cli 共享工作树，一端被攻 → 全端污染 | 一条假事实污染后续所有会话 |

共同根因：**写入路径无来源校验，读取路径无来源感知**。持久记忆既是资产也是攻击面——写入即信任，检索即暴露。

## 2. 写路径设计（写时校验链）

```
写入请求 (content, type, source_ctx)
  → 1. 来源分级：session | agent | file | external_MCP | user_direct
  → 2. 可信度评分 provenance.score（1-5）
  → 3. 权限判定：
        score ≥ 4 (user_direct / 高置信) → 直接写正式区
        score 2-3 (agent/session)        → 写正式区 + 标 provisional
        score ≤ 1 (external 未审查)      → 只写 draft 区（不参与检索），人工/用户确认后提升
  → 4. 冲突检测：与既有高置信记忆冲突？→ 冲突告警 + 默认保留高置信旧条目
  → 5. 写入：落 typed_memories + 同步 hybrid_search 索引（provenance 字段必填）
```

**来源分级规则（对齐供应链铁律）**：
- user_direct（用户明示）= 最高信任，直接写正式区
- agent（本 agent 推理产出，如授粉报告结论）= 常规信任，provisional 标记
- file/MCP（外来文件、MCP 工具返回）= 低信任，必须审查（对接 mcp-trust-audit-checklist）
- external 未审查 = 只进 draft 区

**draft 区**：独立表/独立索引，检索默认排除；用户确认或多次一致后提升。防止 InjecMEM 类"一次交互注入"直达检索层。

## 3. 读路径设计（provenance ranking）

- 检索结果按 `score 加权 + 时间衰减 + RRF 融合` 重排：
  `final_rank = rrf_rank * 0.6 + provenance_weight * 0.4`
- provenance_weight：user_direct=1.0 / agent=0.7 / provisional=0.5 / draft=不参与
- 高置信冲突记忆标记展示（"⚠️ 与历史记忆冲突，来源等级 X vs Y"），由上层 agent 决定采信
- 注入上下文时附来源标签（对齐 claude-mem 授粉点：platform_source 归一化）

## 4. 检测启发式（写路径实时检测 + 周期扫描）

| # | 启发式 | 描述 | 触发 → 处置 |
|---|--------|------|------------|
| H1 | 异常一致性 | 单来源在短时间内反复写入同一事实（N≥3 次/min） | 疑似注入 → 标低可信 + 告警 |
| H2 | 时间聚集 | 多条新记忆在短窗内集中到达（非用户会话节奏） | 批量审查 → 未审查全进 draft |
| H3 | 冲突检测 | 新记忆与既有高置信记忆矛盾 | 保留旧条目 + 告警 |
| H4 | 指令隐藏 | 记忆内容含"忽略/忘记/不要检查"类指令词 | 判可疑 → 只进 draft |
| H5 | token 放大 | 技能/记忆文件体积或引用量异常增长（SkillBloat） | 资源限额 + 审查 |
| H6 | 来源漂移 | 同一实体内容来源等级突变（低→高无人工确认） | 拒绝提升 + 告警 |

周期扫描：每日 cron 跑 H1/H2/H3 汇总（对齐授粉流水线"增量自动跑"偏好）。

## 5. 与 memory_maas SPEC 接口对齐

| memory_maas 字段 | trust 模块对接 |
|-----------------|---------------|
| provenance {source, ts, confidence, origin_rank} | 写路径第 1/2 步填充；origin_rank = 来源分级映射 |
| pinned / pinned_reason | 高可信记忆置 pinned（防 consolidation/retention 清掉） |
| warning 类型实体 | H3 冲突检测结果落 warning 实体 |
| archived_by | 投毒判定后的隔离归档（archived_by="trust_honeypot"） |

**数据流**：写请求 → trust 校验链 → typed_memories（正式/draft）→ hybrid_search 索引（draft 不索引）→ 检索时 provenance 重排 → 注入时来源标签。

## 6. 落地优先级

- P0：来源分级 + draft 区（写路径最小闭环，防 InjecMEM 直达检索）
- P1：provenance ranking（读路径重排）+ H1/H3 检测
- P2：H2/H4/H5/H6 + 周期扫描 cron
- 与 memory_maas sidecar 一起实现（同一数据目录、同一单写者模型）
