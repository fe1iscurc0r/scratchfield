# 工单 214 · 记忆层第二梯队融合调研（EverOS / tigerless agent-memory / neo-chat）

> 委托方：用户 · 执行：Trae（GitHub 线，仓库 fe1iscurc0r/scratchpad）· 出单：沈遥 · 日期：2026-10-08
> 背景：memory_maas SPEC 已落地（claude-mem 授粉），但记忆层的"portable/local-first"新范式在 2026-Q4 有三家高星新选手，与陆墨的记忆栈（五维记忆融合 SPEC-05 + NEKO 记忆）方向对口。本单做第二梯队调研，与工单 209 任务三（cognee/MemOS 调研卡）合编一个目录。

## 任务一（P0）：三份调研卡（调研级，不动手）

GitHub 实测 2026-10-08（全部真实、近期活跃、与已有 63+ 份授粉报告零重复）：

| 候选 | ★ | 许可 | 最近推送 | 卖点 |
|---|---|---|---|---|
| EverMind-AI/EverOS | 13359 | Apache-2.0 | 10-06 | **可移植记忆层**：local-first + Markdown 原生，跨 agent 共享 |
| tigerless-labs/agent-memory | 2381 | MIT | 10-07 | **纯 Markdown 记忆运行时**——与 Hermes 自身 memory 机制同构，最易对读 |
| u14app/neo-chat | 1865 | MIT | 10-01 | local-first 聊天工作区（models/agents/skills/plugins 集成面） |

1. 每家落调研卡 `docs/fusion-candidates-2026-10/`（与工单 209 任务三同目录）：
   - 架构一句话 / 记忆数据格式 / 与 memory_maas + SPEC-05 五维记忆的差距 / 可借用设计（非代码）/ 优先级
2. **重点问题**（EverOS 卡必答）："portable memory layer" 的跨 agent 协议是怎么设计的——若它定义了记忆交换格式，评估陆墨（apiserver 记忆）↔ Hermes（本地 memory）↔ NEKO（facts.py）三方互通借这套格式的可行性
3. tigerless 卡重点：Markdown-as-source-of-truth 的冲突解决/增量同步机制，对照 Hermes memory 的注入式设计
4. 许可红线照旧：NOASSERTION（TencentDB-Agent-Memory ★27781 但无许可声明）**只看不融**，调研卡里注明原因即可，不出卡

## 任务二（P1）：三方记忆互通预研——格式对齐表

陆墨生态有三套记忆在跑：apiserver 记忆（SPEC-05）、NEKO facts.py、Hermes 本地 memory。EverOS 若提供交换格式，是统一的窗口。

1. 产出 `docs/memory-interop-prestudy.md`（**预研，不实现**）：
   - 三方现状表：存储格式（JSON/SQLite/Markdown）/ 读写入口 / 生命周期（写入时机/淘汰机制）
   - 若对齐到 Markdown 交换格式：各自的转换损耗在哪、哪些字段会丢
   - 结论三选一：直接采用外部格式 / 自定义最小子集 / 维持现状各管各的（给理由）
2. 此预研是 SPEC-05（五维记忆融合）的续篇素材，文内注明承接关系

## 验收
- [ ] 任务一：三份调研卡落盘 fusion-candidates-2026-10/，每份含许可标注+差距+可借设计；EverOS 卡必答跨 agent 协议问题
- [ ] 任务二：memory-interop-prestudy.md 含三方现状表 + 转换损耗分析 + 三选一结论；标注承接 SPEC-05
- [ ] 全程 CI 绿（lint/smoke 若闸门未开则本地等价复现，参照 ci.yml 注释的两步法）
