# 工单 255 完工报告 · 遥测「何时传」四策略对比 + LoRa 噪声-功耗折中表

> 执行：Trae（GitHub 线）｜ 日期：**2026-10-17** ｜ 基线：main `192aaf5a48`
> 工单：`TRAE_WORKORDER_PROMPT_AGENT_255.md`（无线电线一）
> 交付：**4 个新代码/测试文件 + 本报告**，`lora_phy.py` **零改动**

## §0 · 交付物

| 文件 | 类型 | 说明 |
|---|---|---|
| `mcpserver/rf_workflow/telemetry_scheduler.py` | 新 | 任务A：四策略确定性仿真器 + 指标表 + `--demo/--json` |
| `mcpserver/rf_workflow/lora_power_tradeoff.py` | 新 | 任务B：两张表（链路折中 / WuRX 占空比预算），**复用 `lora_phy`** |
| `tools/test_telemetry_scheduler.py` | 新 | 11 用例（含两条硬断言） |
| `tools/test_lora_power_tradeoff.py` | 新 | 8 用例（含"不得复制公式"的反向断言） |
| `reports/workorder255_wireless_telemetry_2026-10-17.md` | 新 | 本报告 |

**不变量**：`mcpserver/rf_workflow/lora_phy.py` **内容零改动** —— 本单只 import 复用；
`git diff --stat -- mcpserver/rf_workflow/lora_phy.py` 为空（PR 变更集里不含该文件即为证）。

## §1 · 指标口径（本单自己定义，报告与测试都引用这里）

| 指标 | 定义 |
|---|---|
| **AoI** | 每 tick，`t - 最近一次「已送达」样本的生成时刻` |
| **AoA**（动作信息年龄） | 接收端每 5 tick 执行一次动作；`AoA = 动作时刻 - 该动作所用样本的生成时刻`，只在动作时刻取样 |
| **AoII（动作侧）** | `(缺电未能执行的动作数 + 执行了但所用值误差超容差的动作数) / 计划动作数` —— **控制口径**：一个跑不起来的动作与一个跑错的动作用同一个代价 |
| **AoII（错误持续时间）** | `|真值 - 接收端状态| > 容差` 的 tick 数 / 总 tick 数 —— **信息口径**（AoII 原文的"错误时间占比"） |
| 发送次数 / 总能耗 / 丢更新 | 见 `Metrics`；丢更新 = 信道忙或没电时被丢弃的更新（无队列） |

> ⚠️ **两套 AoII 都报**，因为工单只说「AoII 违例率」未定义；只报一套容易变成"换个口径结论就翻"。
> 结论：**两套口径方向一致**（见 §3），不是靠选口径凑出来的。

## §2 · 仿真内核的四个建模决定（都可被质疑，故写明理由）

1. **信道占用模型**：一次传输占用信道 `latency_ticks=2`；占用期间想发 ⇒ 计丢更新（低功耗节点无队列）。
   （第一版"新发即清空在途"会让连续发送的节点**永远收不到**，已修正。）
2. **事件交替方向**：事件阶跃 `+0.30` 交替符号。单调阶跃会把值顶到 1.0 饱和，之后**再无"新数据"**
   ⇒ gated 会永久静默（第一版实测 600 tick 只发 2 次，已修正）。
3. **「有新数据」带底噪** `change_epsilon=0.10`：否则随机抖动让 gate 恒真，gated 退化成"有电就发"。
4. **两个场景**：`scarce`（采集 0.10 mJ/tick；动作 0.35/5tick 就吃掉 0.07，留给发射仅 0.03 ⇒ 发一次要攒 40 tick）；
   `abundant`（采集 3.0 mJ/tick ⇒ 能量不再是瓶颈）。参数全部显式写在 `Scenario` 里，可替换。

## §3 · 实测结果

### 3.1 稀缺能量（`scarce`）

| 策略 | AoI(tick) | AoA(tick) | AoII(动作侧) | AoII(错误时间) | 发送次数 | 总能耗(mJ) | 丢更新 | 错过的动作 |
|---|---|---|---|---|---|---|---|---|
| `periodic` | 14.77 | 13.41 | **30.00%** | 16.33% | 25 | 65.00 | 35 | 20 |
| `aoi_threshold` | 14.68 | 13.51 | **32.50%** | 18.50% | 25 | 65.35 | 306 | 19 |
| **`aoa_energy_gated`** | 31.40 | 32.11 | **7.50%** | **3.00%** | 9 | 52.80 | 0 | **0** |
| `event_triggered` | 31.40 | 32.11 | 7.50% | 3.00% | 9 | 52.80 | 0 | 0 |

### 3.2 能量充裕（`abundant`）

| 策略 | AoI(tick) | AoII(动作侧) | AoII(错误时间) | 发送次数 |
|---|---|---|---|---|
| `periodic` | **6.47** | 7.50% | 3.00% | 60 |
| `aoi_threshold` | 7.46 | 7.50% | 3.00% | 50 |
| `aoa_energy_gated` | **31.40** | 7.50% | 3.00% | 9 |
| `event_triggered` | 31.40 | 7.50% | 3.00% | 9 |

### 3.3 机制自证（为什么 gated 在稀缺下更好，不是调参凑的）

稀缺下 `periodic`/`aoi_threshold` 会**在值没变时也发**（信息价值为零的发送）⇒ 电池被无效更新吃掉
⇒ 等真正的事件到来时反而没电，**动作也做不成**（错过 20 / 19 次）。
`gated` 只在「有新数据 且 有能量」时发 ⇒ 省下的电留给动作，**一次都没错过**。

