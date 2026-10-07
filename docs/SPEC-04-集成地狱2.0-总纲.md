# SPEC-04 · 集成地狱 2.0 总纲

> 日期 2026-08-22 深夜 | 状态：规划阶段（不写码）
> 原则：项目庞大、眼光长远、细节严谨、代码处处落实
> 一句话：把今天所有报告合成一张可执行的融合地图

## 一、背景（候选清单）

| 来源 | 内容 | 状态 |
|------|------|------|
| 扫货 | 166 候选 → 137 可融合 | ✅ 已落盘 /tmp/sweep_candidates.json |
| 授粉 Batch-1A | openclaw（session-lineage）、deepseek-harness（Service Definition） | ✅ 已报告 |
| 授粉 Batch-1B | graphify（Lumo 知识图谱）、claw-code（cron 分流） | ✅ 已报告 |
| 授粉 Batch-2 | agent-skills、obsidian-skills、guizang-ppt、nuwa-skill | ✅ 已报告 |
| 授粉 Batch-3 | meshcore-open、ClusterDuck、FlipBits（HW-01 参考） | ✅ 已报告 |
| 授粉 Batch-4 | cozo、sdrtrunk、meshtastic、ground-station、chdb、gstack、mattpocock/skills、Understand-Anything、headroom | ✅ 已报告 |
| 生态情报 | agentskills.io 成行业标准（40+ 产品）、Context7 MCP | ✅ 已报告 |
| 技术债务 | D-01 ~ D-07 | ✅ 已登记 |
| 大工程总纲 | NEKO 巨人 / mcpserver 枢纽 / rf_brain 雏形 / Lumo 业务层 | ✅ v0.1 |

## 二、目标

**集成地狱 2.0 = 把"四个子系统 + 一批新候选"融合成一个可运行的全栈智能体**：

感知（射频 rf_brain）→ 认知（NEKO 记忆 MaaS）→ 行动（mcpserver 工具总线）→ 应用（Lumo 科研/桌宠生活）

不做：重写、重复造轮子、为授粉而授粉（有等效的不装）。

## 三、系统架构（融合后的目标形态）

> **铁律：NEKO 核心冻结不动，一切新能力走端口/sidecar 挂载**
> 模式：独立进程（sidecar）→ API/MCP 端口 → 主系统调用

```
┌─────────────────────────────────────────────────────┐
│  应用层  Lumo 科研工作台 │ NEKO 桌宠壳（冻结）│ 生活工具 │
│          ┌──────────────────────────────────────┐    │
│  认知层  │  记忆 sidecar（cozo 独立进程 + API）   │    │
│          │  会话血统+混合检索+索引卡 ［端口挂载］  │    │
│          └──────────────────────────────────────┘    │
│  行动层  mcpserver 工具总线（MCP 工具调度/白名单）    │
│          ┌──────────────────────────────────────┐    │
│  感知层  │  rf_brain 射频大脑                     │    │
│          │  + sdrtrunk sidecar（JVM 子进程桥）    │    │
│          └──────────────────────────────────────┘    │
└─────────────────────────────────────────────────────┘
```

### 四个融合点（全部走端口，不侵入核心）

1. **mcpserver ↔ 记忆 sidecar**：cozo 独立进程暴露 HTTP/API → mcpserver 注册为 MCP 工具 → 全系统可调，NEKO 核心零改动
2. **mcpserver ↔ rf_brain**：sdrtrunk 解码结果 → 工具总线事件 → 频谱数据入库
3. **mcpserver ↔ Lumo**：graphify GraphRAG / duckdb 工作台注册为 MCP 工具
4. **skills 体系**：186 个 skills 做 agentskills.io 规范体检 → 跨 agent 可移植

## 四、工作包拆分（按优先级）

