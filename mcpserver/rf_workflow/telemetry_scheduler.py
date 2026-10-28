"""遥测「何时传」四策略对比 —— 确定性仿真器（工单255 任务A）。

## 授粉点（论文 → 本模块哪一层 → 为什么这样取舍）

| 论文 | 机制 | 落到本模块 | 取舍 |
|---|---|---|---|
| 2610.22304 | AoI/AoA 联合 +「有新数据**且**有能量才动」 | `Policy.AOA_ENERGY_GATED` | 只借"决策律的形状"，**不搬论文实验数值**；能量/动作代价全部是本模块显式参数 |
| 2610.21968 | 事件触发 + 最小静默间隔 | `Policy.EVENT_TRIGGERED` | 同上：借"Δ + 静默窗"结构 |
| — | AoI（信息年龄）/ AoA（动作信息年龄）/ AoII（错误信息年龄）作为**对比指标** | `simulate()` 的 metrics | 三个 ages 统一由本模块定义（见下），保证四策略在同一口径下可比 |

⚠️ 本模块交付的是**口径与可跑基线**，不是任何论文结论的复现。论文里的实验数字一律不出现。

## 三个 age 的口径（本模块唯一定义，测试与报告都引用这里）

- **AoI**：每个 tick，`age = t - 最近一次「已送达」样本的生成时刻`。送达延迟按 `LATENCY_TICKS` 计入。
- **AoA**（动作信息年龄）：接收端每 `ACTION_PERIOD_TICKS` 执行一次动作，动作用"当时已送达的最新样本"；
  `AoA = 动作时刻 - 该样本生成时刻`，只在这些动作时刻取样再平均。
- **AoII 违例**：接收端状态 = 最近送达样本的值；若 `|真值 - 接收端状态| > AOA_VALUE_TOL` 记一次违例 tick；
  **违例率 = 违例 tick 数 / 总 tick 数**。（AoII 的"错误持续时间占比"口径。）

## 因果链（为什么稀缺能量下 gated 更好，而不是靠调参凑出来）

稀缺能量场景下，`periodic`/`aoi_threshold` 会**在值没变时也发**（信息价值为零的发送），
把电池耗在无效更新上；等真正的变化（事件）到来时反而没电可发 ⇒ 违例率升高。
`aoa_energy_gated` 只在「有新数据 且 有能量」时才发，省下的电留给了真正含信息的时刻。

## 复现

    python -m mcpserver.rf_workflow.telemetry_scheduler --demo
"""
from __future__ import annotations

import argparse
import json
import math
from dataclasses import dataclass, field


class Policy:
    """策略标识（字符串常量，避免 Enum 的序列化摩擦）。"""

    PERIODIC = "periodic"
    AOI_THRESHOLD = "aoi_threshold"
    AOA_ENERGY_GATED = "aoa_energy_gated"
    EVENT_TRIGGERED = "event_triggered"

    ALL = (PERIODIC, AOI_THRESHOLD, AOA_ENERGY_GATED, EVENT_TRIGGERED)


@dataclass(frozen=True)
class Scenario:
    """一个确定性场景。所有随机性都来自 `seed`，不得使用全局 random / 时间。"""

    name: str
    ticks: int = 600
    seed: int = 20261017
    # 数值演化：平时只有**噪声级抖动**（不算"新信息"），每 event_every 注入一次**事件阶跃**
    value_step: float = 0.008
    event_every: int = 60
    event_jump: float = 0.30
    # 「有新数据」的判定底噪：|Δ| 必须大于噪声量级才算新信息（否则随机抖动会把 gate 打成恒真）
    change_epsilon: float = 0.10
    # 能量模型（毫焦，mJ）
    battery_capacity_mj: float = 12.0
    harvest_per_tick_mj: float = 0.02      # 稀缺场景应 < tx 成本
    tx_cost_mj: float = 1.2
    action_cost_mj: float = 0.35
    # 接收端约束
    latency_ticks: int = 2                  # 单次传输占用信道的时长（tick）= 送达延迟
    action_period_ticks: int = 5            # AoA 取样周期
    aoa_value_tol: float = 0.12             # AoII 判定容差（值域归一化后）
    # 策略参数
    periodic_ticks: int = 10                # periodic：每 N tick 发一次
    aoi_threshold_ticks: int = 12           # aoi_threshold：本地年龄超该值就发
    event_delta: float = 0.10               # event_triggered：变化量阈值
    event_min_silence: int = 12             # event_triggered：最小静默间隔


