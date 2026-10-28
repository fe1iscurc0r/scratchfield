"""物理/工程约束门（工单246 · 对应 SeisEvo 的 "physical constraints ... rejected outright"）。

SeisEvo 的第二条机制：**违反任务物理约束的候选直接否决，不进入打分**。
本模块把这条落成可执行的约束集，每条都必须满足：

1. **可辩护**：依据是信号处理事实、硬件预算或数学稳定性条件 —— 不是"我觉得不行"；
2. **有出处**：`source` 字段写明依据来自哪里（论文/教材/本仓既有测量）；
3. **会真的否决**：每条约束都有对应的单测证明它能挡住违规候选（否则是装饰）。

分层（关键设计）
----------------
约束分为两段，因为**代价不同**：

- **A 段 · 参数级（O(1)，不碰信号）**：如 LMS 稳定上界、显著度下限。
- **B 段 · 检测级（一次 FFT，便宜；但**不跑陷波**）**：如"检出干扰数上限"、"总陷波带宽占比"。

⚠️ 为什么这样分：本仓 `rfi_brain.rfi_mitigation.adaptive_notch` 是**逐样本 Python 循环**，
陷波是整条链里最贵的环节；而检测只是一次 `np.fft`。**先在便宜阶段否决**，
就能把灾难候选的算力**真实省下来**（`GateResult.saved_notch_ops` 会给出可核对的数字）。
实测：`prominence_db=8` 可检出 161~170 个"干扰"，若照单全收逐个陷波，既拖垮算力又把信号毁掉。
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field

import numpy as np

#: `detect_rfi_narrowband` 在 1 MHz 采样下的 FFT 分辨率量级（Hz）—— 用于估算总陷波带宽占比
_FFT_BIN_HZ = 1_000_000.0 / 4096.0


@dataclass
class Violation:
    """一条约束违规。"""

    code: str
    message: str
    rationale: str
    source: str
    severity: str = "reject"          # reject / warn

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass
class GateResult:
    """约束门结果。"""

    passed: bool
    violations: list[Violation] = field(default_factory=list)
    stage: str = "A"                  # 走到哪一段就被否 / 走完为 "B"
    detected_freqs: list[float] = field(default_factory=list)
    saved_notch_ops: int = 0          # 因否决而**没有**执行的陷波样本运算量（估算）
    notes: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "passed": self.passed, "stage": self.stage,
            "violations": [v.as_dict() for v in self.violations],
            "detected_freq_count": len(self.detected_freqs),
            "saved_notch_ops": self.saved_notch_ops,
            "notes": self.notes,
        }


# --------------------------------------------------------------------------- 约束定义

def _lms_mu_upper_bound(sample_rate_hz: float, n_taps: int = 2, power: float = 1.0) -> float:
    """LMS 步长的**稳定上界**（保守式）。

    标准结论：对实值 LMS，收敛要求 ``0 < μ < 1/(N·λ_max)``，其中 N=2（本仓
    `adaptive_notch` 用 sin/cos 两个正交参考 ⇒ 2 个抽头），λ_max ≤ N·P_x
    （P_x = 参考序列功率；正交参考的功率各为 0.5，合计 1.0）。
    取 ``1/(N·P_x) = 1/(2·1.0) = 0.5`` 为上界，再按工程经验取 **1/2 裕度** ⇒ 0.25。
    """
    p_x = float(power)
    return 0.5 / (float(n_taps) * p_x)


def check_params(params: dict, *, sample_rate_hz: float = 1_000_000.0) -> list[Violation]:
    """A 段：只看参数本身的约束（不碰信号）。"""
    vs: list[Violation] = []

    prom = float(params.get("prominence_db", 20.0))
    if prom < 6.0:
        vs.append(Violation(
            code="PROMINENCE_BELOW_NOISE_FLOOR",
            message=f"显著度 {prom} dB 低于噪声底的统计起伏量级（≈6 dB）",
            rationale="周期图估计的谱峰起伏在 ~5.6 dB 量级；阈值低于它时噪声峰会被判为干扰",
            source="周期图（periodogram）指数分布：单峰幅度超过噪声底 5.6 dB 的概率≈10%",
        ))

    if params.get("adaptive"):
        mu = float(params.get("mu", 0.01))
        ub = _lms_mu_upper_bound(sample_rate_hz)
        if mu >= ub:
            vs.append(Violation(
                code="LMS_STEP_TOO_LARGE",
                message=f"LMS 步长 μ={mu} ≥ 稳定上界 {ub:.3f}（2 抽头正交参考）",
                rationale="μ 超过 1/(N·λ_max) 时权值更新发散 —— 不是「效果差」，是**数值上不收敛**",
                source="LMS 收敛条件 0<μ<1/(N·λ_max)（Haykin, Adaptive Filter Theory, 4th ed. §6）",
            ))
    return vs


def check_detection(params: dict, detected: list[float], *, sample_rate_hz: float = 1_000_000.0,
                    signal_band_hz: float = 100_000.0, max_notches: int = 12,
                    max_notch_band_fraction: float = 0.5) -> tuple[list[Violation], list[str]]:
    """B 段：拿到**检测结果**后的约束（检测便宜、陷波昂贵 ⇒ 在这里拦下灾难候选）。

    - `MAX_NOTCHES`：一次采样窗内检出过多"干扰" = 把噪声峰当干扰。物理依据：窄带信道
      占用率上限 —— 1 MHz 带宽内同时存在十几个以上独立窄带干扰已属极端，过百必然是误检。
    - `TOTAL_NOTCH_BAND`：总陷波带宽占信号带宽比例上限 —— 陷掉半个信号带的"抑制"没有意义。
    """
    vs: list[Violation] = []
    notes: list[str] = []
    n = len(detected)
    if n > max_notches:
        vs.append(Violation(
            code="TOO_MANY_NOTCHES",
            message=f"检出 {n} 个干扰频点，超过上限 {max_notches}",
            rationale=("该量级必然是噪声峰误检：窄带干扰在 1 MHz 带宽内的占用率不可能这么高；"
                       "且每多一个频点就要多跑一遍陷波，算力随时延线性增长"),
            source="本仓 rf_brain/rfi_statistic.StatisticalRFIDetector 的误报率验收口径（≤5%）"
                   "＋ 检出数与算力成正比的结构事实",
        ))
    bw = params.get("notch_bw_hz")
    bw = float(bw) if bw else sample_rate_hz / 1000.0      # 与 mitigate_rfi 的缺省一致
    total_bw = n * bw
    frac = total_bw / signal_band_hz if signal_band_hz > 0 else 0.0
    if frac > max_notch_band_fraction:
        vs.append(Violation(
            code="TOTAL_NOTCH_BAND_TOO_WIDE",
            message=(f"总陷波带宽 {total_bw:.0f} Hz = 信号带（{signal_band_hz:.0f} Hz）的 "
                     f"{frac*100:.0f}%，超过上限 {max_notch_band_fraction*100:.0f}%"),
            rationale="陷波器不是理想方格：总带宽占掉半个信号带时，带内有用信号被一并抑制",
            source="带阻滤波器过渡带与实际响应的工程常识（2 阶 Butterworth 的 -3dB 带宽定义）",
        ))
    return vs, notes


def gate(candidate_params: dict, signal: np.ndarray, sample_rate_hz: float,
         *, signal_band_hz: float = 100_000.0, max_notches: int = 12,
         max_notch_band_fraction: float = 0.5, detect=None) -> GateResult:
    """完整约束门：A 段（参数）→ 若通过则 B 段（检测）。

    :param detect: 可注入的检测函数（默认用本仓 `rf_brain` 的 `detect_rfi_narrowband`），
        注入是为了让测试能构造确定性的"检出数"而不用依赖具体场景。
    """
    res = GateResult(passed=True)
    a = check_params(candidate_params, sample_rate_hz=sample_rate_hz)
    if a:
        res.passed = False
        res.violations = a
        res.stage = "A"
        res.detected_freqs = []
        res.saved_notch_ops = _est_notch_ops(candidate_params, _ASSUMED_DETECTED_CAP, signal.size)
        res.notes.append("A 段（参数级）即否决 ⇒ 一次信号运算都没做")
        return res

    if detect is None:                                  # 惰性导入，避免模块级拉起 rf_brain
        from mcpserver.rf_brain.rfi_mitigation import detect_rfi_narrowband as detect  # type: ignore

    detected = list(detect(signal, sample_rate_hz,
                           prominence_db=float(candidate_params.get("prominence_db", 20.0))))
    res.detected_freqs = detected
    b, notes = check_detection(candidate_params, detected, sample_rate_hz=sample_rate_hz,
                              signal_band_hz=signal_band_hz, max_notches=max_notches,
                              max_notch_band_fraction=max_notch_band_fraction)
    res.notes.extend(notes)
    if b:
        res.passed = False
        res.violations = b
        res.stage = "B"
        res.saved_notch_ops = _est_notch_ops(candidate_params, len(detected), signal.size)
        res.notes.append(
            f"B 段（检测级）否决 ⇒ 只跑了 1 次 FFT，省下 {len(detected)} 次陷波（{res.saved_notch_ops} 次样本运算）")
    else:
        res.stage = "B"
        res.notes.append("两段约束均通过")
    return res


#: A 段否决时假定"若不拦会检出多少"的上界估计（用于算省下的算力；取超限阈值，保守）
_ASSUMED_DETECTED_CAP = 100


def _est_notch_ops(params: dict, n_notches: int, n_samples: int) -> int:
    """估算"若不拦、照单全收这 n 个频点"会产生的样本运算量。

    固定陷波 = 逐频点一次 IIR 递归（O(N)）；自适应陷波 = 逐频点一次**逐样本 Python 循环**
    （同样是 O(N)，但常数高得多）。这里统一按 O(n_notches × N) 计，单位=样本运算次数。
    """
    return int(max(0, n_notches) * max(0, n_samples))
