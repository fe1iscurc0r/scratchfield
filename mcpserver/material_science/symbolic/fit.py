"""fit.py — 符号回归拟合（纯 numpy 遗传编程）。

输入 X(n,d)/y(n) → 产出显式表达式（Expression）。与 biopred.py 黑箱主流程无关：
本旁路独立拟合，供"黑箱预测 + 符号表达式对照"用，不修改 biopred。

工具选型（Y-01 结论）：gplearn 级别纯 numpy GP——无 gplearn/pysr 依赖，
重工具（pysr/Julia 后端）判定为二期；合成数据验收，真实数据留真机。
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from .expr import Expression


# ---- 受保护函数 / 二元算子（防 NaN/Inf 炸种群）----
def _safe_log(x):
    return np.log(np.maximum(np.abs(x), 1e-9))


def _safe_sqrt(x):
    return np.sqrt(np.maximum(x, 0.0))


def _safe_div(a, b):
    b = np.where(np.abs(b) < 1e-9, 1e-9, b)
    return a / b


_FUNCS = {
    "sin": np.sin,
    "cos": np.cos,
    "exp": np.exp,
    "log": _safe_log,
    "sqrt": _safe_sqrt,
    "abs": np.abs,
}
_BIN = {
    "add": lambda a, b: a + b,
    "sub": lambda a, b: a - b,
    "mul": lambda a, b: a * b,
    "div": _safe_div,
}
_FUNC_NAMES = list(_FUNCS)
_BIN_NAMES = list(_BIN)
_CONST_POOL = [-5.0, -2.0, -1.0, -0.5, 0.5, 1.0, 2.0, 3.0, 5.0]

# 树节点：["c", 常数] | ["v", 特征索引] | ["u", 函数名, 子树] | ["b", 算子名, 左, 右]


def _rand_leaf(n_features: int, rng: random.Random):
    if rng.random() < 0.5:
        return ["v", rng.randrange(n_features)]
    return ["c", float(rng.choice(_CONST_POOL))]


def _rand_tree(depth: int, max_depth: int, n_features: int, rng: random.Random):
    leaf_p = 0.25 + 0.5 * (depth / max(1, max_depth))
    if depth >= max_depth or rng.random() < leaf_p:
        return _rand_leaf(n_features, rng)
    if rng.random() < 0.25:
        return ["u", rng.choice(_FUNC_NAMES),
                _rand_tree(depth + 1, max_depth, n_features, rng)]
    return ["b", rng.choice(_BIN_NAMES),
            _rand_tree(depth + 1, max_depth, n_features, rng),
            _rand_tree(depth + 1, max_depth, n_features, rng)]


def _children(node):
    if node[0] == "u":
        return [node[2]]
    if node[0] == "b":
        return [node[2], node[3]]
    return []


def _clone(node):
    if node[0] == "c":
        return ["c", node[1]]
    if node[0] == "v":
        return ["v", node[1]]
    if node[0] == "u":
        return ["u", node[1], _clone(node[2])]
    return ["b", node[1], _clone(node[2]), _clone(node[3])]


def _eval_node(node, vals):
    k = node[0]
    if k == "c":
        return np.full(vals[0].shape, node[1], dtype=float)
    if k == "v":
        return vals[node[1]]
    if k == "u":
        return _FUNCS[node[1]](_eval_node(node[2], vals))
    if k == "b":
        return _BIN[node[1]](_eval_node(node[2], vals), _eval_node(node[3], vals))
    raise ValueError(f"未知节点: {k}")


def _count_nodes(node) -> int:
    if node[0] in ("c", "v"):
        return 1
    if node[0] == "u":
        return 1 + _count_nodes(node[2])
    return 1 + _count_nodes(node[2]) + _count_nodes(node[3])


def _score(node, y, vals, parsimony: float = 0.0) -> float:
    try:
        with np.errstate(all="ignore"):
            pred = np.asarray(_eval_node(node, vals), dtype=float).ravel()
            if pred.shape != y.shape:
                pred = np.broadcast_to(pred, y.shape)
            if not np.all(np.isfinite(pred)):
                return float("inf")
            rmse = float(np.sqrt(np.mean((pred - y) ** 2)))
        # 复杂度惩罚（parsimony）：节点越多惩罚越重，抑制 GP 膨胀
        return rmse * (1.0 + parsimony * _count_nodes(node))
    except Exception:
        return float("inf")


def _fold_constants(node):
    """常数折叠：把仅含常数的子树合并为单个常数节点，清理 GP 冗余项（如 abs(-1)→1）。"""
    k = node[0]
    if k in ("c", "v"):
        return node
    if k == "u":
        child = _fold_constants(node[2])
        if child[0] == "c":
            with np.errstate(all="ignore"):
                val = float(_FUNCS[node[1]](np.array([child[1]]))[0])
            if np.isfinite(val):
                return ["c", val]
        return ["u", node[1], child]
    left = _fold_constants(node[2])
    right = _fold_constants(node[3])
    if left[0] == "c" and right[0] == "c":
        with np.errstate(all="ignore"):
            val = float(_BIN[node[1]](np.array([left[1]]), np.array([right[1]]))[0])
        if np.isfinite(val):
            return ["c", val]
    return ["b", node[1], left, right]


def _collect_refs(node, parent=None, idx=None, acc=None):
    """收集所有子树的 (父节点, 槽位下标, 子树) 引用；槽位下标是真实 list 下标。

    "b" 节点子节点在 index 2/3，"u" 节点子节点在 index 2——不能直接拿
    _children 的 enumerate 序数（0/1），否则 parent[idx]=new 会写到 kind/name 字段。
    """
    if acc is None:
        acc = []
    acc.append((parent, idx, node))
    if node[0] == "u":
        _collect_refs(node[2], node, 2, acc)
    elif node[0] == "b":
        _collect_refs(node[2], node, 2, acc)
        _collect_refs(node[3], node, 3, acc)
    return acc


def _crossover(a, b, rng: random.Random) -> None:
    ra = _collect_refs(a)
    rb = _collect_refs(b)
    pa, ia, na = ra[rng.randrange(len(ra))]
    pb, ib, nb = rb[rng.randrange(len(rb))]
    ca = _clone(na)
    cb = _clone(nb)
    if pa is None:
        na[:] = cb
    else:
        pa[ia] = cb
    if pb is None:
        nb[:] = ca
    else:
        pb[ib] = ca


def _mutate(tree, rng: random.Random, n_features: int, max_depth: int) -> None:
    refs = _collect_refs(tree)
    parent, idx, node = refs[rng.randrange(len(refs))]
    r = rng.random()
    new = None
    if r < 0.4:
        new = _rand_tree(0, max_depth, n_features, rng)
    elif r < 0.7:
        k = node[0]
        if k == "c":
            node[1] = float(rng.choice(_CONST_POOL))
        elif k == "v":
            node[1] = rng.randrange(n_features)
        elif k == "u":
            node[1] = rng.choice(_FUNC_NAMES)
        else:
            node[1] = rng.choice(_BIN_NAMES)
    else:
        ch = _children(node)
        if not ch:
            return
        new = _clone(ch[rng.randrange(len(ch))])
    if new is not None:
        if parent is None:
            node[:] = new
        else:
            parent[idx] = new


def _tournament(scored, k: int, rng: random.Random):
    pick = [scored[rng.randrange(len(scored))] for _ in range(k)]
    return min(pick, key=lambda p: p[0])[1]


def _to_infix(node, names) -> str:
    if node[0] == "c":
        return f"{node[1]:.6g}"
    if node[0] == "v":
        return names[node[1]]
    if node[0] == "u":
        return f"{node[1]}({_to_infix(node[2], names)})"
    op = {"add": "+", "sub": "-", "mul": "*", "div": "/"}[node[1]]
    return f"({_to_infix(node[2], names)} {op} {_to_infix(node[3], names)})"


@dataclass
class FitResult:
    expression: Expression
    rmse: float
    r2: float
    generations: int
    feature_names: list[str]
    best_history: list[float] = field(default_factory=list)


def fit(X, y, *, feature_names=None, population_size: int = 300,
        generations: int = 40, tournament_size: int = 5, max_depth: int = 4,
        parsimony: float = 0.001, random_state: int = 0,
        verbose: bool = False) -> FitResult:
    """拟合显式表达式（grep 验收：def fit）。

    X: (n, d) 或 (n,)；y: (n,)；返回 FitResult（含 Expression/rmse/r2）。
    """
    X = np.asarray(X, dtype=float)
    y = np.asarray(y, dtype=float).ravel()
    if X.ndim == 1:
        X = X.reshape(-1, 1)
    if X.ndim != 2:
        raise ValueError("X 必须是 1D 或 2D")
    n, d = X.shape
    if n != y.shape[0]:
        raise ValueError(f"X 行数 {n} 与 y 长度 {y.shape[0]} 不一致")
    if n < 3:
        raise ValueError(f"样本不足（{n} < 3）")
    if feature_names is None:
        feature_names = [f"x{i}" for i in range(d)]
    elif len(feature_names) != d:
        raise ValueError(f"feature_names 长度 {len(feature_names)} 与特征数 {d} 不一致")

    rng = random.Random(random_state)
    vals = [X[:, i] for i in range(d)]
    pop = [_rand_tree(0, max_depth, d, rng) for _ in range(population_size)]
    history: list[float] = []
    best_tree = None
    best_score = float("inf")

    for gen in range(generations):
        scored = [(_score(t, y, vals, parsimony), t) for t in pop]
        scored.sort(key=lambda p: p[0])
        if scored[0][0] < best_score:
            best_score = scored[0][0]
            best_tree = _clone(scored[0][1])
        history.append(best_score)
        if verbose:
            print(f"[gen {gen}] best rmse={best_score:.6g}")
        new_pop = [_clone(scored[0][1]), _clone(scored[1][1])]
        while len(new_pop) < population_size:
            a = _tournament(scored, tournament_size, rng)
            b = _tournament(scored, tournament_size, rng)
            ca = _clone(a)
            cb = _clone(b)
            if rng.random() < 0.85:
                _crossover(ca, cb, rng)
            if rng.random() < 0.5:
                _mutate(ca, rng, d, max_depth)
            if rng.random() < 0.5:
                _mutate(cb, rng, d, max_depth)
            new_pop.append(ca)
            if len(new_pop) < population_size:
                new_pop.append(cb)
        pop = new_pop

    if best_tree is None:
        scored = [(_score(t, y, vals, parsimony), t) for t in pop]
        scored.sort(key=lambda p: p[0])
        best_tree = _clone(scored[0][1])
        best_score = scored[0][0]

    best_tree = _fold_constants(best_tree)
    expression = Expression(_to_infix(best_tree, feature_names))
    # 用折叠后的表达式重新算「原始」rmse/r2（best_score 是带 parsimony 的适应度）
    with np.errstate(all="ignore"):
        pred = np.asarray(_eval_node(best_tree, vals), dtype=float).ravel()
        rmse = float(np.sqrt(np.mean((pred - y) ** 2)))
    ss_res = rmse ** 2 * n
    ss_tot = float(np.sum((y - np.mean(y)) ** 2))
    r2 = float(1.0 - ss_res / ss_tot) if ss_tot > 1e-12 else 0.0
    return FitResult(expression=expression, rmse=rmse, r2=r2,
                     generations=generations, feature_names=list(feature_names),
                     best_history=history)


def _demo_data() -> tuple[np.ndarray, np.ndarray]:
    """内置合成数据：y = 3*x0 + 2（线性目标，验证旁路能收敛）。"""
    x0 = np.linspace(-3.0, 3.0, 40)
    return x0.reshape(-1, 1), 3.0 * x0 + 2.0


def self_test(verbose: bool = False) -> dict[str, Any]:
    """内置合成数据自测（验证 fit 存在且可跑）。"""
    X, y = _demo_data()
    res = fit(X, y, population_size=200, generations=30,
              random_state=0, verbose=verbose)
    return {"ok": res.rmse < 0.1, "expression": res.expression.text,
            "rmse": round(res.rmse, 6), "r2": round(res.r2, 6)}


__all__ = ["fit", "FitResult", "self_test"]
