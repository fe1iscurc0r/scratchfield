"""射频大脑 · 自主闭环调度器（Phase 5）

把 scanner（频谱扫描）→ energy detect（能量检测）→ 候选信号表
→ feature/决策（LLM 或规则兜底）→ 解调 → 失败重试反馈环 串成一条
"无人值守"闭环：一次 run_sweep() 自动扫完整片频段，逐候选信号解码，
输出 SweepReport（含误检率统计）。

误检口径（验收：误检率 <10%）：
- 误检 FP：布点表标记无信号（噪声），但能量检测判为候选
- 漏检 FN：布点表标记有信号，但能量检测漏掉
- 误检率 = FP / 无信号窗口数；漏检率 = FN / 有信号窗口数
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field

from mcpserver.rf_brain.loop import LoopResult, run_loop
from mcpserver.rf_brain.scanner import CandidateSignal, ScanConfig, ScanResult, scan_spectrum


@dataclass
class SignalReport:
    """单个候选信号的闭环报告。"""
    center_freq_hz: float
    detected: bool
    ground_truth: str | None        # 仅测试台
    modulation: str                 # 最终收敛的调制方式
    converged: bool
    attempts: int
    history: list[dict] = field(default_factory=list)
    protocol: str | None = None     # 协议叶子（aprs/psk31/...，认不出=None）


@dataclass
class SweepReport:
    """整轮扫描闭环报告。"""
    candidates: list[SignalReport]
    n_windows: int                  # 观测窗口总数
    n_present: int                  # 布点表有信号的窗口数
    n_detected: int                 # 能量检测判为候选的窗口数
    false_positive: int             # 误检（噪声被判为信号）
    false_negative: int             # 漏检（信号没被检到）
    false_positive_rate: float      # 误检率（FP / 无信号窗口）
    false_negative_rate: float      # 漏检率（FN / 有信号窗口）
    wall_time_s: float


def run_sweep(config: ScanConfig, max_attempts: int = 3) -> SweepReport:
    """自主闭环主入口：扫描 → 候选表 → 逐候选闭环（决策+解调+重试）。

    单个候选复用 loop.run_loop（感知→决策→解调→失败换 alternatives 重试），
    扫描器只负责"发现"，不参与协议判定——新增协议对闭环主流程透明。
    """
    t0 = time.perf_counter()
    result: ScanResult = scan_spectrum(config)

    reports: list[SignalReport] = []
    for cand in result.candidates:
        loop: LoopResult = run_loop(
            cand.iq,
            sample_rate=config.sample_rate,
            center_freq=cand.center_freq_hz,
            ground_truth_modulation=cand.ground_truth,
            max_attempts=max_attempts,
        )
        reports.append(SignalReport(
            center_freq_hz=cand.center_freq_hz,
            detected=cand.detected,
            ground_truth=cand.ground_truth,
            modulation=loop.modulation,
            converged=loop.converged,
            attempts=loop.attempts,
            history=loop.history,
            protocol=loop.protocol,
        ))

    n_present = sum(1 for c in result.candidates if c.ground_truth)
    n_absent = result.n_windows - n_present
    fp = sum(1 for r in reports if not r.ground_truth and r.detected)
    fn = sum(1 for r in reports if r.ground_truth and not r.detected)

    return SweepReport(
        candidates=reports,
        n_windows=result.n_windows,
        n_present=n_present,
        n_detected=result.n_detected,
        false_positive=fp,
        false_negative=fn,
        false_positive_rate=(fp / n_absent) if n_absent else 0.0,
        false_negative_rate=(fn / n_present) if n_present else 0.0,
        wall_time_s=time.perf_counter() - t0,
    )