@dataclass
class Metrics:
    policy: str
    scenario: str
    avg_aoi_ticks: float = 0.0
    avg_aoa_ticks: float = 0.0
    aoii_violation_rate: float = 0.0
    tx_count: int = 0
    total_energy_mj: float = 0.0
    dropped_updates: int = 0
    actions_taken: int = 0
    energy_depleted_ticks: int = 0
    extra: dict = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {
            "policy": self.policy,
            "scenario": self.scenario,
            "avg_aoi_ticks": round(self.avg_aoi_ticks, 4),
            "avg_aoa_ticks": round(self.avg_aoa_ticks, 4),
            "aoii_violation_rate": round(self.aoii_violation_rate, 6),
            "tx_count": self.tx_count,
            "total_energy_mj": round(self.total_energy_mj, 4),
            "dropped_updates": self.dropped_updates,
            "actions_taken": self.actions_taken,
            "energy_depleted_ticks": self.energy_depleted_ticks,
            "extra": self.extra,
        }


def _lcg(seed: int):
    """确定性伪随机（线性同余）——**不用** random 模块，保证跨版本逐位一致。"""

    state = seed & 0xFFFFFFFF

    def nxt() -> float:
        nonlocal state
        state = (1103515245 * state + 12345) & 0x7FFFFFFF
        return state / 0x7FFFFFFF

    return nxt


