"""白盒算法产物生成（工单246 · 对应 SeisEvo 的 "standalone white-box algorithm"）。

SeisEvo 的第四条机制，也是最容易被忽略的一条：

> The output is neither an agent system nor a neural network,
> but a **standalone white-box algorithm that requires no agent or neural network at inference time**.

本模块据此生成一份**自包含**的 Python 产物：

- 只依赖 `numpy`（本仓既有依赖），**不 import** 本仓任何模块、不依赖 harness、不依赖 LLM；
- 内联算法本体（检测 + 陷波 + 可选 LMS），与 `rf_brain/rfi_mitigation.py` 的数学**逐式一致**；
- 带 `PROVENANCE`：这组参数是**怎么被搜出来的**、在哪些场景上读数多少、过没过约束门。

⇒ 因此它可以被打包进固件工程、被同事直接读、被单测回归 —— 而不是"一个要连 agent 才能跑的东西"。

产物的正确性判据（写在 `tests/test_rf_evolve.py`）：**在同样的场景上，产物跑出的 S/N 提升
必须与 harness 报告的读数一致（容差内）**。若不成立，说明产物不是真货。
"""

from __future__ import annotations

import json
import pprint
from pathlib import Path

#: 产物模板。`{params}` / `{provenance}` / `{header}` 由 `render()` 填充。
_TEMPLATE = '''"""{header}

⚠️ 本文件由 `mcpserver/rf_evolve/codegen.py` **生成**，请勿手改 —— 要改就改编辑面参数并重跑演化。

它是 SeisEvo（arXiv:2608.18272v1）意义上的**白盒产物**：
推理期不需要 agent、不需要神经网络、不需要本仓任何模块 —— 只需要 `numpy`。
"""
from __future__ import annotations

import json

import numpy as np

#: 搜索得到的参数（= 本算法的全部自由量）
PARAMS = {params}

#: 这组参数是怎么来的（出处、读数、约束），由演化 harness 写入，便于审计
PROVENANCE = {provenance}


# --------------------------------------------------------------------------- 算法本体
def power_spectrum(signal: np.ndarray, sample_rate: float):
    """实信号 -> 单边功率谱（Hz, 功率）。不做归一化（保留绝对量级供阈值判定）。"""
    x = np.asarray(signal, dtype=float)
    if x.ndim != 1 or x.size == 0:
        raise ValueError("signal 必须为非空一维实信号")
    n = x.size
    x_fft = np.fft.rfft(x)
    freqs = np.fft.rfftfreq(n, 1.0 / float(sample_rate))
    return freqs.astype(float), np.abs(x_fft) ** 2


def detect_narrowband(signal: np.ndarray, sample_rate: float, prominence_db: float):
    """窄带峰检测：稳健中位数估计噪声底，超过 prominence_db 的局部极大值判为干扰。"""
    freqs, power = power_spectrum(signal, sample_rate)
    noise = float(np.median(power))
    if noise <= 0.0:
        noise = 1e-12
    thresh = noise * (10.0 ** (prominence_db / 10.0))
    peaks = []
    for i in np.flatnonzero(power > thresh):
        if i == 0 or i == power.size - 1:
            continue
        if power[i] >= power[i - 1] and power[i] >= power[i + 1]:
            peaks.append(float(freqs[i]))
    return peaks


def notch_biquad(f0: float, sample_rate: float, bw_hz: float):
    """2 阶 Butterworth 带阻（陷波）系数；极半径 r 随带宽收窄趋近 1。"""
    sr = float(sample_rate)
    f0 = float(f0)
    bw = float(bw_hz)
    if not 0.0 < f0 < sr / 2.0:
        raise ValueError(f"陷波频率越界: {{f0}}（须在 0..{{sr / 2}} Hz）")
    if bw <= 0.0:
        raise ValueError(f"带宽必须 > 0: {{bw}}")
    w0 = 2.0 * np.pi * f0 / sr
    r = float(np.clip(1.0 - np.pi * bw / sr, 0.0, 0.9999))
    b = np.array([1.0, -2.0 * np.cos(w0), 1.0])
    a = np.array([1.0, -2.0 * r * np.cos(w0), r * r])
    return b, a


def biquad_lfilter(b: np.ndarray, a: np.ndarray, x: np.ndarray) -> np.ndarray:
    """直接 II 型转置 biquad（2 阶）。逐样本循环，与仓内实现同式。"""
    b = np.asarray(b, dtype=float) / a[0]
    a = np.asarray(a, dtype=float) / a[0]
    x = np.asarray(x, dtype=float)
    y = np.zeros(x.size)
    z1 = z2 = 0.0
    b0, b1, b2 = b[0], b[1], b[2]
    a1, a2 = a[1], a[2]
    for i in range(x.size):
        xi = x[i]
        yi = b0 * xi + z1
        z1 = b1 * xi - a1 * yi + z2
        z2 = b2 * xi - a2 * yi
        y[i] = yi
    return y


def adaptive_notch(signal: np.ndarray, sample_rate: float, f0: float, mu: float) -> np.ndarray:
    """LMS 单频自适应陷波：以 sin/cos 正交参考重构干扰并从输入减去。"""
    x = np.asarray(signal, dtype=float)
    t = np.arange(x.size) / float(sample_rate)
    ref_sin = np.sin(2.0 * np.pi * f0 * t)
    ref_cos = np.cos(2.0 * np.pi * f0 * t)
    w1 = w2 = 0.0
    two_mu = 2.0 * float(mu)
    y = np.zeros(x.size)
    for i in range(x.size):
        err = x[i] - (w1 * ref_sin[i] + w2 * ref_cos[i])
        w1 += two_mu * err * ref_sin[i]
        w2 += two_mu * err * ref_cos[i]
        y[i] = err
    return y


def mitigate(signal: np.ndarray, sample_rate: float, reference=None):
    """端到端：检测干扰频点 -> 逐频点陷波（固定或自适应）。返回 (cleaned, detected_freqs)。"""
    x = np.asarray(signal, dtype=float)
    sr = float(sample_rate)
    bw = float(PARAMS["notch_bw_hz"]) if PARAMS["notch_bw_hz"] else sr / 1000.0
    freqs = detect_narrowband(x, sr, float(PARAMS["prominence_db"]))
    cleaned = x.copy()
    for f0 in freqs:
        if PARAMS["adaptive"]:
            cleaned = adaptive_notch(cleaned, sr, f0, float(PARAMS["mu"]))
        else:
            b, a = notch_biquad(f0, sr, bw)
            cleaned = biquad_lfilter(b, a, cleaned)
    return cleaned, freqs


def snr_db(signal: np.ndarray, reference: np.ndarray) -> float:
    """相对参考信号的 S/N（dB）：P(参考) / P(残差)。与仓内 _snr_db 同式。"""
    s = np.asarray(signal, dtype=float)
    r = np.asarray(reference, dtype=float)
    sp = float(np.mean(r ** 2))
    rp = float(np.mean((s - r) ** 2))
    if rp <= 0.0:
        return 200.0
    return 10.0 * np.log10(sp / rp + 1e-12)


if __name__ == "__main__":  # pragma: no cover - 自检入口
    _sr = 1_000_000.0
    _n = 4096
    _t = np.arange(_n) / _sr
    _sweep = 100_000.0 / (_n / _sr)
    _ref = 0.5 * np.sin(2.0 * np.pi * (_sweep / 2.0) * _t ** 2) + 0.08 * np.random.default_rng(1).standard_normal(_n)
    _dirty = _ref + 0.6 * np.sin(2.0 * np.pi * 180_000.0 * _t + 0.3)
    _clean, _f = mitigate(_dirty, _sr)
    print(json.dumps({{"detected": len(_f), "improvement_db": round(snr_db(_clean, _ref) - snr_db(_dirty, _ref), 4)}},
                     ensure_ascii=False))
'''


