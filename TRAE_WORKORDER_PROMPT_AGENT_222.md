# 工单 222 · 并发与锁安全审计——共享可变状态全图 + 六处嫌疑点实测

> 委托方：用户 · 执行：Trae（GitHub 线，仓库 fe1iscurc0r/scratchpad）· 出单：沈遥 · 日期：2026-10-08
> 背景：用户问"线程并发锁考虑了吗"。沈遥初勘结论：**基础面合格，但有三处明枪三处暗哨**。本单做全仓共享可变状态的系统性审计。

## 初勘实况（grep 实证）

**已做对的**（61 处 Lock 使用，架构有意识）：
- ✅ config 写入原子性：tempfile + os.replace（config_manager.py:317-324，防写一半崩溃截断）
- ✅ SQLite：热点库开 WAL（llm_router/subagent）；迁移期刻意不开 WAL 且注释了实测原因（Windows 边车文件争抢）——**有实验依据的决策**
- ✅ Playwright 单线程隔离：MatChat executor max_workers=1（对象绑定创建线程，注释明确）
- ✅ token 刷新 asyncio.Lock（naga_auth）、event_store/bridge/tool_gate 各自 threading.Lock
- ✅ subagent 并发有 Semaphore 限流

**六处嫌疑**（按危险排序）：

| # | 嫌疑 | 证据 | 危险 |
|---|---|---|---|
| 1 | **config 并发写竞态**：原子 rename 只防崩溃不防并发——两个通道同时 `update_config`，后写覆盖前写（lost update）；rename 本身原子但**读-改-写三步不原子** | config_manager 无进程内锁；routes/system.py:255 直接调 | 🔴 数据丢 |
| 2 | **模块级 global 单例无锁**：10 处 `global _xxx`（intent_router 缓存/local_embedder/llm_service/loop_checkpoint 等）——首次并发初始化可能双建 | grep 实证 10 处 | 🟡 浪费/状态分裂 |
| 3 | **device_state._store global**：设备状态字典并发读写无锁保护迹象 | device_state.py:138 | 🟡 视访问模式 |
| 4 | config.py 内**另一条写路径**（:223 直接 json.dump 进 open(target,"w")，非原子、无锁）与 config_manager 原子路径并存——双写入口标准不一 | config.py:223 vs config_manager.py:320 | 🔴 标准分裂 |
| 5 | **threading vs asyncio 锁混用**：telemetry 同时有两种锁（:148 asyncio / :494 threading）——若同一数据被两种上下文访问，任一锁都形同虚设 | telemetry.py | 🟡 需核对保护对象 |
| 6 | **跨进程写入**：云服三端（weixin/qqbot/cli）共享 scratchpad 工作树是 git 层已知问题（有 skill），但 **runtime 数据目录**（user_data/event_store/audit）是否也有多进程写——apiserver 与 agentserver 两个进程各写各的还是共享 | 架构问题 | 🟡 需实测 |

## 任务一（P0）：嫌疑点逐个实测

1. **config 竞态复现**（嫌疑1）：写脚本并发 20 线程同时 update_config 不同字段 → 检查最终文件是否丢更新。复现 = P0 实锤
2. **global 单例双建检测**（嫌疑2）：对 10 处 global 加临时探针或在并发测试中检查对象 id 一致性
3. **双写入口对齐检查**（嫌疑4）：config.py:223 的直接 dump 路径是否可达（谁调用）——若死代码直接标记删除候选
4. **telemetry 双锁**（嫌疑5）：核对两把锁各保护什么数据，是否同一数据被跨上下文访问
5. **跨进程写实测**（嫌疑6）：起 apiserver + agentserver 双进程，观察 event_store/audit 文件是否交错写入（ flock 需求判定）
6. 产出 `docs/concurrency-audit-2026-10.md`：每嫌疑 = 复现方法/结果/伤害分级/修法

## 任务二（P0 若实锤）：config 读写锁 + 单写入口

若嫌疑 1/4 实锤（大概率）：
1. config_manager 加进程内 `threading.Lock` 包住读-改-写全区间（三通道都在同进程内，进程内锁够用）
2. config.py:223 死路径删除或改走 config_manager 统一入口——**一仓一个写 config 的门**
3. 跨进程场景（若嫌疑 6 实锤有双进程写 config）：加文件锁（fcntl/portalocker）或声明"config 单进程写"架构约束并写进 AGENTS.md

## 任务三（P1）：global 单例统一惰性锁模式

1. 10 处 global 单例统一成同一个模式（如 `@functools.lru_cache` 或显式 check-lock-check），新代码有样板可抄
2. 改动只加锁不改语义；每处配一个并发冒烟断言（双线程同时首调 → 同一实例）

## 验收
- [ ] 任务一：六嫌疑全部实测复现/排除，报告含复现命令与结果数据（不接受纯代码推断）
- [ ] 任务二：若实锤——锁落地+并发压测（20 线程×50 次读写零丢失）；单写入口收口
- [ ] 任务三：10 处单例统一模式，并发冒烟断言全绿
- [ ] 全程 CI 绿
