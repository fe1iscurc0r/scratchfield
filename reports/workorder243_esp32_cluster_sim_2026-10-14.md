# 工单243 交付报告 · ESP32/LoRa 自适应分簇 + RLNC 冗余分配（仿真底座）

> 执行：Trae（GitHub 线，仓库 `fe1iscurc0r/scratchpad`）｜出单：沈遥｜交付日期：2026-10-14
> 基线：fork 自 main `fd27e34124`（工单242 台账补记合并点）
> 本单**零既有文件改动**：18 个文件全部为新增（16 代码/文档 + 本报告 + 集成图）

---

## §0 一句话

在 `mcpserver/esp32/` 下落成一套**纯 Python 仿真底座**：RSSI 阈值 + 跳数的自适应分簇模拟器、
RLNC 编解码**薄兼容层**（真值源复用仓内既有 `mcpserver/rf_brain/rlnc/`，不新建第二套 GF(2^8)）、
以及只产数据的弹性仪表盘 —— 给 LoRaCanary v1.1/v1.2 重启前做可行性验证，避免 v1.0「没做仿真就烧板」重演。

---

## §1 交付物清单（18 文件，全新增，合计 108,448 B / 2,628 行）

### 代码与文档（16）

| # | 文件 | 字节 | 行 | 职责 |
|---|---|---:|---:|---|
| 1 | `mcpserver/esp32/__init__.py` | 1,084 | 20 | 包文档 + `__all__` |
| 2 | `mcpserver/esp32/dashboard.py` | 18,262 | 410 | 弹性曲线 / 跳数权衡 / 冗余扫描 → `dashboard.json` |
| 3 | `mcpserver/esp32/README.md` | 5,421 | 91 | 上层说明（三子模块 / 快速上手 / 四口径 / 落点偏差） |
| 4 | `mcpserver/esp32/cluster_sim/__init__.py` | 2,206 | 87 | 对外出口 |
| 5 | `mcpserver/esp32/cluster_sim/node.py` | 6,345 | 187 | 路损 / RSSI / 节点状态机 |
| 6 | `mcpserver/esp32/cluster_sim/topology.py` | 7,639 | 234 | 拓扑生成（grid / random / lora_deployment） |
| 7 | `mcpserver/esp32/cluster_sim/cluster.py` | 10,850 | 296 | 分簇核心（链路 / BFS 跳数 / 健康度 / 不稳定链路） |
| 8 | `mcpserver/esp32/cluster_sim/config.py` | 7,693 | 208 | YAML 配置 + 仿真编排 |
| 9 | `mcpserver/esp32/cluster_sim/config.example.yaml` | 2,695 | 40 | 配置示例（含「为什么 area 给 30 km」长注释） |
| 10 | `mcpserver/esp32/cluster_sim/README.md` | 6,421 | 133 | 分簇模块说明 + 实测对照表 |
| 11 | `mcpserver/esp32/rlnc/__init__.py` | 1,387 | 28 | 兼容层：全量镜像 + 2 具名封装 |
| 12 | `mcpserver/esp32/rlnc/encoder.py` | 1,953 | 37 | 兼容层 `encode_random()` |
| 13 | `mcpserver/esp32/rlnc/decoder.py` | 1,963 | 47 | 兼容层 `decode_full()` |
| 14 | `mcpserver/esp32/rlnc/README.md` | 4,134 | 72 | 差异表 + 身份契约（防漂移） |
| 15 | `tests/test_cluster_sim.py` | 17,638 | 430 | 40 用例 |
| 16 | `tests/test_rlnc.py` | 12,757 | 308 | 36 用例 |

> 行尾：16 文件 **CRLF 计数全为 0**（全 LF，符合本仓 `mcpserver/**` / `tests/**` 基线）。

### 报告与集成图（2）

| # | 文件 | 说明 |
|---|---|---|
| 17 | `reports/workorder243_esp32_cluster_sim_2026-10-14.md` | 本报告 |
| 18 | `docs/integration-graph/esp32.txt` | 依赖图（对齐 242 的 `rf_workflow.txt` 格式） |

---

## §2 路径对账（工单 §1/§2 写的路径 vs 本仓实况）