def generate_trace(sc: Scenario) -> list[float]:
    """生成真值轨迹（确定性）：随机游走 + 每 event_every 注入阶跃，裁到 [0,1]。"""
    rnd = _lcg(sc.seed)
    value = 0.5
    trace: list[float] = []
    for t in range(sc.ticks):
        value += (rnd() - 0.5) * 2.0 * sc.value_step
        if sc.event_every > 0 and t > 0 and t % sc.event_every == 0:
            # 事件**交替方向**（否则单调阶跃会把值顶到 1.0 饱和，之后再无"新数据"）
            direction = 1.0 if (t // sc.event_every) % 2 == 1 else -1.0
            value += direction * sc.event_jump
        value = min(1.0, max(0.0, value))
        trace.append(value)
    return trace


def _should_send(policy: str, sc: Scenario, t: int, *, last_tx_t: int, last_sent_value: float,
                 current_value: float, has_new_data: bool, energy_ok: bool) -> bool:
    """单 tick 的发送决策（纯函数，便于单测）。"""
    if policy == Policy.PERIODIC:
        return t % max(1, sc.periodic_ticks) == 0
    if policy == Policy.AOI_THRESHOLD:
        return (t - last_tx_t) >= max(1, sc.aoi_threshold_ticks)
    if policy == Policy.AOA_ENERGY_GATED:
        # 2610.22304 的形状：**有新数据（超过底噪）且 有能量（且不饿死动作）**才动
        return has_new_data and energy_ok
    if policy == Policy.EVENT_TRIGGERED:
        if (t - last_tx_t) < max(1, sc.event_min_silence):
            return False
        return abs(current_value - last_sent_value) >= sc.event_delta
    raise ValueError(f"未知策略: {policy}")


def simulate(scenario: Scenario, policy: str) -> Metrics:
    """跑一个场景 × 一个策略，返回指标。**确定性**：同参数两次调用结果逐位一致。

    信道模型：一次传输**占用信道 `latency_ticks`**；占用期间无法发起新传输，
    此时若决策仍要发 ⇒ 计"丢更新"（无队列，符合低功耗节点实况）。
    送达后接收端状态更新为**该次传输发出时的值**。
    """
    if policy not in Policy.ALL:
        raise ValueError(f"未知策略: {policy}")

    trace = generate_trace(scenario)
    battery = scenario.battery_capacity_mj
    last_tx_t = -(10 ** 6)
    last_sent_value = trace[0]
    busy_until_t = -1                       # 信道占用到何时
    inflight: list[tuple[int, int, float]] = []
    delivered_gen_t = -1
    delivered_value = trace[0]

    aoi_sum = 0.0
    aoa_samples: list[float] = []
    wrong_ticks = 0                          # 逐 tick 错误持续时间（AoII 口径①）
    planned_actions = 0
    missed_actions = 0                       # 缺电未执行
    wrong_info_actions = 0                   # 执行了但用的是错值（AoII 口径② 的两个分量）
    tx_count = 0
    dropped = 0
    total_energy = 0.0
    actions = 0
    depleted_ticks = 0

    for t in range(scenario.ticks):
        battery = min(scenario.battery_capacity_mj, battery + scenario.harvest_per_tick_mj)
        if battery < scenario.tx_cost_mj:
            depleted_ticks += 1

        # 到货
        for item in [x for x in inflight if x[0] <= t]:
            _, gen_t, value = item
            inflight.remove(item)
            delivered_gen_t, delivered_value = gen_t, value

        current_value = trace[t]
        age = (t - delivered_gen_t) if delivered_gen_t >= 0 else (t + 1)

        # 「有新数据」= 相对**上次已发**值的改变超过底噪（噪声抖动不算新信息）
        has_new_data = abs(current_value - last_sent_value) >= scenario.change_epsilon
        energy_ok = battery >= (scenario.tx_cost_mj + scenario.action_cost_mj)
        want_send = _should_send(policy, scenario, t, last_tx_t=last_tx_t,
                                 last_sent_value=last_sent_value, current_value=current_value,
                                 has_new_data=has_new_data, energy_ok=energy_ok)

        if want_send:
            if t < busy_until_t:
                dropped += 1                     # 信道忙 ⇒ 该更新被丢弃（无队列）
            elif battery >= scenario.tx_cost_mj:
                battery -= scenario.tx_cost_mj
                total_energy += scenario.tx_cost_mj
                tx_count += 1
                last_tx_t = t
                last_sent_value = current_value
                busy_until_t = t + scenario.latency_ticks
                inflight.append((t + scenario.latency_ticks, t, current_value))
            else:
                dropped += 1                     # 想发但没电

        aoi_sum += age
        if abs(current_value - delivered_value) > scenario.aoa_value_tol:
            wrong_ticks += 1

        # 动作（AoA 取样 + AoII 口径② 的判定点）
        if t % max(1, scenario.action_period_ticks) == 0:
            planned_actions += 1
            if battery < scenario.action_cost_mj:
                missed_actions += 1              # 缺电 ⇒ 动作没做成（对控制回路等价于"错的"）
            else:
                battery -= scenario.action_cost_mj
                total_energy += scenario.action_cost_mj
                actions += 1
                aoa_samples.append(float(age))
                if abs(current_value - delivered_value) > scenario.aoa_value_tol:
                    wrong_info_actions += 1

    ticks = max(1, scenario.ticks)
    action_viol = (missed_actions + wrong_info_actions) / max(1, planned_actions)
    return Metrics(
        policy=policy,
        scenario=scenario.name,
        avg_aoi_ticks=aoi_sum / ticks,
        avg_aoa_ticks=(sum(aoa_samples) / len(aoa_samples)) if aoa_samples else float("nan"),
        aoii_violation_rate=action_viol,
        tx_count=tx_count,
        total_energy_mj=total_energy,
        dropped_updates=dropped,
        actions_taken=actions,
        energy_depleted_ticks=depleted_ticks,
        extra={
            "ticks": ticks,
            "aoii_error_time_rate": round(wrong_ticks / ticks, 6),   # 口径①：错误持续时间占比
            "planned_actions": planned_actions,
            "missed_actions": missed_actions,
            "wrong_info_actions": wrong_info_actions,
        },
    )


def simulate_all(scenario: Scenario) -> list[Metrics]:
    return [simulate(scenario, p) for p in Policy.ALL]


# ---------------------------------------------------------------------------
# 内置场景（稀缺 / 充裕）—— **测试与 demo 用同一份定义**，避免两处漂移
# ---------------------------------------------------------------------------
def scarce_scenario() -> Scenario:
    """能量稀缺：采集 0.10 mJ/tick。

    动作每 5 tick 花 0.35 mJ ⇒ 光动作就要 0.07 mJ/tick；留给发射的只剩 0.03 mJ/tick
    ⇒ 发一次（1.2 mJ）要攒 40 tick。**周期性无脑发（每 10 tick）必然透支电池**。
    """
    return Scenario(name="scarce", harvest_per_tick_mj=0.10, tx_cost_mj=1.2,
                    action_cost_mj=0.35, battery_capacity_mj=6.0)


def abundant_scenario() -> Scenario:
    """能量充裕：采集 3 mJ/tick ≫ 发射 1.2 mJ ⇒ 能量不再是瓶颈，四策略只受"何时愿意发"限制。"""
    return Scenario(name="abundant", harvest_per_tick_mj=3.0, tx_cost_mj=1.2,
                    action_cost_mj=0.35, battery_capacity_mj=12.0)


def format_table(results: list[Metrics]) -> str:
    """把结果渲染成等宽表（单位写在表头）。"""
    head = ("policy", "scenario", "AoI(tick)", "AoA(tick)", "AoII违例率", "发送次数",
            "总能耗(mJ)", "丢更新", "动作次数", "缺电tick")
    rows = [head]
    for m in results:
        rows.append((
            m.policy, m.scenario,
            f"{m.avg_aoi_ticks:.2f}", f"{m.avg_aoa_ticks:.2f}",
            f"{m.aoii_violation_rate * 100:.2f}%",
            str(m.tx_count), f"{m.total_energy_mj:.2f}", str(m.dropped_updates),
            str(m.actions_taken), str(m.energy_depleted_ticks),
        ))
    widths = [max(len(r[i]) for r in rows) for i in range(len(head))]
    out = ["  ".join(c.ljust(widths[i]) for i, c in enumerate(r)) for r in rows]
    out.insert(1, "  ".join("-" * w for w in widths))
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="遥测「何时传」四策略对比（工单255 任务A）")
    ap.add_argument("--demo", action="store_true", help="跑内置稀缺+充裕两个场景并打印指标表")
    ap.add_argument("--json", action="store_true", help="输出 JSON（机读）")
    args = ap.parse_args(argv)

    results = simulate_all(scarce_scenario()) + simulate_all(abundant_scenario())
    if args.json:
        print(json.dumps([m.as_dict() for m in results], ensure_ascii=False, indent=1))
        return 0

    print("遥测「何时传」四策略对比（工单255 任务A）")
    print("注：AoI/AoA 单位 = tick（1 tick = 一个采样周期）；AoII 违例率 = 错误持续 tick 占比")
    print()
    print(format_table(results))
    print()
    print("AoII(动作侧) = (缺电未执行动作 + 用错值执行动作) / 计划动作数；"
          "AoII(错误持续) 见 --json 的 extra.aoii_error_time_rate")
    print("口径：AoI=已送达样本的年龄；AoA=动作时刻所用样本的年龄（每 "
          f"{scarce_scenario().action_period_ticks} tick 取一次）；"
          f"AoII 容差 = ±{scarce_scenario().aoa_value_tol}（归一化值域）")
    print("⚠️ 本表是**口径与可跑基线**，不是论文实验数值的复现。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
