# WO-272 施工记录 —— P0-18 / P0-19 两处「静默数据丢失」

- **工单**：`_workorders/2026-10-22/TRAE_WORKORDER_PROMPT_AGENT_272.md`
- **定罪基线**：`main@61835ad63625`（审查报告 `docs/full-repo-review-2026-10-21/README.md` 对照表 #18 / #19）
- **交付基线**：`main@3819501fd987`
- **分支**：`wo/272-data-loss`
- **环境**：本机两个冻结 Python 环境（`C:\Users\ASUS\python-sdk\python3.13.2`、`NEKO/N.E.K.O/.venv`）一字节未装、未改；所有验证都是**只读跑**，产物写进 `Temp` 与仓库外的 `_wo272_verify/`。

## 基线核对（为什么交付基线不是定罪基线）

`GET /repos/.../compare/61835ad63625...3819501fd987` → `status=ahead, ahead_by=6, behind_by=0, total_commits=6`，
37 个变更文件里**不含**本单触碰的 `main_logic/cross_server.py` 与 `main_logic/proactive_chat/state.py`。
⇒ 从定罪基线取的改动可以原样叠到当前 main tip，无冲突、无回退他人改动。

## 一句话

两处都是同一个形状的事故：**失败被当成成功继续往下走**。P0-18 是记忆结算失败后照样
`chat_history.clear()`，那段对话在 memory_server 和本地同时消失；P0-19 是统计文件读不出来
时照样置 `loaded`，下一次自增就拿着「只有本次增量的内存」做全量覆盖写，把用户全部历史
累计计数截断成 1。本单把两个「失败」都变成可观测、可恢复的状态，并且让新写的重试队列
自己不再犯 P0-19。

---

## T1（P0-18）session end 结算失败 ⇒ 保留 + 重试

| 位置 | 改了什么 |
|---|---|
| `main_logic/memory_settle_retry.py`（**新增 455 行**） | `SettleRetryQueue`：每角色一个队列，内存一份 + `memory/<角色>/memory_settle_retry.json` 一份。载荷是事实来源，入队即落盘。退避 30s 起步、每次翻倍、封顶 1800s；`MAX_ATTEMPTS = 8` 打满后转 `exhausted`——**停止自动重试但保留载荷**；`MAX_ENTRIES = 20` 超限先丢最老的 exhausted 条目（会 `logger.error` 说清丢了哪段）。同一段重复入队只刷新退避不复制第二份；新载荷是旧条目的延长线时把旧条目并入（前缀覆盖判定用逐条相等，不用哈希近似）。 |
| 同文件 | 这个新文件自己按 P0-19 的规矩写：`unloaded / missing / loaded / failed` 四态，读失败或结构不认识（`entries` 不是列表）都记 `failed` 并**拒绝落盘**。否则「重试队列读不出来」会先变成「重试队列是空的」，再把还没结算的几段一起抹掉。 |
| `cross_server.py:808` `_defer_failed_settlement()` | 失败载荷交给队列；**入队本身失败也只是让下一次会话结束重发这段**，本地历史照样不动。 |
| `cross_server.py:846` `_notify_exhausted_settlements()` | 有 exhausted 条目时向 `status_callback` 播报「⚠️ 有 N 条记忆未结算（已自动重试 8 次）」——不能只剩日志。 |
| `cross_server.py:1014` `_advance_settled_tail()` | 补投成功后推进本地未同步尾部。**清理与 `last_synced_index = 0` 必须同一步**：只归零不清历史＝把已结算的段落重新当成未结算，下次会话结束再投一遍。 |
| `cross_server.py:1029` / `:1703` | 连接器创建 `MemorySettleRetry-<角色>` 巡检任务（15s 一轮）；连接器退出时取消任务并 `unregister_callback(connector_key)`。 |
| `cross_server.py:1569`（普通 session end） | 只在 `ok is True` 时 `chat_history.clear()` + 归零，并在成功时 `drop_covered()` 摘掉被这次投递覆盖的旧条目；失败则入队 + 播报。`_settle_endpoint` 选择（有增量 `/process`、无增量 `/settle`、语言屏障 `/cache`）一字未动。 |
| `cross_server.py:1180`（热重置 renew/settle） | 与 session end 是同一个缺陷的两个入口，原来不管成没成功都往下 clear；现在同一条规则。 |
| `cross_server.py:1177` / `:1565`（shutdown 分支） | **保持原样**：进程正在关闭时仍然 `chat_history.clear()`。关停路径不该被一条后台重试线拖住，这是有意的。 |
| `cross_server.py:1674`（语言切换屏障 `finally`） | **保持原样**：屏障仍然无条件清空连接器局部缓冲（fail-closed 隔离）。数据不靠它保，靠队列里那份载荷副本。 |