**这是本仓第 9 次「工单写的路径与实况不符」**（前 8 次：210/228/229/237/239/240/241/242）。
main 全树 22,561 blob / 25,114 条目，逐条 `GET /contents/<path>?ref=main` 实测：

| 工单声明的路径 | 实测 | 处置 |
|---|---|---|
| `mcpserver/esp32/cluster_sim/` | **404** | ✅ 本单新建 |
| `mcpserver/esp32/rlnc/` | **404**，但 `mcpserver/rf_brain/rlnc/` **存在（10 文件）** | ⚠️ 建**薄兼容层**（re-export），不重复实现 |
| `mcpserver/esp32/dashboard.py` | **404** | ✅ 本单新建 |
| `tests/test_cluster_sim.py` | **404** | ✅ 本单新建 |
| `tests/test_rlnc.py` | **404** | ✅ 本单新建 |
| `WORKORDER_SEEDS_V2_2026-10-11.json`（§1 称素材池） | **404**（全树 0 命中） | ⚠️ 未落地，见 §9 |
| `mcpserver/esp32_inspiration_doc`（§1 提到） | **404** | ⚠️ 未落地，见 §9 |

**新增的一类偏差**：以往 8 次是「工单写的路径不存在」；本次是
**「工单要求新建的东西已经存在」** —— 任务二要「新建 `mcpserver/esp32/rlnc/`（GF(2^8) 编解码，只用 numpy）」，
但本仓 `mcpserver/rf_brain/rlnc/` 已有完整实现。按字面新建 = 仓内出现**第二套 GF(2^8) 公式** ⇒ 必然漂移。

---

## §3 任务落地

### 任务一（P0）自适应分簇模拟器 ✅

- `node.py`：对数距离路损 + RSSI + 最大可达距离**解析反解**。FSPL 常数 `−147.55` 与
  `mcpserver/rf_workflow/lora_phy.py`（工单242 真值源）**同源**，避免仓内两套口径。
  `d < 1 m` 按 1 m 截断（近场公式不适用）。
- `topology.py`：`grid` / `random` / `lora_deployment`（**合成样例**，非真实布点表）。
  频道参数（`freq_hz` / `path_loss_exponent`）挂在 `Topology` 而非 `Node` —— 信道属性 vs 节点属性。
- `cluster.py`：RSSI 阈值可达图 → BFS 跳数 → 确定性分簇（活邻度降序 + id 升序）。
  `Cluster.health()` = 活成员占比 × 连通度 `1/mean_hops`；**簇头失效 ⇒ 0**。
  `unstable_pairs()`：距阈值不足 margin（默认 6 dB）的链路标为「抖动即断」。
- `config.py`：YAML 输入四项必填（`nodes` / `area` / `rssi_threshold` / `simulate_duration`）+ 扩展项；
  未知键 / 非法值直接 `ValueError`。
- 输出 JSON 形态与工单 §2 任务一.3 一致（`clusters[{id, members, health, ...}]` + `unstable_pairs`），
  **额外自检** `stats.uncovered_alive`（活节点覆盖性，必须为空）。

### 任务二（P0）RLNC 编/解码库 ✅（**薄兼容层**）

- `rlnc/encoder.py`：`encode_random(blocks, *, factor, generation=0, seed=None)`
  ≡ `RlncEncoder(len(blocks), factor, generation, seed).encode(blocks)`
- `rlnc/decoder.py`：`decode_full(blocks, *, k=None, generation=None)` —— k 缺省时按系数长度**众数**推断
- `rlnc/__init__.py`：`from mcpserver.rf_brain.rlnc import *` 全量镜像 + 上述 2 个新符号。
  **实测 `__all__` 30 项**（28 镜像 + 2 新增），14 个符号的 `is` 身份断言全为 True
  ⇒ 任何一边改数学，另一边立刻同步，**公式漂移结构性不可能**。
- 依赖：兼容层**导入链无第三方依赖**（真值源 `__init__` 只导出 7 个标准库模块）。
  ⚠️ 同目录 `apc_mesh_routing.py` 确实 `import numpy`，但**不在导入链上** —— 由
  `test_compat_layer_import_chain_has_no_heavy_dependency`（静态解析镜像表）+
  `test_importing_compat_layer_does_not_pull_numpy`（子进程 `sys.modules` 实证）双证守死。
