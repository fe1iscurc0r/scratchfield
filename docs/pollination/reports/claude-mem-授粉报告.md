# claude-mem 授粉报告

> 2026-08-29 · 来源：thedotmack/claude-mem（Apache-2.0，92522★，明确支持 Hermes）
> 勘察：src/services/domain/types.ts · src/services/sqlite/observations/{store,get,files}.ts · SessionStore(3248行) · SessionSearch(615行) · CLAUDE.md
> 定位：跨 session 持久记忆压缩系统（Claude Code 插件）——**压缩+注入**工作流，非实体图谱路线

## 一句话

claude-mem 解决的是"session 之间怎么不重头开始"：hook 捕获工具调用观察 → LLM 压缩成结构化块 → 新 session 按需注入。跟 par（typed 实体）是互补路线，两者都值得收进 memory_maas。

## 核心架构（3 层）

1. **捕获层（hooks）**：PreToolUse/PostToolUse 记录 observation（files_read / files_modified / project / platform_source），**sha256 内容哈希去重**（`computeObservationContentHash(memorySessionId, title, narrative)` → 16位hex），相同观察不重复入库。
2. **压缩层**：LLM 把 session 压缩成 XML 结构块（title/fact/narrative/concept 占位符 + summary checkpoint：investigated/learned/completed/next_steps/notes），ModeConfig 驱动全套提示模板。
3. **注入层（MCP 3层工作流）**：新 session 启动时按（project + 关键词 + 文件路径）检索，默认 limit 15、上限 100，token 高效——先少量精确注入，再按需深入。

## 可授粉点

| # | 点 | 来源 | 流向 | 价值 |
|---|-----|------|------|------|
| 1 | 内容哈希去重 | observations/store.ts | memory_maas v2 捕获层 | 防重复观察，零成本幂等 |
| 2 | 压缩块 XML 模板 | domain/types.ts ModePrompts | memory_maas consolidation | LLM 蒸馏输出结构标准化（比 par 自由文本更可解析） |
| 3 | 多路径匹配 | get.ts #2691 | memory_maas 注入检索 | PreToolUse/PostToolUse 路径形式不一致坑：注入检索必须同时匹配绝对/相对/项目根三种路径形式 |
| 4 | ModeConfig 模板驱动 | domain/types.ts | NEKO 角色配置 | 记忆观察类型+提示模板整体配置化，角色卡可切换 |
| 5 | platform_source 归一化 | shared/platform-source | 多端共享记忆 | weixin/qqbot/cli 三端来源打标（记忆 provenance 的天然来源字段） |
| 6 | 心跳 15min | CLAUDE.md | memory_maas P2 | 与 par 心跳参数一致，统一 |

## 差距清单

- claude-mem 无 typed 实体/KG（路线不同，不补它，由 par 线补）
- 压缩依赖 Claude Agent SDK（vendor lock）——我们照搬"压缩+注入"设计，但实现走自家 LLM 栈（DeepSeek/MiniMax），不依赖 Claude SDK
- 数据全在 SQLite（bun:sqlite），我们沿用五件套标准库 sqlite3，不引 bun

## 落地建议

- P0：**内容哈希去重** 进 memory_maas v2 捕获层（一行函数移植，零依赖）
- P0：**多路径匹配** 进注入检索实现（防踩 #2691 同类坑）
- P1：压缩块 XML 模板 进 consolidation 输出规范
- 不 clone 运行时、不依赖 Claude SDK，只收设计。

## 反封禁备注（用户问过）

Anthropic 4/4 封的是第三方 harness 蹭 Claude 订阅计费，不是记忆插件；claude-mem 仍在官方插件市场、8月仍有 commit。我们只读 Apache-2.0 源码抄设计，零风险。