净增：`cross_server.py` 1577 → 1725 行（+148）。

## T2（P0-19）proactive 累计计数三态 + 备份

| 位置 | 改了什么 |
|---|---|
| `proactive_chat/state.py` | 加载态拆成 `unloaded / missing / loaded / failed`。`FileNotFoundError` ⇒ `missing`（合法空启动，原有文案不变）；其它异常 ⇒ `failed`，**内存原样保留、`_loaded` 保持 False**（这正是原 bug：读失败也置 `loaded`）。 |
| 同文件 `_persist_totals_unlocked()` | 非 `loaded/missing` 一律拒写并计数 `write_refusals`；写成功返回 True。 |
| 同文件（增量台账） | `failed` 期间的 `_increment_proactive_chat_total` / `_mark_invite_ever_delivered` 记进 `_proactive_chat_totals_pending_delta` / `_pending_ever_delivered`，落盘成功才清空；恢复可读时把台账**叠回磁盘基线**再写，补回的增量记日志。 |
| 同文件（备份） | 全量覆盖写之前先 `shutil.copy2` 一份 `proactive_chat_totals.json.bak`；备份失败只告警、不挡住写（写了才有价值，这点与「拒写」相反，理由在代码注释里）。 |
| 同文件 `proactive_chat_totals_load_state()` | 健康快照：`load_state / read_failures / write_refusals / pending_delta`，给调用方和体检用。 |
| 硬边界遵守 | 计数语义一字未改（v1→v2 那一次「强制重投一次」是设计）；没有新存储后端，仍是 JSON + `atomic_write_json_async`；`_source_history_*` 那套逻辑没动，只是新代码照它的约定写。 |

净增：`proactive_chat/state.py` 985 → 1131 行（+146）。

---

## 实测输出（失败注入）

跑法：仓库外的驱动脚本 `repro_p0_18.py` / `repro_p0_19.py`，同一份脚本分别接
「`main@61835ad63625` 原始文件」和「本单改后的文件」。`_post_memory_server` 被换成假实现，
`fail=True` 时返回 `(False, "HTTP 503 (body_len=0)", {})`。

### P0-18 · 原始版本（数据确实丢了）

```
############ 连接器 = main_logic._p018_baseline_connector ############
结算失败后 · 本地尾部        = 1 条（增量 1 条）
结算失败后 · 待重试队列      = 0 段
结算失败后 · sidecar 落盘    = False
再走一次 session end · 本地   = 0 条（增量 0 条）
这段对话的去向                = 没了：memory_server 没收，本地也被 clear
补投结果                      = 队列里什么都没有（{'pending': 0, 'load_state': 'unloaded', ...}）—— 那段记忆已经无从补投
```

第二次 session end 走的是 `/settle`（`增量 0 条`），这就是「已经被 clear 掉」的直接证据。

### P0-18 · 改后版本（注入失败 ⇒ 行为正确）

```
############ 连接器 = main_logic.cross_server ############
[Yui] 记忆结算未成功，1 条对话已交给待重试队列（session_id=9e2a6b8f, endpoint=process, origin=session_end）
结算失败后 · 本地尾部        = 1 条（增量 1 条）
结算失败后 · 待重试队列      = 1 段
结算失败后 · sidecar 落盘    = True
再走一次 session end · 本地   = 1 条（增量 1 条）
这段对话的去向                = 还在：本地尾部保留 + 队列里等补投
补投结果                      = 成功 1 段，队列剩 0 段
补投载荷 == 失败时那一段        = True
补投成功后的第三次 session end   = 0 条（增量 0 条）
sidecar 内容                    = []
```

### P0-19 · 原始版本 vs 改后版本

磁盘上先放一份 `{"totals": {"Yui": 7, "Akari": 3}}` 再**截断一个字符**，然后自增：