- 工单说「只用 numpy」：**实际更严** —— 核心路径连 numpy 都不需要（纯 Python GF(2^8) 查表）。

### 任务三（P1）弹性曲线 + 仪表盘 ✅

`dashboard.py` **只产数据不画前端**，输出 `dashboard.json` 三块 + `model` / `config`：

| 面板 | 内容 |
|---|---|
| `resilience_curve` | 失活率 5/10/20/30% → 重建成功率 |
| `cluster_scale_vs_hops` | `max_hops` 1→4 的「簇规模 ↑ vs 中继跳数 ↑」权衡 |
| `rlnc_redundancy_sweep` | 固定 20% 失活下扫冗余率 factor |

重建模型（刻意简单，已在 docstring + payload `model.caveat` 明示**不是物理层仿真**）：
取**活成员最多**的簇 → 中继槽位 `min(A, n)` → 取跳数最近的活成员 → 每块沿 `h` 跳的生存率 `s^h`（`s = 1 − block_loss_rate`）
→ 收到的块喂 `decode_full` → **满秩即成功**（与源块逐字节比对）。

---

## §4 验收逐条对账（工单 §3）

| # | 验收项 | 结果 | 证据 |
|---|---|---|---|
| 1 | `pytest tests/test_cluster_sim.py tests/test_rlnc.py -q` 全绿（≥6 用例） | ✅ **76 passed / 0 failed**（40 + 36） | 验证场 `realrepo/field` 实跑 |
| 2 | 两目录完整（`__init__.py` / `node.py` / `encoder.py` / `decoder.py` / `README.md`） | ✅ | §1 清单；两目录各有 `README.md` |
| 3 | `python -m mcpserver.esp32.dashboard --nodes 50 --failure 0.2` 跑通并出 `dashboard.json` | ✅ | 见 §5 输出（LF，6,444 B） |
| 4 | PR 描述含 §0 两条 arXiv 复查表 | ✅ | 见 §5；报告 + PR 正文双处复述 |
| 5 | 不许触碰四类禁区（`mcp_assembly`/`mcp/services` 路由、`core/` stdlib 强约束、`coupled/`、`.hermes/config.yaml`） | ✅ | 18 文件**全新增**，零既有改动（§8 反向断言） |

**lint**：`ruff check --config ruffcfg/pyproject.toml mcpserver/esp32 tests/test_cluster_sim.py tests/test_rlnc.py`
→ `All checks passed!`（完整 `E/F/I/UP/N/SIM`）。

---

## §5 §0 两条 arXiv 链接复查（2026-10-14 实测，直连 `arxiv.org/abs/<pid>`）

| pid | HTTP | 标题 | 与 ESP32/LoRa 贴合度 |
|---|---|---|---|
| `2608.26040` | **200** | Adaptive Peer Clustering with Hierarchical Random Linear Network Coding for Resilient Decentralized Wireless Networks | **HIGH 贴题**（主体） |
| `2609.07269` | **200** | Singularity-Free Guiding Vector Fields on SO(3) with Designer-Specified Progression Behavior | **LOW 噪声**（机器人控制，与 ESP32 无关，备查） |

- 两条均 **200**，标题与工单 §0 记的一致（无「标题被改」情形）。
- 正文抓取：`2608.26040` abstract **1,563 字符**、`2609.07269` abstract **1,575 字符**（均非空壳页）。
- `2608.26040` abstract 字面命中：**EWMA 可靠度**、**multi-tier network coding within and across clusters**、
  `O(sqrt(T))` regret（FTRL）、Jetson Nano testbed、线性扩展到 500+ 节点。
  ⇒ **本单的三处设计都能在该 abstract 里找到出处**：① 分簇依据用 EWMA 可靠度
  （本仓 `rf_brain/rlnc/reliability.py::EWMAReliability` 已有实现，本单未改）；
  ② 簇内/簇间分层编码（`RlncEncoder` 的 `generation` 隔离即分层）；
  ③ 自适应重配置（本单以 `max_hops` / 失活率扫描刻画，**未做** FTRL 在线重配，见 §9）。
