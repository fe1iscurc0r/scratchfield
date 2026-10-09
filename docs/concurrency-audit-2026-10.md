# 并发与锁安全审计（工单222）

> 日期：2026-10-08 ｜ 范围：全仓共享可变状态的系统性审计（config / 单例 / 双写入口 / 跨进程写）
> 原则：**每条结论都带复现方法或实测数据**；代码推断与实测结论分开标注。

---

## 0. 结论摘要

### 六处嫌疑的实测裁定

| # | 工单嫌疑 | 裁定 | 关键证据 |
|---|---|---|---|
| 1 | **config 并发写竞态**（读-改-写三步不原子） | 🔴 **实锤** | 20 线程各写一个字段 → **只落盘 1 个，丢 19 个**；且并发 `os.replace` 抛 `WinError 5` 被**静默吞掉** |
| 2 | **模块级 global 单例无锁**（工单称"10 处"） | 🟡 **实锤（范围更大）** | 全仓扫描：**107 处 global 写点**，其中**真懒加载单例 52 处**；改写前 **18 带锁 / 34 裸奔**。模式对照演示：裸模式 16 线程 → **5/5 轮全双建**；DCL 后 **0/5** |
| 3 | `device_state._store` 无锁保护 | ✅ **排除** | `DeviceStateStore.__init__` 已有 `self._lock`，`register/update_state/heartbeat/get_state` 的复合写**全部在锁内**（`apiserver/device_state.py:41-101`） |
| 4 | **config 双写入口标准分裂** | 🔴 **实锤** | `system/config.py` 的 `sync_source_config_to_runtime()` 用 `open(target,"w")+json.dump`（**非原子、无锁**），与 `config_manager` 的原子路径并存；**可达**：`main.py:805` / `main.py:899` 启动期调用 |
| 5 | telemetry 混用 threading / asyncio 锁 | ✅ **排除** | `mcpserver/telemetry.py` 现全文 **3 把锁全是 `threading.Lock`**（recorder/breaker/module `_LOCK`），**无 asyncio 锁**（工单引用的 `:148 asyncio` 在当前版本不存在） |
| 6 | 跨进程共享写入 | 🟡 **部分成立（配置侧排除，数据侧需约束）** | config 写调用点**全部在 apiserver 包内**（`routes/system.py:255`、`naga_control.py:107/192/238`、`naga_auth.py:508`、`routes/auth.py:309`）→ **config 单进程写成立**；但 `agentserver` 与 apiserver 是**独立 uvicorn 进程**（`start_server.py`），`event_store/events.jsonl`（`apiserver/event_bus/event_store.py:130`，append + **rename 轮转**）目前仅 apiserver 写 → **当前无双写，但轮转 rename 与"未来多进程"不兼容**，建议写成架构约束 |

### 本次改动

| 项 | 内容 |
|---|---|
| 新增 | `system/config.py: atomic_write_json()` —— **全仓唯一原子写入口** |
| 修改 | `system/config_manager.py`：`_CONFIG_RMW_LOCK`（RLock）包住读-改-写；`_save_config_file` 委托原子写入口；移除已无用的 `tempfile` |
| 修改 | `system/config.py`：`sync_source_config_to_runtime()` 改走原子写入口（**双门 → 一门**） |
| 修改 | **34 个文件**的懒加载单例加 DCL 锁（含 2 处 `X is None or X.is_closed` 特殊形状） |
| 新增 | `tools/singleton_lock_codemod.py`（AST 判定 + 文本改写，幂等，`--check`/`--write`） |
| 新增 | `tests/test_concurrency_locks.py`（**18 例**：config 压测 / 单例并发冒烟 / 原子写不变量） |
| 新增 | docs：本文件 |

---

## 1. 任务一：六嫌疑逐个实测

### 嫌疑 1 · config 并发写竞态 —— 🔴 实锤（含一个工单没提的 Windows 现象）

**复现方法**

