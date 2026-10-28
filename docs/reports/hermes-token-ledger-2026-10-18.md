# Hermes token 账本基线（2026-09-18 ~ 2026-10-18）

> 由工单 261 产出。**数字来源：沈遥 2026-10-18 云服实测（工单 §0.2）+ 脚本对 fixture 的自检**。
> 脚本自身未在本机对真实 `~/.hermes/state.db` 运行过（本机无该库）——凡未实跑的项均标注「未测」。

## 1. 样本口径

| 数据源 | 路径 | 规模 | 可用性 | 用法 |
|---|---|---|---|---|
| **state.db** | `~/.hermes/state.db` | 2.6 GB | ✅ 权威 | 唯一可信账本（sessions / session_model_usage / messages） |
| request_dump | `~/.hermes/sessions/request_dump_*.json` | 1,084 份 / 33 MB | ⚠️ 样本有偏 | **全部是失败请求**（`error.type` 非空 1084/1084）⇒ 只用于「报错循环」，**不可当成本基线** |
| logs | `~/.hermes/logs/` | 33 MB | 辅助 | 仅对时间线 |

**已核实的口径限制**

- `messages.token_count` **实测全为 NULL** ⇒ 字符量走 `length(content)`，无可换算的 token 数。
- `sessions.cost_status` 多条为 `unknown` ⇒ `estimated_cost_usd` 只能作量级参考，**不是账单**。

## 2. 三段占比 + 缓存命中率（30 天实测）

| 项 | 数值 |
|---|---:|
| sessions | 1,011 |
| api_calls | 9,797 |
| input | 29,073,669 |
| cache_read | 600,890,803 |
| cache_write | 0 |
| output | 3,409,385 |
| **缓存命中率** | **95.4%** |

7 天口径：api_calls 2,582 / cache_read 162,958,141 / 命中率 95.4%。

**消息字符构成（全库，6 月至今）**

| role | 条数 | 总字符 | 占比 |
|---|---:|---:|---:|
| tool | 121,560 | 226,738,985 | **82.3%** |
| assistant | 127,451 | 33,744,380 | 12.2% |
| user | 15,017 | 15,009,352 | 5.4% |

**工具输出字符 Top（全库，原始口径）**

| tool_name | 调用数 | 总字符 | 均字符 | 单次最大 |
|---|---:|---:|---:|---:|
| web_search | 65,569 | 116,044,904 | 1,770 | 27,903 |
| read_file | 3,501 | 33,965,288 | 9,702 | 102,816 |
| terminal | 23,462 | 28,839,014 | 1,229 | 56,375 |
| web_extract | 17,459 | 15,754,214 | 902 | 3,981 |
| execute_code | 3,874 | 10,253,190 | 2,647 | 50,014 |
| session_search | 495 | 8,020,397 | 16,203 | 90,400 |
| skill_view | 398 | 5,333,605 | 13,401 | 97,949 |

## 3. 回注放大（真实账单权重）Top 10

> **未测**：`reflush` 需要真实 `state.db`（本机没有 2.6 GB 库）。
> 该子命令已在 fixture 上自检通过（见 §6），云服执行命令：
> ```bash
> python3 scripts/token_ledger.py reflush --since 30d --json > reflush.json
> ```
> 判读方式：把下表（原始字符）与 `reflush` 的 `amortized_chars` 并列看，
> 比值越大说明「这条工具输出被反复回注的次数越多」，才是真实账单权重。

| tool_name | 原始字符（§0.2） | 摊销字符 | 比值 |
|---|---:|---:|---:|
| web_search | 116,044,904 | 未测 | 未测 |
| read_file | 33,965,288 | 未测 | 未测 |
| terminal | 28,839,014 | 未测 | 未测 |
| web_extract | 15,754,214 | 未测 | 未测 |
| execute_code | 10,253,190 | 未测 | 未测 |
| session_search | 8,020,397 | 未测 | 未测 |
| skill_view | 5,333,605 | 未测 | 未测 |

**预判（待数据验证，不是结论）**：`web_search` 原始字符第一但单次仅 1,770 字符 ⇒ 若回注系数低，
其账单权重可能远低于 `read_file`（单次 9,702，最大 102,816）与 `session_search`（单次 16,203）。

## 4. 缓存失效事件

> **未测**：需真实库。检测口径（`cache` 子命令，阈值默认 50%）：
> 同一模型、按 `started_at` 相邻的两个 session，后者 `input_tokens > 前者 cache_read × 0.5`
> ⇒ 记为一次失效，并记录 `system_prompt_hash` 是否变化。

```bash
python3 scripts/token_ledger.py cache --since 30d --threshold 0.5 --json > cache.json
```

## 5. 三条改进建议

> 每条标注「影响哪个指标 + 量级区间」，**不写倍数**（本节刻意回避厂商口径）。

1. **优先压缩「单次大输出」而非「高频小输出」**
   影响指标：`cache_write` 与失效后的全量 `input`。
   量级：若把 `read_file`（单次均值 9,702 字符、最大 102,816）与 `session_search`（均值 16,203）的
   单次体积压到 1/3 以内，按它们合计 4,000 万字符估算，可削减的**首次写入**量在百万～千万字符量级。

2. **先定位缓存失效，再谈省 token**
   影响指标：`cache_read` 占比（当前 95.4%）。
   量级：命中率每掉 1 个百分点，等价于把约 1/95 的 input 变成全价；在 30 天 6.3 亿 token 的量级上，
   这比「压缩工具输出」的直接影响更大。**动作**：先跑 `cache` 子命令拿到失效事件数与涉及 token。

3. **把「报错循环」当独立优化项**
   影响指标：`api_calls`（重复调用）与 output。
   量级：1,084 份失败 dump 里若能识别出重复型，按「每段 ≥3 次重复」估算，可砍掉的调用数在
   百次量级（占 9,797 的个位数百分比）。

## 6. 脚本自检（fixture，本机实跑）

```bash
python3 -m pytest tests/test_token_ledger.py -q      # 6 passed
```

覆盖：summary 计数与命中率、单价缺失时成本为 null（不是 0）、tools Top1、
reflush 早期消息摊销更大、loops min-repeat=3 命中 1 条、空库退出码 1 无 traceback。

---

> 本报告数字来源：沈遥 2026-10-18 云服实测（工单 §0.2）+ 脚本 fixture 自检。未测项标注「未测」。
