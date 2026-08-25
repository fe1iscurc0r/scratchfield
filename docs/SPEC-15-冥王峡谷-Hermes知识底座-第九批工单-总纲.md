# SPEC-15 冥王峡谷 Hermes 知识底座 · 第九批工单总纲 · v1

> 状态：待施工（2026-08-25 用户拍板：冥王峡谷主系统 = Hermes，NagaAgent/llama.cpp 方案搁置）
> 用途：冥王峡谷（NUC8i7HVK, i7-8809G + Vega M GH, 16GB RAM, 512GB NVMe, Kali 主力）给林楠（Hermes profile `~/.hermes/profiles/linnan/`）添砖加瓦——数据库 + 知识库 + Obsidian 底座
> 读者：Trae / WorkBuddy / 沈遥
> 依据：SPEC-14（本 SPEC 修正其方向）；skill: linnan-onboarding；2026-08-24/25 微信会话结论

## 〇、方向修正（用户拍板 2026-08-25）

- ❌ **搁置**：SPEC-14 的 NagaAgent 寄生层 5 服务 + llama.cpp 本地 LLM——不为它们预留内存
- ✅ **主系统**：Hermes 直接跑（林楠 profile 即 Hermes 形态），给 Hermes 加底座
- 16GB 内存全给 Hermes 生态 + Obsidian + 嵌入式数据库，不做本地 LLM 常驻服务

## 一、底座架构

```
┌─ 知识库前端 ───────────────────────┐
│ Obsidian vault ~/kb/              │  Kali GUI 编辑，--disable-gpu 防 Vega M GH 崩
└──────────────┬────────────────────┘
               │ markdown
┌─ 知识库层 ────────────────────────┐
│ kaas (MIT, bybit) 编译 wiki       │  docs/ + vault → 可查询 wiki，systemd timer 增量
│ LanceDB 向量索引                  │  vault/docs → chunk → embedding → 检索
└──────────────┬────────────────────┘
               │ Hermes 工具/MCP
┌─ 记忆层 ──────────────────────────┐
│ Sibyl-Memory (MIT, SQLite+FTS5)  │  五层分级 schema，sibyl-memory-hermes 适配包
│ 迁移桥：linnan JSON → Sibyl      │  T-01 交付，只读源不破坏原 JSON
└──────────────┬────────────────────┘
┌─ 存储层 ──────────────────────────┐
│ SQLite + FTS5（已有）             │  采集/事实/事件主存储
│ 512GB NVMe → /data 数据盘         │  kb / kb_index / kb_wiki / memory 分目录
└───────────────────────────────────┘
```

**扩展原则**：全部嵌入式、零常驻守护进程；新组件 = 新 venv 依赖 + 按需 CLI/工具，不跑 HTTP 服务（除非必要）。

## 二、组件选型

| 组件 | 来源 | 许可 | 内存 | 用途 |
|---|---|---|---|---|
| SQLite + FTS5 | 系统已有 | 公有 | ~0 | 主存储/全文检索 |
| LanceDB | PyPI `lancedb` | Apache-2.0 | 按需 | 向量 RAG |
| Sibyl-Memory | PyPI `sibyl-memory-hermes` | MIT | 按需 | 林楠记忆层升级 |
| kaas | GitHub bybit-exchange/kaas | MIT | 编译时 | Markdown → wiki |
| Obsidian | AppImage（Kali） | 免费/私有 | GUI 时 | 知识库前端 |

嵌入模型：sentence-transformers 小模型（默认 all-MiniLM-L6-v2，~80MB，CPU 可跑），非 LLM 服务，与"不做本地 LLM"不冲突。

## 三、工单概览（第九批 · T 线）

| 工单 | 内容 | 类型 |
|---|---|---|
| T-01 | Sibyl-Memory 记忆迁移桥（JSON → 五层 schema） | 写码 |
| T-02 | kaas 知识库编译流水线（增量 + timer） | 写码 |
| T-03 | LanceDB 检索工具封装（ingest + kb_search，Hermes 工具注册） | 写码 |
| T-04 | 冥王峡谷部署包（Obsidian/vault/venv/systemd/verify 脚本） | 文档+脚本 |

详见 `TRAE_WORKORDER_PROMPT_AGENT_T.md`（含每单目标/输入/动作/验收/硬约束）。

## 四、验收（部署后真机清单）

1. 记忆迁移：`sibyl_migrate.py --dry-run` 出映射对照，`--apply` 后三类（事实/事件/状态）可查
2. 知识库：`kb_build.py` 增量编译产出 wiki 索引，grep 命中
3. 检索：`kb_search "关键词"` 返回 vault 相关片段
4. Obsidian：`--disable-gpu` 启动打开 ~/kb 不崩
5. systemd timers：kb-build / kb-backup active
6. `verify_hermes_kb.sh` 全部 PASS

## 五、提交规范

- SPEC 与工单进 scratchpad 仓库 main（Trae 拉取用），施工产物走 `trae/agent-t` 分支
- 真机部署执行留林楠侧（Kali），沈遥只出部署提示词与验收标准
- 施工中发现假设不成立 → 回填本 SPEC，不绕过硬干

---

*制定：沈遥（Hermes）· 2026-08-25*
*依据：SPEC-Writing-Standard-v2 + linnan-onboarding + 8-24/25 会话结论*