| 编号 | 工作包 | 动作 | 落点 | 依赖 | 模式 |
|------|--------|------|------|------|------|
| W-01 | sdrtrunk sidecar | JVM 独立进程桥，多协议解码（P25/DMR） | rf_brain P6 | 无 | Trae 工单 |
| W-02 | cozo 记忆 sidecar | 独立进程 + HTTP/API，记忆三套分家 → 单库试点 | 端口挂载（不动 NEKO） | 无 | 沈遥自做 |
| W-03 | graphify GraphRAG | 代码库/文献 → 知识图谱 + 向量检索 | Lumo P2 | 已装 | Trae 工单 |
| W-04 | skills 规范体检 | 扫描 186 skills frontmatter → 批量修复 | skills/ | 无 | 沈遥脚本 |
| W-05 | Context7 MCP | 接入防 API 幻觉 | mcpserver | 无 | 沈遥自做 |
| W-06 | 记忆 MaaS API | sidecar 暴露 会话血统+混合检索 → MCP 工具注册 | 端口挂载（不动 NEKO） | W-02 | Trae 工单 |
| W-07 | gstack 编排参考 | 读 23 代理编排 → 优化 delegate_task 用法 | Hermes agent | 无 | 沈遥自做 |
| W-08 | meshtastic 协议参考 | 对照 MeshRadio 设计（路由/加密） | HW-01 | 无 | 文档级 |
| W-09 | academic 16 融合 | MODEL_INTERFACE×16 → knowledge-base | Lumo P1 | 545M 已核 | Trae 工单 |

## 五、执行策略（三线并行）

1. **Trae 工单线**（走 GitHub）：W-01 sdrtrunk 桥 / W-03 graphify / W-06 记忆 MaaS / W-09 academic 16 —— 给 SPEC 拆解 + 验收标准，Trae 写码
2. **沈遥自做线**：W-02 cozo 评估 / W-04 skills 体检 / W-05 Context7 / W-07 gstack —— 轻量、快、不占工单
3. **NEKO 意见线**：MaaS 打通后 NEKO 可对工单提意见（评审角色）——token 不给图像，全砸代码/调研

**顺序**：先 W-04（30 分钟见效）→ W-05（防幻觉立即提升写码质量）→ 再 Trae 重工单（W-01/W-03/W-06/W-09 并行下发）

## 六、验收标准（每个工作包）

| 工作包 | 验收 |
|--------|------|
| W-01 | 真实音频文件过桥 → 解出 P25/DMR 帧，输出结构化 JSON |
| W-02 | cozo 试点库跑通：同一查询横跨关系+图+向量 |
| W-03 | 知识图谱生成 → 对图谱提问得到引用来源的回答 |
| W-04 | 体检脚本输出合规率，186 个 skills 修复到 100% |
| W-05 | Context7 注册进 mcpserver，写码时拉取库文档命中率↑ |
| W-06 | 全系统任一模块调记忆 API 成功返回会话血统 |
| W-07 | delegate_task 编排模式改造 1 处落地 |
| W-08 | 协议对照表输出（MeshRadio vs Meshtastic 差异） |
| W-09 | 16 个 MODEL_INTERFACE 全部接好，Lumo 可调用 |

## 七、风险与债务联动

- D-01（rf_brain 真机）不阻塞 W-01 开发（模拟音频可测）
- D-04（academic 16）被 W-09 消化
- D-06（授粉 A3/C3 推远端）在新工单下发前先确认
- **许可结论（已核实）**：NEKO=Apache-2.0，cozo=MPL-2.0。MPL 是文件级 copyleft，调用/链接不传染，与 Apache/GPL/AGPL 均兼容——cozo 直接嵌入合法；但按"NEKO 不动"铁律仍走 sidecar 端口挂载，许可+架构双保险
- **token 纪律**：本轮不给 gptimage2，图像类全部延后

## 八、结论

候选已满仓，地图已画好，铁律已立（NEKO 冻结、端口挂载）。下一轮动作：W-04 + W-05 先落地（沈遥线），W-01/W-03/W-06/W-09 拆 SPEC 下发 Trae。