## §4 · ⚠️ 硬断言结果（工单 §4 允许"未达标 + 差异"，禁止改断言变绿）

| # | 工单原文 | 结果 |
|---|---|---|
| 1 | 稀缺下 `aoa_energy_gated` 的 AoII 违例率**严格低于** `periodic` 与 `aoi_threshold` | ✅ **PASS**，且**两套口径同时成立**：动作侧 7.50% < 30.00% / 32.50%；错误时间 3.00% < 16.33% / 18.50% |
| 2a | 充裕下三者 **AoII** 收敛 | ✅ PASS（四策略 AoII 完全相等，7.50% / 3.00%） |
| 2b | 充裕下三者 **AoI** 差距收敛 | ❌ **不成立（如实报）**：gated 的 AoI = **31.40** vs periodic **6.47** / aoi_threshold **7.46**，差 4~5 倍，且比稀缺场景的差距**更大** |

**2b 的差异归因**：`gated` 的 AoI 是它**用 AoI 换能效**的必然取舍（只在有新闻时才说），
能量充裕时这个取舍**纯亏**（能量本来不要钱），所以 AoI 不可能收敛到 `periodic` 的水平。
**归属建议**：把工单断言 2 改写为「充裕能量下 **AoII 差距收敛**（AoI 上 gated 显著更差，属取舍）」。
本单已用 `test_abundant_aoi_does_not_converge_tradeoff_is_real` **把这个事实钉死**——
谁想靠调参让 AoI "看起来收敛"，该用例会红。

## §5 · 验收命令（工单 §2 四条，原始输出）

```
# 1) 策略对比
$ python -m mcpserver.rf_workflow.telemetry_scheduler --demo > /tmp/wo255_a.txt
$ grep -cE "periodic|aoi_threshold|aoa_energy_gated|event_triggered" /tmp/wo255_a.txt
8                       # ≥4 ✓

# 2) 折中表 + WuRX 预算
$ python -m mcpserver.rf_workflow.lora_power_tradeoff --demo > /tmp/wo255_b.txt
$ grep -c "VIOLATION" /tmp/wo255_b.txt
2                       # ≥1 ✓（0.5 s 唤醒周期 ⇒ 占空比 20% > 限值 10%）

# 3) 真值源复用（不得复制公式）
$ grep -c "from .lora_phy import" mcpserver/rf_workflow/lora_power_tradeoff.py
1                       # ≥1 ✓

# 4) 测试
$ python -m pytest tools/test_telemetry_scheduler.py tools/test_lora_power_tradeoff.py -q
19 passed in 0.15s      # ✓
```

**ruff**：4 个新文件 `All checks passed!`。

## §6 · 表 A / 表 B 摘要（节选，**数字全部取自 `--demo --json` 实测输出**）

```
表 A · SF × BW × CR（真值源 lora_phy）
SF  BW(kHz)  CR    灵敏度(dBm)  ToA(ms)  每比特能耗(µJ)  标称速率(bps)
7   125      4/5   -123.00      51.46    10.098         5468.8
9   125      4/5   -129.00      164.86   32.353         1757.8
12  125      4/8   -137.00      1712.13  335.990        183.1
12  250      4/5   -133.99      577.54   113.336        585.9

表 B · WuRX 唤醒占空比预算（主接收 30 mW / 唤醒接收 10 µW / 唤醒窗 0.1 s）
唤醒周期(s)  主接收占空比(%)  日均能耗(J)  常开监听(J)  省电(%)  限值(%)  合规
0.5          20.0             519.26      2592.0      79.97   10.0    VIOLATION
1.0          10.0             260.06      2592.0      89.97   10.0    OK
2.0          5.0              130.46      2592.0      94.97   10.0    OK
5.0          2.0              52.70       2592.0      97.97   10.0    OK
10.0         1.0              26.78       2592.0      98.97   10.0    OK
```

## §7 · ⚠️ §0 的「字面验」未能执行（如实记录）

工单 §0 要求粘 `curl export.arxiv.org/api/query?id_list=2610.22304,…` 的标题输出。本机实测：

```
$ curl -s -o /dev/null -w "%{http_code} %{size_download}\n" --max-time 20 https://export.arxiv.org/api/query?id_list=2610.22304
000 0
```

⇒ **直连被墙**（与既有记录一致：本机 `git fetch`/直连 github 同样被拦，只有 `api.github.com` 可达）。
因此**未取得四篇论文的标题核对**；本单按工单 §1 任务A 的允许条款执行：
「若拿不到正文，就实现**基础口径**并在 PR 里如实标注」——
本单实现的是**与论文无关的通用四策略骨架与折中表**，docstring 里只写"授粉点=哪个机制"，**不引用任何论文实验数值**。

## §8 · 边界（工单 §3）

- ❌ 不碰硬件、不写 PX4/ROS2/飞控文件（师傅 2026-10-15 暂停令仍在）；
- ❌ 不改 `lora_phy.py` / NEKO / apiserver / frontend；
- ❌ 不新增重依赖（**纯标准库 math/json**，连 numpy 都没用）；
- ❌ 不把论文实验数值当自己的结果（本报告只有本机实测数字）；
- ✅ 两个模块的中文 docstring 都写了「授粉点 → 落到哪一层 → 为什么这样取舍」。
