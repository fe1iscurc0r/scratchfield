# 工单 256 完工报告 · 高阶正弦频率精修 + RFI 相关监测（扩既有，未重写）

> 执行：Trae（GitHub 线）｜ 日期：**2026-10-17** ｜ 基线：main `035d42e48d`
> 工单：`TRAE_WORKORDER_PROMPT_AGENT_256.md`（无线电线二）
> 交付：**2 个新模块 + 2 个测试文件 + 1 份口径文档 + 本报告**；`rfi_mitigation.py` / `rfi_statistical.py` **零改动**

## §0 · 交付物

| 文件 | 任务 | 说明 |
|---|---|---|
| `mcpserver/rf_brain/sine_refine.py` | A | 多音频率精修（analysis-by-synthesis，纯 numpy） |
| `mcpserver/rf_brain/rfi_correlated_monitor.py` | B | 双通道**相干**判据 + 三场景混淆矩阵 |
| `mcpserver/rf_brain/test_sine_refine.py` | A | 11 用例（含硬断言 + 确定性 + "不用真值初始化"守卫） |
| `mcpserver/rf_brain/test_rfi_correlated_monitor.py` | B | 12 用例（含硬断言 + 既有签名不变量） |
| `docs/rf-brain-互耦与弱周期信号口径-2026-10-17.md` | C | **60 行**（限 120），互耦适用边界 + 弱信号统计量口径 |
| `reports/workorder256_sine_refine_rfi_correlated_2026-10-17.md` | — | 本报告 |

**不变量**：`rfi_mitigation.py` / `rfi_statistical.py` **公开签名零改动** ——
PR 变更集不含这两个文件（即为证），且有测试 `test_existing_api_untouched` 逐参数名核对。

## §1 · 任务A · 正弦频率精修

**算法**：`power_spectrum` 取功率最大的 K 个 bin 作初值（允许相邻 bin）→ 迭代
「{cos,−sin} 最小二乘拟合幅度相位 → 减掉其它音得残差 → 在三段网格上最大化相关模长更新频率」→
最大频率改动 < 容差即收敛。**初值绝不用真值**（由 `test_seeds_do_not_use_truth` 守住：
给不给真值，初值/收敛路径/迭代次数必须完全一致，只有 RMSE 字段允许不同）。

**实测**（`--demo`，fs=1000 Hz、N=1024、bin=0.9766 Hz、两音间隔 **1.23 bin**、SNR 30 dB）：

| 项 | 值 |
|---|---|
| 真值 | 100.0 / 101.2 Hz |
| FFT 初值 | 99.6094 / 101.5625 Hz |
| 精修结果 | **100.0016 / 101.1979 Hz** |
| `rmse_fft` | **0.376825 Hz** |
| `rmse_refined` | **0.001840 Hz**（降 **99.5%**） |
| `iterations` | 11（收敛曲线单调下降：0.298 → 0.112 → 0.0267 → 0.0146 → 0.00476 …） |

⚠️ **未实现论文 2610.21643 的高阶（导数项）模型**：正文不可达（本机直连 arxiv 被墙，见 §5）。
按工单 §1 任务A 允许条款实现**基础迭代精修**，此处如实标注差异。

## §2 · 任务B · RFI 相关监测（新增而非重写，理由如下）

仓内已有三种判据，本模块补的是**第四种、且信息正交**的量：

| 判据 | 函数 | 抓什么 | 抓不到什么 |
|---|---|---|---|
| 单通道能量峰 | `detect_rfi_narrowband` | 强于噪声底的窄带峰 | **分不清真信号与本地干扰** |
| 双通道能量失衡 | `detect_rfi_dual_channel` | 极化不对称（只进一路的强干扰） | 两路都有（功率相近）时无判据 |
| 统计子带检测 | `rfi_statistical.StatisticalRFIDetector` | 子带能量持续性 | 无跨通道相关性 |
| **双通道相干（本模块）** | `coherence_spectrum` | **两路是否同源**（相干⇒真信号，不相干⇒本地干扰） | 帧数少时相干估计方差大 |

**统计量**：分帧（Hann 窗、hop 50%）→ 平均互谱 → 幅度平方相干
`γ²(f) = |⟨X_a X_b*⟩|² / (⟨|X_a|²⟩⟨|X_b|²⟩) ∈ [0,1]`；判据 = 能量超底噪 **且** `γ² < 阈值`。