```
############ BASELINE (main@61835ad63625, P0-19 未修) ############
load_state        = n/a
_loaded           = True
ensure() returned = None
磁盘是否被改动      = 已被覆盖写改写
磁盘现在的内容      = {"Yui": 1}
*.bak 是否存在      = False

############ PATCHED (WO-272 T2) ############
load_state        = failed
_loaded           = False
ensure() returned = False
磁盘是否被改动      = 未改动（仍是损坏的原文件）
磁盘现在的内容      = 读不出来（JSONDecodeError），仍是那份损坏字节
*.bak 是否存在      = False
修复后 ensure()     = True, load_state = loaded
修复后 increment     = 9（磁盘基线 7 + 补回 + 本次）
修复后磁盘 totals    = {"Yui": 9, "Akari": 3}
```

对应工单验收三条：`_loaded` 为 False ✓、后续 increment 不修改磁盘 ✓、`*.bak` 未生成（因为没写）✓。
baseline 那侧 `Akari` 整条消失、`Yui` 从 7 变 1，就是这条 P0 的杀伤面。

### 重启恢复（队列仍在）

`tests/unit/test_memory_settle_retry.py::test_queue_survives_process_restart_by_reading_the_sidecar`：
入队 → 断言 sidecar 有 1 条 → **换一个新的 `SettleRetryQueue` 对象**（等价于重启后的进程，内存一无所有）→
读盘断言 `pending == 1` 且载荷文本一致 → 补投成功 → 队列与盘都清空。

---

## 验收用例（`pytest` 实测）

| 文件 | 用例 | 结果 |
|---|---|---|
| `tests/unit/test_memory_settle_retry.py`（新增 302 行） | 6 | **6 passed** |
| `tests/unit/test_proactive_totals_load_state.py`（新增 204 行） | 5 | 全绿 |
| 全部 `tests/unit/test_proactive*.py` + 上面两个新文件（27 文件） | 1197 | **1197 passed in 12.39s** |

```
tests/unit/test_memory_settle_retry.py ......                    [100%]
6 passed, 2 warnings in 0.52s
```

### 改坏 ⇒ FAIL（两个变异实验）

1. **退避窗口**：把 `drop_covered()` 里「摘条后落盘」那一行去掉 ⇒ `test_a_later_success_drops_the_entry_it_superseded`
   报 `assert [{'session_id...么久'}]}], ...}] == []`（内存摘了、盘上还在，重启就会重复结算）。
   **这条是施工中真实发现并修掉的缺陷**，不是事后编的变异。
2. **同一步清理**：把 `_advance_settled_tail()` 改成「只 `last_synced_index = 0`、不 `chat_history.clear()`」⇒

```
FAILED tests/unit/test_memory_settle_retry.py::test_retry_success_drains_queue_and_clears_tail_in_one_step
1 failed, 5 passed, 2 warnings in 0.63s
```

3. **成功才清**：直接拿 `main@61835ad63625` 的原始连接器跑同一份驱动 ⇒ 本地尾部在结算失败后被清成 0 条，
   队列恒为 0（见上面 P0-18 baseline 段）。

三个变异各自只打中对应用例，其余仍绿；改坏的文件均已还原并 `sha256` 校验一致。

### 全量回归（证明零回归）

`grep -rl cross_server tests/unit` 命中 25 个既有测试文件，同一份文件清单分别跑「改后」与「原始基线」：

```
PATCHED  : 15 failed, 1452 passed, 801 warnings in 45.70s
BASELINE : 15 failed, 1452 passed, 801 warnings in 45.83s
FAILED 名单逐条 diff ⇒ 完全相同（0 差异）
```

那 15 条是本机跑法的既有产物：`pytest.ini` 的 `asyncio_mode = auto` 依赖 pytest-asyncio，
而本机两个冻结环境都没有它（`pyproject.toml:235` 声明了它，**CI 才是权威口径**）；
本地用仓库外 15 行的 `asyncio_min_plugin.py` 顶替，且 `--noconftest` 跳过了 conftest 的事件循环隔离夹具，
于是跨文件的 global 状态串味。按派单纪律：**没有 skip / xfail / 放宽断言来凑绿，阻塞点如实写在这里。**

---

## 哪些既有行为被有意保留

