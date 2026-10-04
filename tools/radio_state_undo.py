"""EvoUndo 无线电参数状态回滚（A31 · NEKO/IC-705）。

依据 round3 digest-g1b-2026-08-31.md 授粉点 3（2608.28363 EvoUndo）：
「自我演化产生的修改必须可恢复；扩展恢复语言 + 精确状态地址接地协同可将
恢复率提升至 99.3%」。

对 IC-705/NEKO 的迁移：认知无线电 Agent 自主修改参数（频率/功率/调制/SWR 阈值）
后，遇到干扰切换回来需要**精确恢复**而非模糊重启。映射：
  - 恢复演算（recovery calculus）= 每次变更记录「反向操作」（旧值），逆序回滚；
  - 状态地址接地 = 参数集合显式登记（tracked），未被登记的参数是「盲点」，
    其旧值丢失 → 回滚后残留少量不精确（对应 EvoUndo 的 99.3% 而非 100%）。

原型（纯 stdlib，确定性）：
  - RadioController 管理参数状态 + 反向操作日志；
  - set() 对已登记参数压入 (参数, 旧值)，对盲点参数直接改（旧值丢失）；
  - undo(n) 逆序恢复；correctness(snapshot) 统计回滚正确率。

验收（SPEC A31）：模拟参数变更回滚正确率 ≥95%。

运行：
  python tools/radio_state_undo.py
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class RadioController:
    """无线电参数控制器：带反向操作日志的精确回滚。"""

    state: dict[str, float]
    tracked: set[str] = field(default_factory=set)  # 状态地址接地：可回滚参数
    undo_log: list[tuple[str, float]] = field(default_factory=list)

    def set(self, param: str, value: float) -> None:
        """变更参数：已登记参数记录反向操作 (param, old)，盲点参数旧值丢失。"""
        if param in self.tracked:
            self.undo_log.append((param, self.state[param]))
        self.state[param] = value

    def undo(self, n: int | None = None) -> int:
        """逆序回滚最近 n 步（默认全部），返回实际回滚步数。"""
        if n is None:
            n = len(self.undo_log)
        n = min(n, len(self.undo_log))
        for _ in range(n):
            param, old = self.undo_log.pop()
            self.state[param] = old
        return n

    def correctness(self, snapshot: dict[str, float]) -> float:
        """回滚正确率：与快照一致的参数比例。"""
        if not snapshot:
            return 1.0
        matched = sum(1 for k, v in snapshot.items() if self.state.get(k) == v)
        return matched / len(snapshot)

    def snapshot(self) -> dict[str, float]:
        """精确状态接地：取当前完整参数快照。"""
        return dict(self.state)

    def restore(self, snapshot: dict[str, float]) -> None:
        """直接恢复到快照（精确状态接地），并清空日志（快照为新基线）。"""
        self.state.update(snapshot)
        self.undo_log.clear()


def build_radio(n_params: int = 40, seed: int = 0) -> RadioController:
    """构建初始状态一致的电台：n_params 个参数，最后 1 个为「盲点」（未接地）。"""
    import random
    rng = random.Random(seed)
    state = {f"p{i}": float(i) for i in range(n_params)}
    tracked = {f"p{i}" for i in range(n_params - 1)}  # 最后一个 p{n-1} 未登记
    return RadioController(state=state, tracked=tracked)


def simulate(n_params: int = 40, n_changes: int = 30, seed: int = 0) -> dict:
    """模拟：干扰场景做 n_changes 次变更（含盲点变更），然后回滚，统计正确率。"""
    import random
    rng = random.Random(seed)
    radio = build_radio(n_params, seed)
    snapshot = dict(radio.state)

    # 干扰期：对 tracked 参数做 n_changes 次可回滚变更 + 1 次盲点变更
    for _ in range(n_changes):
        p = f"p{rng.randrange(n_params - 1)}"
        radio.set(p, radio.state[p] + rng.uniform(1.0, 10.0))
    blind = f"p{n_params - 1}"
    radio.set(blind, radio.state[blind] + 999.0)  # 盲点变更，旧值丢失

    # 干扰消失：回滚全部可回滚变更
    radio.undo()
    return {"correctness": radio.correctness(snapshot), "snapshot": snapshot, "state": radio.state}


def main() -> int:
    result = simulate()
    acc = result["correctness"]
    print(f"[回滚正确率] {acc:.3f}（验收要求 ≥0.95）")
    # 找出残留不精确的参数（盲点）
    bad = [k for k, v in result["snapshot"].items() if result["state"].get(k) != v]
    print(f"[残留不精确参数] {bad}")
    return 0 if acc >= 0.95 else 1


if __name__ == "__main__":
    raise SystemExit(main())
