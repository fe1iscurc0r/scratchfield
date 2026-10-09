# 工单 220 · 全仓架构健康四线优化——启动性能 / 配置收敛 / 孤儿模块 / 文档热度

> 委托方：用户 · 执行：Trae（GitHub 线，仓库 fe1iscurc0r/scratchpad）· 出单：沈遥 · 日期：2026-10-08
> 背景：用户问"其他领域/功能/内容/架构还有什么可优化"。沈遥以系统架构师视角做了全仓体检，避开已出单的线（巨石拆分 209 / 协议审计 216 / EDA 三连 217-219），扫出四条**没人管过**的结构性优化线。全部先测后动。

## 任务一（P0）：启动性能基线——冷启动解剖

已有线索：卷191-B3 打过启动计时点（模块加载+lifespan），但**没有基线档案**。

1. 跑三次冷启动（清 pycache），记录分解耗时：
   - 模块导入段（python -X importtime apiserver/start_server.py 输出解析，Top20 慢模块表）
   - lifespan 内各初始化步骤（索引/适配器注册/事件总线 attach）逐段计时
2. 产出 `docs/cold-start-baseline-2026-10.md`：基线数字 + Top 慢点清单 + **懒加载候选表**（哪些导入可延迟到首次调用——重点盘 mcpserver 36 个 adapter 的注册时机，现在是否全量 import）
3. 若 Top1 慢点可安全懒加载且收益 >500ms，给 patch 方案（本单不实施，除非改动 ≤20 行且零行为变化）

## 任务二（P1）：config.json 单例收敛设计

`system/config.py` 2042 行已被工单 209 列为头号巨石，但 209 管拆文件，本任务管**运行时语义**：

1. 盘点 config 读写点：`get_config()/save_config()` 全仓调用图（谁读、谁写、频率），产出调用矩阵
2. 检查三个已知风险：
   - 读写竞态：多路由并发 save 是否有锁？（websocket/qq/weixin 三通道并行时）
   - 热更新：改配置是否需要重启？哪些字段事实上支持热更
   - schema 漂移：config.json 老版本字段升级路径（storageMigration.ts 前端有，后端有没有）
3. 产出 `docs/config-runtime-audit.md`：矩阵 + 三风险结论 + 修复优先级（若竞态实锤标 P0 级隐患）

## 任务三（P1）：孤儿模块甄别——carpet/rag/characters 三目录

`carpet/`（24MB，含 N.E.K.O 子目录——与顶层 NEKO/ 900MB 疑似重复）、`rag/`（7.2MB 独立解析器套件）、`characters/`（20MB 角色资源）——三个目录的归属与存活状态未盘：

1. 逐目录查引用：`grep -rn 'from carpet\|import carpet\|from rag\|import rag'` 全仓调用图；前端/构建脚本对 characters/ 的引用
2. carpet/N.E.K.O 与顶层 NEKO/ 做 diff 判定（同一份的两副本？旧快照？）——若为死副本，列删除候选清单（**不删**，列清单交用户拍板）
3. rag/ 与 mcpserver 内 RAG 组件（lightrag_graph 等）的关系：并行两套还是新旧接替
4. 产出 `docs/orphan-modules-audit.md`：三目录判定表 + 处置建议（保留/合并/删除候选）

## 任务四（P2）：文档热度分析——19MB docs/ 的活性分层

docs/ 1300+ 文件，三轮 SPEC 清理（工单 212）管的是命名归档，本任务管**内容活性**：

1. 用 git log 统计 docs/ 每文件最近修改时间 + 被引用次数（其他文件内 grep 链接/路径引用）
2. 分四层：活跃（30 天内有改）/ 温（90 天）/ 冷（仅历史价值）/ 死链（无任何引用）
3. 冷层+死链列清单进 orphan 报告任务三同文档；**重点找"冷但被工单/SPEC 引用"的矛盾文件**——引用活文档的工单才有效

## 验收
- [ ] 任务一：冷启动基线三次数值 + importtime Top20 + 懒加载候选表；≤20 行零行为变化的 patch 可顺手做
- [ ] 任务二：config 调用矩阵 + 竞态/热更/漂移三结论（竞态若实锤标 P0）
- [ ] 任务三：三目录判定表，删除候选只列不删；rag 双套关系明确
- [ ] 任务四：四层活性分层 + 矛盾文件清单（并入 orphan 报告）
- [ ] 全程 CI 绿