def render(params: dict, provenance: dict, *, header: str) -> str:
    """把一组参数渲染成**自包含**的白盒算法源码。"""
    # ⚠️ 用 pprint 而不是 json：产物是 **Python 源码**，json 的 `null/true/false`
    #    在这里是非法字面量（实测踩过：产物 exec 时 `NameError: name 'null' is not defined`）。
    return _TEMPLATE.format(
        header=header,
        params=pprint.pformat(params, width=100, sort_dicts=False),
        provenance=pprint.pformat(provenance, width=100, sort_dicts=False),
    )


def render_from_result(result, *, header: str = "") -> str:
    """从 `evolve.EvolveResult` 直接渲染（带上读数与约束信息）。"""
    best = result.best
    prov = {
        "found_by": f"mcpserver.rf_evolve（提案器={result.proposal_mode}，"
                    f"{result.config['generations']} 代，seed={result.config['seed']}）",
        "task": result.space["task"],
        "evolved_target": result.space["target"],
        "frozen_components": result.space["frozen"],
        "baseline_params": result.baseline["params"],
        "baseline_score": result.baseline["score"],
        "best_score": best["score"],
        "gate_stats": result.gate_stats,
        "note": ("本产物推理期不需要 agent / 神经网络 / 本仓模块；"
                 "参数由约束门 + 执行打分选出，读数见 best_score。"),
    }
    hdr = header or f"白盒 RFI 抑制算法（演化所得）— 任务：{result.space['task']}"
    return render(best["params"], prov, header=hdr)


def write(path: str | Path, source: str) -> Path:
    """落盘（强制 LF —— 与新文件行尾纪律一致）。"""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(source, encoding="utf-8", newline="\n")
    return p
