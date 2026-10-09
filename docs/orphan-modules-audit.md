# config 运行时审计 + 孤儿模块甄别 + 文档活性（工单220 任务二/三/四）

> 日期：2026-10-08 ｜ 全部基于 grep 调用图 / git 跟踪状态 / 逐字节 hash 等实测。

---

## 任务二 · config 运行时审计

### 调用矩阵（谁读、谁写）

| 面 | 读 | 写 |
|---|---|---|
| 路由层 | 全部路由经 `get_config()`（内存缓存） | `routes/system.py:255`（设置保存）、`naga_control.py:107/192/238`、`naga_auth.py:508`、`routes/auth.py:309` |
| 写机制 | — | **全部收口 `config_manager.update_config`**（工单222 后：`_CONFIG_RMW_LOCK` RLock + `atomic_write_json`） |

### 三风险结论

| 风险 | 结论 | 证据 |
|---|---|---|
| **读写竞态** | ✅ **已修复**（工单222，2026-10-08） | RLock 包读-改-写全程；压测 1000 写零丢失；Windows `os.replace` 退避重试 |
| **热更新** | 🟡 部分 | `update_config` 尾部调 `hot_reload_config()`（锁外）——llm 参数等**部分字段热更**；端口/开关类需重启（启动期读一次）。**无"哪些字段热更"的显式清单**（候选小单：字段级 hot/cold 标注） |
| **schema 漂移** | 🟡 后端有路径但薄 | `CONFIG_SCHEMA_VERSION` 存在 + `config_manager` 有迁移写回（RLock 测试里的 nested save 即此）；对比前端 `storageMigration.ts` 成体系的版本迁移，后端**没有等价的逐版本迁移表**——字段级漂移靠 pydantic 默认值兜底（新增字段安全，删改字段静默丢） |

**修复优先级**：竞态已闭环；热更清单 P2；schema 迁移表 P2（config.py 拆分时一起做，见工单209）。

## 任务三 · 孤儿模块甄别（三目录判定表）

| 目录 | 大小 | git 跟踪 | import 引用 | **判定** | 依据 |
|---|---|---|---|---|---|
| `carpet/` | 82MB | 45 文件 | **0**（业务代码零引用） | 🟡 **NEKO 运行时数据目录**（非代码孤儿） | `carpet/N.E.K.O/` **无 main_routers**（源码特征缺失）——内容是 vrm 动画 55MB / logs 26MB / memory / plugins.lock：**这是 NEKO 的 data 目录被命名成 N.E.K.O**，工单"与顶层 NEKO 疑似重复"**不成立**（非源码副本） |
| `rag/` | 8MB | 10 文件 | **30 处**（api_server/local_embedder/routes/rag 惰性导入） | ✅ **存活核心**（不是孤儿） | 与 mcpserver 内 RAG 是**分工不是重复**：`rag/` = apiserver 的嵌入/索引引擎（vault_indexer/embedding_engine）；lightrag = 知识图谱侧。两套并存有据 |
| `characters/` | 20MB | 57 文件 | 路由引用 4 处（`/characters/` 静态路径 + live2d 模型 URL） | ✅ **存活**（Live2D 资源目录） | `routes/system.py` 直接拼 `/characters/<name>/<model>` URL 服务模型文件 |

**处置建议**：
- `carpet/`：**保留**（运行时数据），但 ⭐ 建议**改名或移出仓库跟踪**——45 个跟踪文件里 26MB logs 类产物混进 git 不干净；候选动作：`git rm -r --cached carpet/N.E.K.O/logs` 级清理（列清单交用户拍板，本单不动）；
- `rag/` `characters/`：保留，无需动作。

**删除候选清单：无**（三目录都不是死副本）。

## 任务四 · docs/ 活性分层（并入本报告，抽样口径）

方法：git log 最近修改时间 + grep 交叉引用计数（docs 内 1300+ 文件全量跑，耗时可控的
**引用计数用文件名 grep 近似**）。

| 层 | 判定 | 数量（约） | 代表 |
|---|---|---|---|
| 活跃（30 天内改） | git log | ~120 | 本月工单产出（monolith-audit、ros-ecosystem 等） |
| 温（90 天） | git log | ~200 | 8 月 SPEC 批 |
| 冷（>90 天） | git log | ~900 | 授粉报告/评估历史 |
| 死链（零引用） | grep 文件名 | ~340 | 大量一次性日报/digest |

⭐ **"冷但被 SPEC/工单引用"的矛盾文件**（重点找的）：

| 文件 | 状态 | 矛盾点 |
|---|---|---|
| `docs/cognee-图记忆-评估.md` | 冷（8 月底） | 被**今天的** fusion 调研卡引用（工单214 增量基座）→ **不算死**，标"活性借调" |
| `docs/HW-06B-report.md` | 冷 | 工单218 引用（30 仓清单唯一来源）→ 同上，**关键依赖文档** |
| `SPEC-02-report.md` / `SPEC-03-report.md` | 冷 | SPEC-INDEX（工单212）锚定关联 → 活性来自索引页 |

**结论**：docs/ 的"冷"不等于"死"——**引用图比时间更重要**；工单212 的归档结构 + 本报告的引用判定已够用，不需要再清理动作。340 个零引用文件**不动**（历史价值判定需人工逐个看，收益低）。

---

## 边界

- 竞态结论引用工单222（今天已修），未重复压测；
- 热更字段清单与 schema 迁移表为候选单，本单不动 config.py（归 209 管辖）；
- 文档活性引用计数是 grep 文件名近似（不解析 markdown 链接语法）。
