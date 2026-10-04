"""DreamLedger 消息信用账本（A26 · NEKO/LoRa 网关通信可靠性追踪）。

依据 docs/paper-round2-2026-08-30/digests/授粉点-统一.md 中 gx-4b 授粉 3：
「DreamLedger 把世界模型预测的可靠性变成可审计的执行结算信用文件——每次使用
预测后对照真实结果更新信用值，低信用预测触发额外观测或缩短依赖范围」→
对 ESP32 MQTT-SN / LoRa 网关的迁移：每条消息按「确认/超时」记账，节点可信度
滚动更新，低可信节点消息降级处理（触发重路由/加冗余）。

机制：
- 信用文件：每条消息 submit() 后进入 pending，confirm()/timeout() 结算
- 节点可信度：EWMA 滚动更新（ack=1 / timeout=0）
- 降级处理：信用 < threshold 的节点，routing_decision 走中继/加冗余

验收（SPEC A26）：模拟丢包节点信用分正确下降，重路由决策生效。

运行：
  python tools/message_ledger.py
"""
from __future__ import annotations

from dataclasses import dataclass, field

DEFAULT_CREDIT = 0.5   # 未知节点初始信用（中性）
ALPHA = 0.3            # EWMA 平滑系数
DOWNGRADE_THRESHOLD = 0.35


@dataclass
class MessageLedger:
    """Agent 间消息可信度记账（信用文件）。"""

    alpha: float = ALPHA
    threshold: float = DOWNGRADE_THRESHOLD
    credit: dict[str, float] = field(default_factory=dict)
    pending: dict[str, str] = field(default_factory=dict)  # msg_id -> sender
    history: list[dict] = field(default_factory=list)      # 可审计结算流水
    settled: int = 0
    timed_out: int = 0

    def credit_of(self, sender: str) -> float:
        return self.credit.get(sender, DEFAULT_CREDIT)

    def submit(self, msg_id: str, sender: str) -> None:
        """登记一条待结算消息。"""
        self.pending[msg_id] = sender

    def confirm(self, msg_id: str) -> None:
        """消息被确认（到达/ACK）→ 结算 ack=1。"""
        self._settle(msg_id, ack=True)

    def timeout(self, msg_id: str) -> None:
        """消息超时（丢）→ 结算 ack=0。"""
        self._settle(msg_id, ack=False)

    def _settle(self, msg_id: str, ack: bool) -> None:
        sender = self.pending.pop(msg_id, None)
        if sender is None:
            return  # 未知消息或已结算，忽略
        c = self.credit_of(sender)
        new_c = self.alpha * (1.0 if ack else 0.0) + (1.0 - self.alpha) * c
        self.credit[sender] = new_c
        # 可审计结算流水：记录每条消息的结算结果与结算后信用
        self.history.append({
            "seq": len(self.history),
            "msg_id": msg_id,
            "sender": sender,
            "ack": bool(ack),
            "credit_after": new_c,
        })
        if ack:
            self.settled += 1
        else:
            self.timed_out += 1

    def audit_records(self, sender: str | None = None) -> list[dict]:
        """导出审计流水（可按节点过滤），对应 DreamLedger 的「可审计结算」。"""
        if sender is None:
            return list(self.history)
        return [r for r in self.history if r["sender"] == sender]

    def downgraded(self, sender: str) -> bool:
        """信用低于阈值 → 降级处理。"""
        return self.credit_of(sender) < self.threshold

    def routing_decision(self, sender: str, candidate_relays: list[tuple[str, float]]) -> dict:
        """路由决策：低信用节点走最可靠中继（重路由）；高信用节点直连。

        candidate_relays: [(relay_name, reliability_0_1)]，可靠性越高中继越优。
        返回 dict：mode ∈ {direct, relay}，并附理由与信用分。
        """
        credit = self.credit_of(sender)
        if self.downgraded(sender):
            if candidate_relays:
                best = max(candidate_relays, key=lambda r: r[1])
                return {"mode": "relay", "relay": best[0], "credit": credit, "reason": "low_credit"}
            return {"mode": "relay", "relay": None, "credit": credit, "reason": "low_credit_no_relay"}
        return {"mode": "direct", "credit": credit, "reason": "trusted"}


def demo() -> None:
    """演示：可信节点 vs 丢包节点，各自结算后看信用与路由决策。"""
    ledger = MessageLedger()
    relays = [("relay-a", 0.9), ("relay-b", 0.7)]

    # 可信节点：10 条消息全确认
    for i in range(10):
        ledger.submit(f"t{i}", "node-trusted")
        ledger.confirm(f"t{i}")

    # 丢包节点：10 条消息只确认 2 条，8 条超时
    for i in range(10):
        ledger.submit(f"d{i}", "node-droppy")
        if i < 2:
            ledger.confirm(f"d{i}")
        else:
            ledger.timeout(f"d{i}")

    print(f"可信节点信用={ledger.credit_of('node-trusted'):.3f} 路由={ledger.routing_decision('node-trusted', relays)}")
    print(f"丢包节点信用={ledger.credit_of('node-droppy'):.3f} 路由={ledger.routing_decision('node-droppy', relays)}")


if __name__ == "__main__":
    demo()
