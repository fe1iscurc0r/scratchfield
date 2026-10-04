"""R16 · ESP32 自适应跳频策略模拟（语义 UEP → 频点/重传映射）

灵感：digest-gx-1 授粉点② · 论文 16227（信息驱动 UEP）。

把语义重要性映射到跳频：重要数据走可靠频点 + 重传，常规数据尽力而为。
模拟对比「均匀跳频」与「语义感知跳频」的送达成功率。

模型：N 个频点，其中 R 个可靠（干扰率 p_rel）、U 个普通（干扰率 p_unrel）。
每个包独立传输，一次成功概率 = 1 - 干扰率；重传 = 多次独立传输，任一成功即送达。

运行：python -m mcpserver.rf_brain.prototypes.adaptive_fh
"""
from __future__ import annotations

import numpy as np


def _send(rng, prob_interf: float, retries: int) -> bool:
    """发送一个包（含 retries 次重传），任一成功返回 True。"""
    for _ in range(retries + 1):
        if rng.random() > prob_interf:
            return True
    return False


def run_simulation(strategy: str, *, n_packets: int = 2000, n_reliable: int = 4,
                   n_unreliable: int = 8, p_reliable: float = 0.05,
                   p_unreliable: float = 0.5, seed: int = 0) -> dict:
    """模拟送达率。strategy ∈ {'uniform', 'semantic'}。返回各语义级别成功率。"""
    rng = np.random.default_rng(seed)
    # 语义级别分布：L0 关键 10%，L1 重要 30%，L2 常规 60%
    levels = rng.choice(["L0", "L1", "L2"], n_packets, p=[0.1, 0.3, 0.6])
    results = {"L0": [], "L1": [], "L2": []}
    for lv in levels:
        if strategy == "uniform":
            # 均匀跳频：全频点随机、无重传
            p = (n_reliable * p_reliable + n_unreliable * p_unreliable) / (n_reliable + n_unreliable)
            ok = _send(rng, p, retries=0)
        elif strategy == "semantic":
            if lv == "L0":
                ok = _send(rng, p_reliable, retries=2)
            elif lv == "L1":
                ok = _send(rng, p_reliable, retries=1)
            else:  # L2
                p = (n_reliable * p_reliable + n_unreliable * p_unreliable) / (n_reliable + n_unreliable)
                ok = _send(rng, p, retries=0)
        else:
            raise ValueError(strategy)
        results[lv].append(ok)
    return {lv: float(np.mean(v)) for lv, v in results.items()}


def main() -> None:
    uni = run_simulation("uniform")
    sem = run_simulation("semantic")
    print(f"{'级别':<8}{'均匀跳频':>10}{'语义感知':>10}")
    for lv in ("L0", "L1", "L2"):
        print(f"{lv:<8}{uni[lv]*100:>9.1f}%{sem[lv]*100:>9.1f}%")


if __name__ == "__main__":
    main()