- `2609.07269` 确认为噪声：abstract 全篇 SO(3) / Lie-group / 控制律，**零** ESP32 / LoRa / 网络编码字样。

---

## §6 与工单叙述的偏差（如实记录）

| 工单说法 | 实况 | 处置 |
|---|---|---|
| 任务二「新建 `mcpserver/esp32/rlnc/`」 | 仓内 `mcpserver/rf_brain/rlnc/` 已有 10 文件完整实现 | 建**薄兼容层**，见 §7 |
| 任务二「只用 numpy，不引 kodo/jeromq」 | 核心路径**连 numpy 都不用**（纯 Python GF(2^8) 查表）；兼容层导入链无第三方依赖 | 满足且更严；同目录 numpy 支已明确隔离并加守卫 |
| §1「素材池 `WORKORDER_SEEDS_V2_2026-10-11.json`」 | 全树 0 命中（404） | 未落地，见 §9 |
| §1「现有 `mcpserver/esp32/` 下做 PoC」 | 该目录**不存在**（404） | 按语义新建整个包 |
| §2 任务一.1「`topology.py`：真实 LoRa 部署样例」 | 本仓无 LoRaCanary 真实布点表（`firmware/dcp_lora/` 只有固件） | `lora_deployment` 是**合成样例**，docstring/README 均标注；建议未来加 `from_waypoints()` 而非改该函数 |
| §2 任务一.2「`simulate_duration: hours`」 | 本单分簇是**静态快照** | 该参数只作**观测窗口**记录，**不驱动任何时变过程**（README 单节说明「别过度解读」） |

---

## §7 设计取舍：为什么是「薄兼容层」而不是按字面新建

工单要求新建一套 GF(2^8) 编解码。字面执行会导致仓内**两套 GF(2^8) 公式**：
`rf_brain/rlnc/galois.py`（不可约多项式 `0x11B`，**生成元 0x03** —— docstring 明写 0x02 在该域不是生成元）
与新写的第二套一旦在多项式/生成元/字节序上任一处不同，就是**静默的数据不互通**。

因此本单的选择：
1. **单一真值源**：`rf_brain/rlnc/` 是唯一实现，本包只 re-export + 补工单字面 API 名；
2. **身份契约当回归**：`tests/test_rlnc.py` 对 14 个符号做 `is` 断言，并断言
   `set(ref.__all__) <= set(esp.__all__)` 且新增符号恰好 2 个；
3. **依赖边界显式**：把「导入链不含 numpy 那支」写成两条独立守卫（静态 + 子进程）；
4. **已知边界留证而非隐藏**：真值源 `decoder.py` 的 `block_size` 由**首个被接受的块**锁定 ⇒
   一个载荷多带 1 字节的脏块若**最先**到达，会被当作块长基准并毒化本代（真值源明写「块级完整性由下层
   dcp 帧 CRC 保证」，故解码器无法自证）。这一条写成**独立用例**
   `test_first_accepted_block_locks_block_size_known_boundary` 留证，防止将来有人误当缺陷「修」掉。

---

## §8 质量与回归

### 本轮修正（自检发现的 5 处名不副实 / 事实错误）

交付前逐条实测，发现并修掉 5 处。**这些都不是口味问题，是「标签与判据不一致」或「数字是拍脑袋的」**：