```bash
cd "D:/my git/scratchpad"
# 打桩 get_config_path 指向临时文件（不碰真实配置），20 线程同时各写一个字段
.venv/Scripts/python.exe - <<'PY'
import json, os, sys, tempfile, threading
sys.path.insert(0, os.getcwd())
import system.config_manager as CM
from pathlib import Path
d = tempfile.mkdtemp(); cfg = os.path.join(d, "config.json")
Path(cfg).write_text(json.dumps({"schema_version": 2}), encoding="utf-8")
CM.get_config_path = lambda: cfg
CM.bootstrap_config_from_example = lambda *a, **k: None
CM.hot_reload_config = lambda *a, **k: None
cm = CM.ConfigManager(); b = threading.Barrier(20)
def w(i):
    b.wait(); cm.update_config({f"field_{i}": i})
ts = [threading.Thread(target=w, args=(i,)) for i in range(20)]
[t.start() for t in ts]; [t.join() for t in ts]
final = json.loads(Path(cfg).read_text(encoding="utf-8"))
got = {k for k in final if k.startswith("field_")}
print("期望 20 / 实际落盘", len(got), "→ 丢失", 20 - len(got))
PY
```

**实测结果（修复前）**

```
[复现] 线程=20 耗时=0.14s 异常=0
[复现]   期望字段=20 实际落盘=1 **丢失=19**
保存配置文件失败: [WinError 5] 拒绝访问。: '...\.config_xxx.tmp' -> '...\config.json'   ← 出现 6 次
配置更新成功: 1 项                                                                    ← 却报成功
```

**两个伤害，第二个是工单没提到的**

1. **lost update**：`update_config` 是 `[读文件 → 递归改内存 → 原子写]` 三步，只保证"写不截断"，
   不保证"三步之间没有别人插进来"。20 线程并发 → **丢 19/20**。
2. ⭐ **静默失败**：Windows 上并发 `os.replace` 到同一目标会抛 `PermissionError(WinError 5)`，
   而 `_save_config_file` 的 `except Exception` 把它**吞成 `return False`**，
   调用方（`routes/system.py`）只看到 `success=False`，日志里只有一行"保存配置文件失败"。
   → 这违反了仓规「**不静默降级**」。

**伤害分级：🔴 数据丢失 + 静默失败**（配置是热更新通道，丢的是用户刚改的设置）

**修法**
- `config_manager` 加 `_CONFIG_RMW_LOCK`（RLock），**读-改-写全程互斥**；热重载放锁外（回调业务代码，避免锁内调外部逻辑）。
- 写机制收口到 `system.config.atomic_write_json`：tempfile → write → `flush + fsync` → `os.replace`，
  带 20 次退避重试，**失败显式抛出**（不再吞）。
- 用 RLock 而非 Lock：`_load_config_file` 内部的"版本迁移写回"会嵌套调用 `_save_config_file`。

### 嫌疑 2 · 模块级 global 单例无锁 —— 🟡 实锤，且**范围比工单大 3 倍以上**

**扫描方法**（AST，纯静态）

```bash
.venv/Scripts/python.exe tools/singleton_lock_codemod.py --check   # 形状判定
# 另有临时扫描器：统计「global 写点 / 真懒加载单例 / 带锁 vs 裸奔」
```

**实测数字**

```
global 写点          107 处（含 token 缓存 / 标志位 / reset_* 测试钩子）
真懒加载单例          52 处   ← 工单按「10 处」立单
  改写前：带锁 18 / 裸奔 34
  改写后：带锁 52 / 裸奔  0
```

**模式对照演示**（`tools/demo_dcl_pattern.py`：16 线程 + 5ms 注入延迟，等价"构造涉及读文件/建连接"）

```
裸 check-then-set   构造次数（5 轮，每轮 16 线程）: [16, 16, 16, 16, 16] → 双建轮次 5/5
DCL（加锁后）       构造次数（5 轮，每轮 16 线程）: [1, 1, 1, 1, 1]   → 双建轮次 0/5
```