| 行为 | 为什么保留 |
|---|---|
| shutdown 分支仍然无条件 `chat_history.clear()` | 关停不能被后台重试线拖住；这条路径的数据丢失是「进程都要死了」的既成事实，不是本单要修的静默丢失。 |
| 语言切换屏障的 `finally` 仍然无条件清空 | 那是 fail-closed 的**隔离**要求：旧连接器局部缓冲绝不能漏进切换后的新会话。数据改由队列副本保住，两边目标不再冲突。 |
| `_settle_endpoint` 的选择（`process` / `settle` / `cache` / `renew`）与增量口径 | 工单只要求「失败不丢」，动端点语义会连带改 memory_server 的写入形状。 |
| `missing`（文件不存在）的原有文案与「首次自增建文件」 | 合法空启动不是故障，把它并进 `failed` 会让每次全新安装都变成拒绝落盘。 |
| v1→v2 那一次「强制重投一次」 | 计数语义是硬边界，明写不动。 |
| `_source_history_*` 全套逻辑 | 工单硬边界；新代码只是**照它的约定**（解析进局部变量、成功才换全局、`_should_log_repeated_failure` 限流）写。 |
| 备份失败不挡住写入 | 队列与拒写机制解决的是「用错误的内存覆盖正确的磁盘」；备份只是第二道保险，为了备份失败而拒绝落盘会把可用状态锁死。 |

## 未尽事项 / 未跑的一态

1. **「记忆文件里出现该段」在 unit 层钉的是投递载荷逐条相等**（`poster.captured`），不是 memory_server
   真的写进了 `recent.json` —— 真实结算要 LLM 参与，本机不可跑。载荷之后的那一跳仍属集成面。
2. `MAX_ENTRIES = 20` 超限**是真丢**（会 `logger.error` 指明丢了哪段、几条消息）。这是「磁盘不能被无限吃穿」
   与「一条不丢」之间的取舍，选的是前者；工单没有给出该场景的验收要求。
3. 未跑真机联调（memory_server 停机 30 分钟再看补投），也未跑 CI：本仓库 PR 的门禁实跑面极窄
   （审查报告 P0-14），CI 绿不代表这 6 个用例在 CI 里被执行过。
4. 审查报告 README 的 #18/#19 处置列回填内容见本文件与 PR 描述；那篇 README 目前只在
   `full-repo-review-2026-10-21`（PR #390）分支上，main 还没有它，回填需落在那条分支。

---

## §X 修复记录（2026-10-23，合并前收口）

### 现象

PR 自带的两个用例在本机（及任意机器）**确定性失败**：

```
test_failed_settlement_keeps_the_local_tail_and_queues_the_payload
test_a_later_success_drops_the_entry_it_superseded
→ FileNotFoundError: .../Yui/memory_settle_retry.json
```

### 根因：**测试等错了信号**（产品语义是对的）

`enqueue()` 的顺序是 `entries.append(...)` → `await _save_unlocked()` → `await asyncio.to_thread(atomic_write_json, ...)`。
**内存先于磁盘是设计**（先保证不丢，落盘失败也只是下次会话结束重发）。但测试：

- `_drive_failing_session_end` 等的是 `retry.peek("Yui")["pending"] >= 1`（**内存**信号），
- 等到后立刻 `_sidecar_entries(store)` 读**磁盘**文件。

中间隔着一次 `to_thread` 跳转 ⇒ 测试必然抢先读到，**100% 失败**（换 4 个 `--randomly-seed` 都一样）。

验证：在等待条件后加 `await asyncio.sleep(0.05)` ⇒ "交给待重试队列"日志出现、失败从 2 条降到 1 条。

### 修法：给队列加**显式持久化屏障**（不是 sleep，也不是 poll 文件名）

`memory_settle_retry.py`：

- `__init__` 增加 `_saved_count`（最近一次成功落盘时覆盖到的条目数）
- `_save_unlocked()` 成功后 `self._saved_count = len(self.entries)`
- 新增 `async def wait_saved(self, timeout=5.0) -> bool`：轮询到 `_saved_count >= len(entries)` 返回 True

测试里两处改为等屏障：

```python
queue = await retry.queue_for("Yui")
assert await queue.wait_saved(), "入队后 sidecar 未在超时内落盘"
```

> 为什么不 poll 文件：那会把"sidecar 叫什么、放在哪"这种实现细节写进测试；
> 为什么不 `sleep`：猜时间，机器慢就偶发红。

### 验收

```
pytest NEKO/N.E.K.O/tests/unit/test_memory_settle_retry.py -q      → 6 passed
   （--randomly-seed=1 / 7 / 42 三个种子均 6 passed）
pytest NEKO/N.E.K.O/tests/unit/test_proactive_totals_load_state.py -q → 5 passed
两个文件合跑                                                        → 11 passed
```