| # | 问题 | 实况 | 修正 |
|---|---|---|---|
| 1 | 测试 `test_bad_blocks_are_rejected_without_polluting_state` 失败（`assert True is False`） | 「载荷长度错」的块是**最先到达**的块，反被接受并锁定块长 | 拆成阶段一（冷启动，与块长无关的三类坏块）/ 阶段二（先喂好块锁块长，四类坏块全拒）；另立独立用例留证该边界 |
| 2 | `test_compat_layer_has_no_heavy_dependency` 失败 | 我把 `rf_brain/rlnc/` 整体说成「纯标准库」是**错的** —— `apc_mesh_routing.py` 用 numpy | 守卫改为「**导入链**无重依赖」+ 新增子进程实证；README/`__init__`/上层 README 三处表述同步更正 |
| 3 | `build_dashboard()`（cfg=None）与 CLI 默认给出**两套数字**（5% 失活：21.7% vs 45.0%） | 库默认沿用 `cluster_sim.DEFAULT_CONFIG`（`topology="grid"`），CLI 默认 `random` | 新增 `DASHBOARD_BASELINE`（与 CLI 默认值逐项一致，`topology="random"`），并加回归 `test_dashboard_default_baseline_matches_cli` |
| 4 | 文档写「30 km 下平均度 ≈ 5.8，落在连通相变附近」 | **实测错**：解析 `λπr² ≈ 3.64`、实测（10 seed）`≈ 3.06`，均在相变（约 4.5）**之下** | 四处（`config.py` / `config.example.yaml` / `cluster_sim/README.md` / `dashboard.py`）改为实测值；新增 `test_default_area_sits_below_connectivity_transition` 钉住 |
| 5 | payload 字段名 `failure_reasons` 里混入成功档 `"ok"`（会让人把成功数当失败数加总） | 该 dict 实为「按结局原因计数」 | 更名 `reason_counts` + 不变量断言 `sum(values) == trials`；README 写明「含 ok」 |

> 第 4 条尤其值得记：**「平均度 5.8」是我自己先前凭感觉写的，没有任何计算支撑。**
> 本轮把解析式与实测值一起写进测试，才让它不可能再复发。

### 自动化测试（76 用例，全部确定性）

```
tests/test_cluster_sim.py   40 passed
tests/test_rlnc.py          36 passed
```

覆盖：拓扑三型 + 可复现 + 未知 kind / 路损与 FSPL 等价 / 1 m 截断 / RSSI 单调 / 最大距离反解 /
**默认区域落在连通相变之下的量化依据** / 覆盖性 `uncovered_alive == []` / 分簇确定性 /
簇头 hop=0 / `max_hops=0` 全单点 / 簇头失效⇒0 与单成员退化 / `health` 不变量 /
不稳定链路与 `margin=0` 边界 / `bfs_hops` 三种参数 / YAML 解析 + 10 组非法值 /
失活计数与可复现 / `simulate` 静态窗口 / dashboard 单调性 + 权衡 + 冗余扫描 + 确定性 + CLI 写 LF /
**库默认 == CLI 默认** / **`reason_counts` 加总不变量** /
兼容层 14 符号 `is` 身份 / `__all__` 镜像完整性 / **导入链无重依赖（双证）** /
10 种子编解码 100% / 少一包边界 / factor=0 / k=1 / k 众数推断 / 30% 丢包 / 坏块拒收 /
**块长基准锁定边界（留证）** / 线性相关不增秩 / GF 乘法逆元与分配律。

### 端到端实测（`seed=20261014`，可复现）

**A. 分簇（`config.example.yaml`）**

```
12 簇 ｜ largest=10 ｜ mean_size=4.167 ｜ mean_health=0.986111
unstable_pair_count=45 ｜ uncovered_alive=[]
簇规模（降序）= [10, 9, 6, 5, 4, 4, 4, 4, 1, 1, 1, 1]
```

**B. dashboard CLI（`--nodes 50 --failure 0.2`，与 README 逐字一致）**

```
[dashboard] nodes=50 topology=random seed=20261014
  failure    5% → 重建成功  45.0%  (活成员均值 11.617, 收块均值 7.217)
  failure   10% → 重建成功  36.7%  (活成员均值 10.85, 收块均值 6.967)
  failure   20% → 重建成功  20.0%  (活成员均值 9.35, 收块均值 6.017)
  failure   30% → 重建成功  11.7%  (活成员均值 8.333, 收块均值 5.667)
  [focus] failure 20% → 20.0% (12/60)
[dashboard] 已写出 dashboard.json (6444 B)
```

`reason_counts` 实测：5% → `{ok: 27, underdetermined: 32}`；30% → `{ok: 7, underdetermined: 53}`（均加总 60）。

**C. 跳数权衡**

| max_hops | 簇数 | 平均簇规模 | 最大簇 | 平均中继跳数 | 平均健康度 |
|---:|---:|---:|---:|---:|---:|
| 1 | 16 | 3.125 | 8 | 0.429 | 1.000 |
| 2 | 12 | 4.167 | 10 | 0.625 | 0.986 |
| 3 | 11 | 4.545 | 14 | 0.701 | 0.962 |
| 4 | 10 | 5.000 | 16 | 0.750 | 0.950 |

