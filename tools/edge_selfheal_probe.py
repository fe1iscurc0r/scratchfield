"""边缘自愈 agent 最小探针（卷102 W102-05 · MIT 可参考，纯 Python 独立实现）。

模拟 sentinel 的「健康检查 → 故障检测 → 自动恢复 → 决策留痕」骨架：
连续失败超阈值触发恢复动作（退化为重启计数），恢复决策记录供决策层（Hermes）收割。

源结构对照（aqstack/sentinel）：
- pkg/health/health.go:13 Status 类型、:22 Check 函数签名（→ :25 CheckResult）、
  :38 NewChecker、:45 Register(name, check)、:59 Check(ctx) → HealthResponse
- pkg/collector/collector.go:18 NodeMetrics（CPU/磁盘/网络指标采集）
- pkg/consensus/raft_lite.go:21 NodeState 集群状态、:43 Decision / :54 DecisionType（分区容错决策）
本探针为单节点退化实现：分区容错/Raft 共识不实现，仅以决策记录结构对照。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

CheckFn = Callable[[], bool]


@dataclass
class RecoveryDecision:
    """恢复决策记录（对照 raft_lite.go:43 Decision：谁做的决策、做了什么）。"""
    check_name: str
    action: str
    ts: float


@dataclass
class EdgeSelfHeal:
    """边缘自愈监控器：心跳式健康检查 + 阈值触发恢复 + 决策留痕。"""

    failure_threshold: int = 3
    checks: dict[str, CheckFn] = field(default_factory=dict)
    consecutive_failures: int = 0
    state: str = "NORMAL"                 # NORMAL / UNHEALTHY / RECOVERING
    restart_count: int = 0
    decisions: list[RecoveryDecision] = field(default_factory=list)

    def register(self, name: str, check: CheckFn) -> None:
        """注册健康检查项（对照 health.go:45 Register）。"""
        self.checks[name] = check

    def _do_recovery(self, name: str, ts: float) -> None:
        """恢复动作（退化）：模拟重启目标进程，计数 +1，决策留痕。"""
        self.restart_count += 1
        self.decisions.append(RecoveryDecision(check_name=name, action="restart_process", ts=ts))
        self.state = "RECOVERING"
        self.consecutive_failures = 0

    def evaluate(self, now: float) -> dict[str, Any]:
        """按心跳周期评估全部检查（对照 health.go:59 Check → HealthResponse）。"""
        failed: list[str] = []
        for name, check in self.checks.items():
            try:
                ok = bool(check())
            except Exception:
                ok = False
            if not ok:
                failed.append(name)

        if failed:
            self.consecutive_failures += 1
            if self.consecutive_failures >= self.failure_threshold:
                self._do_recovery(failed[0], now)
            elif self.state != "RECOVERING":
                self.state = "UNHEALTHY"
        else:
            if self.state == "RECOVERING":
                self.state = "NORMAL"      # 恢复动作生效，回到健康态
            self.consecutive_failures = 0
        return {
            "state": self.state,
            "failed_checks": failed,
            "consecutive_failures": self.consecutive_failures,
            "restart_count": self.restart_count,
        }

    def summary(self) -> dict[str, Any]:
        return {
            "state": self.state,
            "restart_count": self.restart_count,
            "decisions": [(d.check_name, d.action, d.ts) for d in self.decisions],
        }