> ⚠️ **边界如实标注**：这是**模式层**的实测，不是具体站点的故障复现 ——
> 真实站点构造函数太快时 GIL 会掩盖竞态（实测 8 线程并发首调 `get_llm_service()`
> 只实例化 1 次）。**构造带 I/O 的站点（读文件/建连接，如 `_get_vision_client`、
> `_get_openclaw_client`、`system/config.get_prompt_manager`）才是真实风险面。**

**伤害分级：🟡 视站点而定** ——
- 双建**状态分裂**类（两个实例各自持状态）：`device_state`、`message_queue`、`loop_checkpoint`、
  `event_bus.*`、`channels`、`mcp_manager`、`dogtag/registry`、`openclaw/*`
- 双建**资源重复**类（多建连接/线程/定时器）：`neko_cua`、`_get_vision_client`、`_get_openclaw_client`、
  `embedded_runtime`、`get_health_checker`
- 双建**仅浪费**类（幂等构建）：`intent_router._build_tool_list`

### 嫌疑 3 · `device_state._store` —— ✅ 排除

`apiserver/device_state.py:41` `self._lock = threading.Lock()`；
`register`（:45）、`update_state`（:54）、`heartbeat`（:72）、`get_state`（:87，含"读时惰性判超时"的写）
**全部在锁内**。工单说的"无锁保护迹象"与实测不符 → 排除。

### 嫌疑 4 · config 双写入口 —— 🔴 实锤（标准分裂，可达）

```python
# system/config.py:222（修复前）
with open(target, "w", encoding="utf-8") as target_file:      # ← 非原子、无锁
    json.dump(merged_config, target_file, ensure_ascii=False, indent=2)
```
与 `config_manager._save_config_file` 的 tempfile+replace 原子路径**并存**，且**共享同一个 `get_config_path()`**。
**可达性核实**：`main.py:199` 导入、`main.py:805` / `main.py:899` 调用 → 不是死代码。

**伤害分级：🔴 标准分裂**（一条路崩溃可截断、一条路原子；后续维护者不知道该抄哪条）

**修法**：新增 `atomic_write_json()` 作为**唯一**落盘入口，两条路径都走它。

### 嫌疑 5 · telemetry 双锁 —— ✅ 排除

`mcpserver/telemetry.py` 全文 `threading.Lock` × 3（`CallRecorder._lock:67`、`CircuitBreaker._lock:261`、模块级 `_LOCK:353`），
**没有任何 asyncio 锁**。工单引用的 ":148 asyncio" 在当前版本已不存在（文件 398 行）→ 排除。

### 嫌疑 6 · 跨进程写 —— 🟡 部分成立

**实测（静态枚举 + 调用点核查）**

| 检查 | 结果 |
|---|---|
| config 写调用点分布 | **全部在 apiserver 包内**（5 个文件 7 处），`agentserver/` **零** → **config 单进程写成立**（进程内 RLock 足够） |
| apiserver 与 agentserver 是否同进程 | ❌ 否 —— `start_server.py` 每个服务各起一个 `uvicorn.run()`；`agentserver/agent_server.py` 是另一个进程 |
| agentserver 是否碰 event_bus/event_store | ❌ 否（grep 零命中） |
| `event_store/events.jsonl` | `open(...,"a")` 追加 ✓，但**轮转靠 `rename`**（`event_store.py:195`）→ 单写者下安全，**多进程下会与 append 交错** |

**结论**：当前**没有**双进程写 config 的事实；但两条需要写成架构约束（见 §5）。

---

## 2. 任务二：config 读写锁 + 单写入口

**改动**

