"""
屏幕感知 Metrics 监控统计
提供Prometheus风格的性能指标
"""

import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Dict, List


@dataclass
class MetricCounter:
    """计数器指标"""
    name: str
    help: str
    value: int = 0

    def inc(self, amount: int = 1):
        """增加计数"""
        self.value += amount

    def get(self) -> int:
        """获取当前值"""
        return self.value

    def reset(self):
        """重置计数"""
        self.value = 0


@dataclass
class MetricHistogram:
    """直方图指标（用于记录耗时）"""
    name: str
    help: str
    buckets: list[float] = field(default_factory=lambda: [0.1, 0.5, 1.0, 2.0, 5.0, 10.0])
    sum: float = 0.0
    count: int = 0
    bucket_counts: dict[float, int] = field(default_factory=dict)

    def __post_init__(self):
        """初始化bucket计数"""
        for bucket in self.buckets:
            self.bucket_counts[bucket] = 0

    def observe(self, value: float):
        """记录一个观测值"""
        self.sum += value
        self.count += 1

        for bucket in self.buckets:
            if value <= bucket:
                self.bucket_counts[bucket] += 1

    def get_stats(self) -> dict[str, Any]:
        """获取统计信息"""
        avg = self.sum / self.count if self.count > 0 else 0
        return {
            "sum": self.sum,
            "count": self.count,
            "avg": avg,
            "buckets": self.bucket_counts,
        }


class ProactiveVisionMetrics:
    """主动视觉系统指标收集器"""

    def __init__(self):
        # 计数器
        self.checks_total = MetricCounter(
            name="proactive_vision_checks_total",
            help="Total number of screen checks performed"
        )

        self.checks_skipped = MetricCounter(
            name="proactive_vision_checks_skipped_total",
            help="Total number of screen checks skipped due to no change"
        )

        self.rules_triggered = MetricCounter(
            name="proactive_vision_rules_triggered_total",
            help="Total number of rules triggered"
        )

        self.rules_matched = defaultdict(lambda: MetricCounter(
            name="proactive_vision_rule_matched_total",
            help="Total number of times a specific rule was matched"
        ))

        self.screenshot_errors = MetricCounter(
            name="proactive_vision_screenshot_errors_total",
            help="Total number of screenshot/analysis errors"
        )

        self.notification_sent = MetricCounter(
            name="proactive_vision_notifications_sent_total",
            help="Total number of notifications sent to frontend"
        )

        self.notification_failed = MetricCounter(
            name="proactive_vision_notifications_failed_total",
            help="Total number of failed notification attempts"
        )

        # 直方图（耗时）
        self.screenshot_duration = MetricHistogram(
            name="proactive_vision_screenshot_duration_seconds",
            help="Time spent taking and analyzing screenshot"
        )

        self.llm_duration = MetricHistogram(
            name="proactive_vision_llm_duration_seconds",
            help="Time spent on LLM analysis for rule matching"
        )

        self.total_check_duration = MetricHistogram(
            name="proactive_vision_check_duration_seconds",
            help="Total time spent on one complete check cycle"
        )

    def record_check(self, duration: float, skipped: bool = False):
        """记录一次检查"""
        self.checks_total.inc()
        if skipped:
            self.checks_skipped.inc()
        else:
            self.total_check_duration.observe(duration)

    def record_screenshot(self, duration: float, error: bool = False):
        """记录截图耗时"""
        if error:
            self.screenshot_errors.inc()
        else:
            self.screenshot_duration.observe(duration)

    def record_llm_analysis(self, duration: float):
        """记录LLM分析耗时"""
        self.llm_duration.observe(duration)

    def record_rule_triggered(self, rule_id: str):
        """记录规则触发"""
        self.rules_triggered.inc()
        self.rules_matched[rule_id].inc()

    def record_notification(self, success: bool):
        """记录通知发送"""
        if success:
            self.notification_sent.inc()
        else:
            self.notification_failed.inc()

    def get_all_metrics(self) -> dict[str, Any]:
        """获取所有指标"""
        rule_stats = {}
        for rule_id, counter in self.rules_matched.items():
            rule_stats[rule_id] = counter.get()

        return {
            "counters": {
                "checks_total": self.checks_total.get(),
                "checks_skipped": self.checks_skipped.get(),
                "rules_triggered_total": self.rules_triggered.get(),
                "screenshot_errors": self.screenshot_errors.get(),
                "notifications_sent": self.notification_sent.get(),
                "notifications_failed": self.notification_failed.get(),
            },
            "rules": rule_stats,
            "histograms": {
                "screenshot_duration": self.screenshot_duration.get_stats(),
                "llm_duration": self.llm_duration.get_stats(),
                "total_check_duration": self.total_check_duration.get_stats(),
            },
            "derived": {
                "skip_rate_percent": (
                    (self.checks_skipped.get() / self.checks_total.get() * 100)
                    if self.checks_total.get() > 0
                    else 0
                ),
                "notification_success_rate_percent": (
                    (self.notification_sent.get() / (self.notification_sent.get() + self.notification_failed.get()) * 100)
                    if (self.notification_sent.get() + self.notification_failed.get()) > 0
                    else 0
                ),
            },
        }

    def get_prometheus_format(self) -> str:
        """获取Prometheus格式的指标"""
        lines = []

        # 计数器
        lines.append(f"# HELP {self.checks_total.name} {self.checks_total.help}")
        lines.append(f"# TYPE {self.checks_total.name} counter")
        lines.append(f"{self.checks_total.name} {self.checks_total.get()}")

        lines.append(f"# HELP {self.checks_skipped.name} {self.checks_skipped.help}")
        lines.append(f"# TYPE {self.checks_skipped.name} counter")
        lines.append(f"{self.checks_skipped.name} {self.checks_skipped.get()}")

        lines.append(f"# HELP {self.rules_triggered.name} {self.rules_triggered.help}")
        lines.append(f"# TYPE {self.rules_triggered.name} counter")
        lines.append(f"{self.rules_triggered.name} {self.rules_triggered.get()}")

        # 按规则的触发次数
        for rule_id, counter in self.rules_matched.items():
            lines.append(f'{counter.name}{{rule_id="{rule_id}"}} {counter.get()}')

        # 直方图
        for name, histogram in [
            ("screenshot", self.screenshot_duration),
            ("llm", self.llm_duration),
            ("total_check", self.total_check_duration),
        ]:
            lines.append(f"# HELP {histogram.name} {histogram.help}")
            lines.append(f"# TYPE {histogram.name} histogram")
            lines.append(f"{histogram.name}_sum {histogram.sum}")
            lines.append(f"{histogram.name}_count {histogram.count}")

            for bucket, count in histogram.bucket_counts.items():
                lines.append(f'{histogram.name}_bucket{{le="{bucket}"}} {count}')
            lines.append(f'{histogram.name}_bucket{{le="+Inf"}} {histogram.count}')

        return "\n".join(lines)


# 全局单例
_metrics: ProactiveVisionMetrics = None


def get_metrics() -> ProactiveVisionMetrics:
    """获取Metrics单例"""
    global _metrics
    if _metrics is None:
        _metrics = ProactiveVisionMetrics()
    return _metrics
