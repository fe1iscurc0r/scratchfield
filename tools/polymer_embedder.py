"""FRPN 双通道 embedding 检索快通道 · 最小版（工单227 任务三）.

料源：docs/pollination/frpn-multiscale-design-2026-10.md（工单226 任务二设计稿）。
口径：不追 SOTA，只求"双通道能跑通"——
  通道A（单体语义）：SMILES → RDKit Morgan fingerprint（rdkit 缺则整体 skip）；
  通道B（链拓扑）：重复单元计数/连接度/支链度的简单序列特征；
  拼接定长向量 + cosine 检索。
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

# 通道 A 的 rdkit 依赖：缺失环境整模块功能降级（测试侧 importorskip）
try:
    from rdkit import Chem
    from rdkit.Chem import AllChem
    _HAS_RDKIT = True
except ImportError:  # pragma: no cover - 环境依赖
    _HAS_RDKIT = False

_FP_BITS = 256       # Morgan 指纹位数（PoC 用小位宽）
_TOPO_DIMS = 8       # 通道 B 特征维数
EMBED_DIM = _FP_BITS + _TOPO_DIMS


def monomer_fp(smiles: str) -> list[float]:
    """通道A：单体语义（Morgan fingerprint，0/1 → float）。"""
    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        raise ValueError(f"非法 SMILES: {smiles}")
    fp = AllChem.GetMorganFingerprintAsBitVect(mol, radius=2, nBits=_FP_BITS)
    return [float(fp.GetBit(i)) for i in range(_FP_BITS)]


def topology_feats(n_repeats: int, n_branch: int, linear: bool,
                   extra: list[float] | None = None) -> list[float]:
    """通道B：链拓扑（重复单元/支链/线性度 + 可选附加）。"""
    import math

    base = [
        min(n_repeats, 100) / 100.0,
        min(n_branch, 10) / 10.0,
        1.0 if linear else 0.0,
        min(math.log1p(n_repeats) / 5.0, 1.0),
        min(math.log1p(n_branch) / 3.0, 1.0),
        (n_repeats % 10) / 10.0,
        float(n_repeats > 10),
        float(n_branch > 2),
    ]
    if extra:
        base = base[: _TOPO_DIMS - len(extra)] + list(extra)
    return base


def embed(smiles: str, n_repeats: int = 1, n_branch: int = 0, linear: bool = True,
          extra: list[float] | None = None) -> list[float]:
    """双通道拼接 embedding。"""
    return monomer_fp(smiles) + topology_feats(n_repeats, n_branch, linear, extra)


def cosine(a: list[float], b: list[float]) -> float:
    num = sum(x * y for x, y in zip(a, b))
    da = sum(x * x for x in a) ** 0.5
    db = sum(y * y for y in b) ** 0.5
    return num / (da * db) if da and db else 0.0


def search(query: list[float], library: dict[str, list[float]], top_k: int = 3) -> list[tuple[str, float]]:
    ranked = sorted(((cosine(query, v), k) for k, v in library.items()), reverse=True)
    return [(k, s) for s, k in ranked[:top_k]]


# ── demo：PE / PS / PEG（同族=同单体重复；异族=不同单体）──

_DEMO = {
    "PE":  ("C", 100, 0),            # 聚乙烯
    "PS":  ("CC1=CC=CC=C1", 100, 0),  # 聚苯乙烯
    "PEG": ("CCO", 80, 0),            # 聚乙二醇
}


def _demo() -> int:
    if not _HAS_RDKIT:
        print("rdkit 未安装——demo 需要（pip install rdkit）")
        return 2
    lib = {name: embed(smi, n, b) for name, (smi, n, b) in _DEMO.items()}
    print("=== 聚合物双通道 embedding demo ===")
    names = list(lib)
    print("相似度矩阵（cosine）:")
    print("      " + "  ".join(f"{n:>6}" for n in names))
    for a in names:
        row = "  ".join(f"{cosine(lib[a], lib[b]):6.3f}" for b in names)
        print(f"{a:>5} {row}")
    # 检索演示：PS 查询应首选 PS 自身，且与 PE/PEG 的相似度 < 自身
    q = lib["PS"]
    hits = search(q, lib, top_k=3)
    print("检索 PS →", [(k, round(s, 3)) for k, s in hits])
    ok = hits[0][0] == "PS" and all(hits[0][1] > s for _, s in hits[1:])
    print("校验：top1=PS 且分高于异族 =", ok)
    return 0 if ok else 1


def main() -> int:
    ap = argparse.ArgumentParser(description="聚合物双通道 embedding（工单227 PoC）")
    ap.add_argument("--demo", action="store_true")
    ap.add_argument("--smiles", help="单体 SMILES")
    ap.add_argument("--repeats", type=int, default=1)
    ap.add_argument("--branch", type=int, default=0)
    args = ap.parse_args()
    if args.demo:
        return _demo()
    if args.smiles:
        if not _HAS_RDKIT:
            print("rdkit 未安装")
            return 2
        v = embed(args.smiles, args.repeats, args.branch)
        print(json.dumps({"dim": len(v), "head": v[:8]}))
        return 0
    ap.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