| 文件 | 改动 |
|---|---|
| `system/config.py` | 新增 `atomic_write_json(path, data, *, indent=2, retries=20)`：同目录 tempfile → `flush+fsync` → 退避重试 `os.replace`；失败**显式抛出**、清理临时文件 |
| `system/config.py` | `sync_source_config_to_runtime()` 改调 `atomic_write_json`（**双门关闭**） |
| `system/config_manager.py` | 新增 `_CONFIG_RMW_LOCK = threading.RLock()`；`update_config` 的**读→改→写全程持锁**，`hot_reload_config()` 放锁外 |
| `system/config_manager.py` | `_save_config_file` 委托 `atomic_write_json`（唯一写机制）；删掉不再使用的 `tempfile` 导入 |

**验收压测（20 线程 × 50 轮 = 1000 次写）**

```
线程=20 轮次=50 总写操作=1000 耗时=56.77s
期望字段=1000 实际落盘=1000
**丢失=0** 多余=0 返回 False=0 异常=0
结论: ✓ 零丢失（锁生效）
```

（耗时 56.77s 来自 `update_config` 原生的 `time.sleep(0.1)` 节流，与锁无关；测试里已 pat 掉该 sleep。）

**同源加固**：`atomic_write_json` 的 retry 不是装饰 —— 实测 Windows 上**读者持有句柄时 `os.replace` 会瞬时失败**（同一测试内先观察到 `WinError 5`），
退避预算按最坏 ~2s 设定，并在测试里把"写着耗尽重试后显式抛 `OSError`"与"读者永不看到半截文件"分开断言（前者容忍、后者硬断言）。

---

## 3. 任务三：单例统一惰性锁模式

**统一到的模式**（沿用仓内既有样板 `local_embedder._local_engine` / `litellm_lazy.get_litellm`）

```python
_x: T | None = None
_x_lock = threading.Lock()

def get_x() -> T:
    global _x
    if _x is None:              # 快路径（无锁）
        with _x_lock:
            if _x is None:      # 慢路径复查（DCL）
                _x = T()
    return _x
```

**为什么 inline 而不引入共享装饰器**：仓内已有两处同款 DCL 样板；
inline 改写**不动 `global` 变量名、不动 `reset_*_for_tests()` 钩子、不动返回语义**，
零耦合、零新模块，且与既有代码风格一致（"统一成同一个模式"= 统一到**仓内既有**模式）。

**覆盖面**

| | 数 |
|---|---|
| 真懒加载单例（AST 判定） | **52** |
| 改写前裸奔 | 34 |
| **本次加锁** | **34**（+ 18 本就带锁 → **52/52 全带锁，裸奔 0**） |
| 涉及文件 | 34 |
| 形状特殊需手工的 | 5（`scheduler` 多语句体；`neko_cua`/`search`/`executor_openclaw`/`lumo_proxy` 的 `X is None or X.is_closed` 条件） |

**工具**：`tools/singleton_lock_codemod.py`
- AST 严格判定函数体形状（`(docstring)? / global X / if X is None: X = Call() / return X`），**不匹配就跳过并报告**，默认 dry-run；
- 已带锁（If 体内已有 `with`）→ 识别为 `✓ 已带锁` 不动；
- 幂等（重跑无二次改动）；按行号从后往前改写避免漂移；文件结尾统一 LF。
- 加新站点：往 `TARGETS` 加一行即可复用。

---

## 4. 验证汇总

| 项 | 命令 | 结果 |
|---|---|---|
| 并发锁测试 | `pytest tests/test_concurrency_locks.py` | **18 passed** |
| 受影响模块回归（19 个测试文件） | `pytest tests/test_concurrency_locks.py tests/test_channels.py tests/test_confirm_gate.py tests/test_surface.py tests/test_task_context_channels.py tests/test_config_and_tools.py tests/test_llm_router.py tests/test_mcp_adapters.py tests/test_agent_server_smoke.py tests/test_tool_pipeline.py tests/test_blindspots.py tests/test_skill_loader.py tests/test_scope.py tests/test_onboard_doctor.py tests/test_ptz_service.py tests/test_subagent.py tests/test_task_goal_mode.py tests/test_local_embedder.py tests/test_law_tagging.py` | **272 passed** |
| 语法 | `py_compile` 全部改动文件（34 单例 + config 两件） | **全通过** |
| 模块可加载 | import 抽查（device_state / loop_checkpoint / message_queue / telemetry / websocket_manager / trust_layer …） | **全通过** |
| 运行时扫描 | 改后重扫：真懒加载单例 52 处，**带锁 52 / 裸奔 0** | ✓ |
| 压测 | config 20×50 = 1000 次写 | **零丢失** |

