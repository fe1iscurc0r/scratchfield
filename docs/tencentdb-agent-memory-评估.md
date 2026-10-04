# W68-02 TencentDB-Agent-Memory 评估（团队记忆中心）

> 上游：github.com/TencentCloud/TencentDB-Agent-Memory · 许可 MIT（API 误标 NOASSERTION，LICENSE 文本实为 MIT）· 25659★ · TypeScript · 2026-08-31 活跃
> 落点：docs/tencentdb-agent-memory-评估.md · 勘察/评估

## 1. 项目定位

团队级 Agent 记忆中心：把对话、文档、代码转成**可复用的四类记忆**（自动抽取实体/关系），面向「一人公司的增长型 Agent 团队」提供跨会话、跨 Agent 的共享记忆服务。

## 2. 架构拆解

- **三服务**：`memory-core`（记忆核心）+ `memory-hub`（记忆中心面板，localhost:8125）+ `proxy`（接入 Claude Code / CodeBuddy 的代理）。
- **一键部署**：`start-all.sh` 起三服务，输出一行可直接贴进 Claude 的接入配置。
- **迁移工具**：v2→v3 数据迁移。
- **定位**：把记忆从「单 Agent 私有」升级为「团队共享的中心化记忆」，覆盖记忆分片与跨会话 recall。

## 3. 与本仓对照

| 维度 | TencentDB-Agent-Memory | 本仓 |
|---|---|---|
| 记忆粒度 | 四类复用记忆 + 团队分片 | memory_maas / NEKO 记忆五件套 / summer_memory 五元组 |
| 形态 | 中心化服务（core+hub+proxy） | 模块化（mcpserver 内） |
| 跨会话 | 团队级共享 recall | 以单 Agent 记忆为主 |

## 4. 可落地借鉴点（≥3）

1. **「core + hub + proxy」三层解耦**：记忆核心 / 可视化面板 / 模型接入代理分离，比我们把记忆、面板、接入揉在一起更清晰，可参考拆分 memory_maas。
2. **四类记忆的显式分类**：把「对话/文档/代码」统一抽象为四类可复用记忆，可作为我们五元组的补充维度。
3. **一键接入的一行配置**：面向 Claude Code 的即插即用接入方式，可参考降低我们记忆服务的接入门槛。

## 5. 许可裁定 + 结论

- **许可**：LICENSE 文本实为 MIT（API 误标 NOASSERTION，README badge 一致标 MIT）→ **MIT，可借鉴代码**。
- **不重复造轮子判断**：我们已有记忆五件套（memory_maas + NEKO 五件套 + summer_memory），功能重叠度高。**结论：不迁入，参考「三层解耦 + 四类记忆分类」设计即可**；若后续要团队级记忆，优先在现有五件套上加共享层，而非引入新服务。