⇒ **簇变大是用中继跳数（路径变长）换来的**，健康度单调下降。

**D. 冗余扫描（20% 失活）**

| factor | n | 成功率 |
|---:|---:|---:|
| 0.0 | 8 | 3.3% (2/60) |
| 0.3 | 10 | 15.0% (9/60) |
| 0.6 | 12 | 20.0% (12/60) |
| 1.0 | 16 | 21.7% (13/60) |

⇒ **无冗余时几乎必败（3.3%），加冗余后提升到 21.7%** —— 这是 RLNC 值得引入的直接证据。

**E. 区域对照表复测（5 行逐行吻合 `cluster_sim/README.md`）**

| 区域 | 阈值 | 簇数 | 前 5 大簇划分 |
|---|---|---:|---|
| 500 m × 500 m | −120 dBm | 1 | `[50]` ❌ 退化 |
| 10 km × 10 km | −120 dBm | 1 | `[50]` ❌ 退化 |
| 20 km × 20 km | −115 dBm | 3 | `[43, 4, 3]` ⚠️ |
| **30 km × 30 km** | **−110 dBm** | **12** | **`[10, 9, 6, 5, 4]`** ✅ |
| 40 km × 40 km | −115 dBm | 11 | `[16, 9, 6, 4, 4]` ✅ |

---

## §9 未落地 / 需沈遥侧接手

| # | 项 | 说明 |
|---|---|---|
| 1 | `WORKORDER_SEEDS_V2_2026-10-11.json` | 工单 §1 称其为素材池，**全树 404**。若确需入仓，请沈遥提供内容与落点 |
| 2 | `mcpserver/esp32_inspiration_doc` | 工单 §1 提及，**404**。同上 |
| 3 | 簇头**重选**机制 | 本单只做静态快照 + 健康度评估（支持传入更新后的存活性集合评估退化），**未实现**簇头重选。已在 `cluster.py` docstring 与测试标注为「已知简化而非遗漏」 |
| 4 | 时变过程 | `simulate_duration` 不驱动任何时变；节点随机加入/退出、链路质量时间序列、重传退避均不在本单范围 |
| 5 | FTRL 在线重配置 | 论文 `2608.26040` 的 `O(sqrt(T))` regret 在线重配**未实现**；本单以 `max_hops` / 失活率静态扫描刻画 |
| 6 | 真实布点表 | `lora_deployment_topology()` 是**合成样例**。建议后续新增 `from_waypoints()` 读取真实布点，**不要改**该函数（会破坏既有用例口径） |
| 7 | Web UI / Plotly 接入 | 本单按工单要求**只产数据**，`dashboard.json` 已就绪待前端接 |
| 8 | 硬件验证 | 仿真 ≠ 真机。这是 v1.1/v1.2 重启前的**可行性底座**，不代表现场能跑多远 |

**无新增「需沈遥侧接手」的动作项**（工单 §4 备忘未要求任何运维动作）；
工单241 遗留的三项交接（真实审计落点 / `AGENT_GOVERNANCE=1` 上线发令牌 / `HERMES_AGENT_ID_KEY` 分发）**与本单无关**，仍待处理。

---

## §10 数据快照口径

| 项 | 值 |
|---|---|
| 基线 commit | main `fd27e34124`（工单242 台账补记合并点） |
| 本单新增 | 18 文件 / 108,448 B（代码文档 16 文件）+ 报告 + 集成图 |
| 既有文件改动 | **0**（合并后逐文件反向断言） |
| 随机种子 | `20261014`（dashboard `DEFAULT_SEED`；所有实测数字均出自该 seed） |
| 实测环境 | Python 3.13.12 + pytest（workbuddy 隔离 venv）+ ruff 0.16.8；numpy 2.5.4 / PyYAML 6.0.3 可用但核心路径不依赖 numpy |
| 验证方式 | 「真仓验证场」：`cp -r` 出 `mcpserver/ system/ tests/`，再用 main 真字节覆盖 ⇒ 在**真实 import 链**上跑 pytest（非 mock） |