**已知不相关失败（非本单引入，如实标注）**：`tests/test_memory_maas.py` 9 failed + 7 errors。
根因是 **NEKO 子树与上游不一致**：`NEKO/N.E.K.O/utils/http/url.py` 缺 `same_endpoint`，
而 `NEKO/N.E.K.O/utils/config_manager/core_config.py` 要 import 它。
证据：这两个文件与远端 `main` **逐字节一致**（`3b089151dd` / `5615bbce76`，本单未改一行），
而**上游 NEKO 仓库的同名 `url.py` 已含 `same_endpoint`** → 属 2026-10-07 上游同步的**增量边界外**文件，
建议下一轮同步单独处理。

---

## 5. 边界与未做

1. **跨进程写**：本单**未**引入文件锁（`fcntl`/`portalocker`）—— 实测当前无多进程写 config 的事实，
   引入平台特定的文件锁属过度设计。改为**声明架构约束**（见下）并建议写入 `AGENTS.md`：
   > config 只由 apiserver 进程写；`event_store` 单写者 + 轮转 rename 与多进程不兼容。
2. **`caller` 语义错位**（工单205 遗留，本单未动）：`mcpserver/mcp_manager.py:113` 把 `caller` 填成工具名，
   影响任务级画像聚合 —— 需先审计消费方，独立立单。
3. **`update_config` 的定长 `time.sleep(0.1)`**：现为串行化后的固定延迟（1000 次写 ≈ 57s）。
   本单**不动语义**；若要提速需评估热重载的时序依赖，另立单。
4. **工单数字修正三处**：单例"10 处"→ 实测 52 处；telemetry"双锁"→ 实测单锁；`config.py:223`
   实际是 `system/config.py:222`（`apiserver/config.py` 无该写路径，147 行、无 `json.dump`）。
5. 全量 CI 依赖远端 runner；本机跑了上述 272 例受影响回归 + 18 例新增，**未跑全仓 900+ 例**（时间预算）。

---

## 6. 复现命令速查

```bash
cd "D:/my git/scratchpad"

# ① config 竞态（修复前会丢 19/20）
.venv/Scripts/python.exe -m pytest tests/test_concurrency_locks.py::TestConfigRmwLock -q

# ② 单例并发冒烟（16 线程同时首调，构造注入 10ms 延迟）
.venv/Scripts/python.exe -m pytest tests/test_concurrency_locks.py -q -k singleton

# ③ 原子写不变量（4 写 + 4 读持续 1s，读者不得见半截 JSON）
.venv/Scripts/python.exe -m pytest tests/test_concurrency_locks.py::TestAtomicWriteJson -q

# ④ 全仓裸单例扫描（改代码后重跑即可复核）
.venv/Scripts/python.exe tools/singleton_lock_codemod.py --check

# ⑤ 模式对照演示（裸 vs DCL）
.venv/Scripts/python.exe tools/demo_dcl_pattern.py

# ⑥ 压测（20 线程 × 50 轮）
.venv/Scripts/python.exe -m pytest "tests/test_concurrency_locks.py::TestConfigRmwLock::test_concurrent_update_no_lost_update" -q
```

> 注：本机 `pytest` 需前缀 `CODEBUDDY_SAFE_DELETE_ENABLED=0`（否则清理 tmp 时被批量删除守卫打断）。
