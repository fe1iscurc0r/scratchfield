#!/usr/bin/env python3
"""K11 材料性能预测管线（主动学习闭环，M03 扩展）。

基于 bo_optim 的木质素水热合成参数空间（T 温度 / t 时间 / R 配比 / C 浓度）：
主动学习闭环 = 代理模型预测 → 采集函数推荐下一组实验条件 → 实测回填 → 更新模型。

注意：bo_optim 的 sample() 不套约束（只在 validate() 校验），故本脚本用
显式合法种子 + 对推荐配方按已知设备/溶解度上限夹紧（C≤18、T≤220），
模拟真实湿实验的「可行性夹紧」。合成响应面模拟实测，真实数据留真机。
"""
from __future__ import annotations

import numpy as np

from mcpserver.material_science.bo_optim import BOLoop, lignin_hydrothermal_space


def _clamp(r: dict) -> dict:
    r = dict(r)
    r["C"] = min(float(r.get("C", 10.0)), 18.0)   # 原料溶解度上限
    r["T"] = min(float(r.get("T", 190.0)), 220.0)  # 设备温度上限
    return r


def simulate(recipe: dict) -> dict:
    """合成响应面（木质素 NPs 水热合成假设规律，含噪声）。"""
    rng = np.random.default_rng()
    t_ = recipe["T"]
    yield_ = 0.25 + 0.18 * np.exp(-((t_ - 190) / 25) ** 2) * (recipe["R"] / 6.0) * np.clip(recipe["t"] / 12.0, 0.2, 1.3)
    yield_ = float(np.clip(yield_ + rng.normal(0, 0.01), 0.0, 1.0))
    pdi = float(np.clip(0.30 - 0.05 * (t_ - 190) / 30 + rng.normal(0, 0.02), 0.05, 0.6))
    size_nm = float(np.clip(120 + (t_ - 160) * 2.0 + rng.normal(0, 8), 40, 400))
    return {"yield": yield_, "pdi": pdi, "size_nm": size_nm}


def _fmt(r: dict) -> dict:
    return {k: (round(float(v), 2) if isinstance(v, (int, float, np.floating)) else v) for k, v in r.items()}


def main() -> int:
    space = lignin_hydrothermal_space()
    loop = BOLoop(space, strategy="ei")

    # 1) 初始粗扫（显式合法种子）
    seeds = [
        {"T": 160, "t": 6, "C": 10, "R": 3, "S": "纯水", "pH": "酸性", "L": "碱木质素"},
        {"T": 180, "t": 12, "C": 12, "R": 5, "S": "乙醇-水", "pH": "中性", "L": "酶解木质素"},
        {"T": 200, "t": 18, "C": 8, "R": 8, "S": "纯水", "pH": "碱性", "L": "其他"},
        {"T": 150, "t": 4, "C": 15, "R": 2, "S": "乙醇-水", "pH": "酸性", "L": "碱木质素"},
    ]
    loop.init(n=0, warm_start=[{"recipe": s, "metrics": simulate(s)} for s in seeds])
    loop.update()

    # 2) 主动学习迭代：推荐 → 实测 → 更新
    for it in range(3):
        batch = loop.recommend_batch(k=2)
        for r in batch:
            r = _clamp(r)
            loop.record(r, simulate(r))
        loop.update()
        print(f"iter {it + 1}: 观测 {loop.n_observations()} 组，best_objective={loop.y_best():.4f}")

    # 3) 最终推荐下一组实验条件
    recs = loop.recommend_batch(k=1)
    final = _clamp(recs[0])
    print("推荐下一组实验条件:", _fmt(final))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