**实测**（fs=1000、N=4096、干扰 180 Hz 仅进 ch_a、真信号 120 Hz 两路同源相位差 0.4 rad、SNR 12 dB）：

| 场景 | 相关判据 | 单通道能量基线 | γ² |
|---|---|---|---|
| `local_only` | 检测率 **100%** | 检测率 100% | γ²@rfi = **0.0582**（不相干 ✓） |
| `signal_only` | 误报 **0%** | 误报 **100%**（把真信号当干扰） | γ²@signal = **0.9985**（相干 ✓） |
| **`mixed`** | 检测率 100% / 误报 **0%** | 检测率 100% / 误报 **100%** | γ²@rfi 0.0565 / γ²@signal 0.9990 |

**硬断言**：混合场景下相关判据的误报率（**0.0%**）**严格低于**单通道能量判据（**100.0%**）⇒ ✅ **PASS**，
且检测率同时保持 100%（不是靠"什么都不报"换来的低误报）。

> 评估集口径（写明以免被质疑）：正类 = RFI 音 ±1 bin，负类 = 真信号音 ±1 bin（与正类重叠时以正类为准）。
> 因此"误报"专指**把真信号判成干扰**，正是本任务要区分的那件事。

## §3 · 任务C · 口径文档（60 行）

`docs/rf-brain-互耦与弱周期信号口径-2026-10-17.md`：

- **互耦边界检查清单 5 条**：隔离度（S21 最差值）/ 幅度线性（泄漏随激励的斜率）/ 时不变性（两次标定差异）/
  通道相位稳定性 / 动态范围，每条带阈值与"不满足时怎么办"；并给出**何时必须放弃线性模型**的三条红线
  （互调产物 / 压缩曲线 / 温度姿态差异 > 6 dB）；
- **弱周期信号 6 条口径**：先判噪声是否高斯（峰度）→ 用中位数+MAD 而非均值+std → 折叠累积 → 累积长度与
  相干时间匹配 → 非高斯下的秩/符号统计量 → 必须同时报检测率与误报率；
- 明确标注「本文件为口径整理，**未做数值复现**」，且两篇论文正文均未读到。

## §4 · 验收（工单 §2 四条，原始输出）

```
# 1) 精修级可跑且指标可读
$ python -m mcpserver.rf_brain.sine_refine --demo > /tmp/wo256_a.txt
$ grep -E "rmse_fft|rmse_refined|iterations" /tmp/wo256_a.txt | wc -l
3                       # ≥3 ✓

# 2) 相关监测混淆矩阵
$ python -m mcpserver.rf_brain.rfi_correlated_monitor --demo > /tmp/wo256_b.txt
$ grep -E "confusion|detection_rate|false_alarm" /tmp/wo256_b.txt | wc -l
6                       # ≥3 ✓

# 3) 既有实现未被重写
$ python -c "import mcpserver.rf_brain.rfi_mitigation as m; need=[...]; print([n for n in need if callable(getattr(m,n,None))])"
['power_spectrum', 'detect_rfi_narrowband', 'detect_rfi_dual_channel', 'mitigate_rfi']   # 4 个全在 ✓

# 4) 测试
$ python -m pytest mcpserver/rf_brain/test_rfi_correlated_monitor.py mcpserver/rf_brain/test_sine_refine.py -q
23 passed in 0.42s      # ✓
```

**ruff**（4 个新 py 文件）：`All checks passed!`

## §5 · ⚠️ 论文不可达（如实记录，同 WO-255）

```
$ curl ... https://export.arxiv.org/api/query?id_list=2610.21643
000 0        # 直连被墙；本机只有 api.github.com 可达
```

⇒ 2610.21643（精修模型）/ 2610.20847（相关监测）/ 2610.22197 / 2610.20848 四篇的**标题与正文均未核对**。
本单实现的是**通用工程骨架**（迭代精修 / 相干判据 / 口径清单），docstring 只写"授粉点 = 哪个机制"，
**不引用任何论文数值**。

## §6 · 边界（工单 §3）

- ❌ 不碰硬件、不写飞控/ROS2/PX4（暂停令仍在）；
- ❌ 不改既有 rfi 模块签名与默认行为；❌ 不复制既有实现魔改成新文件；
- ❌ **不用 scipy / torch / sklearn**（实测：两模块仅 import `numpy` + 标准库）；
- ❌ 不把论文实验数值当本仓结果（上面所有数字都是本仓构造场景实测）。
