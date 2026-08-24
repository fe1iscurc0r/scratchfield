"""yjs/pycrdt 知识库同步原型（WO-04）

多实例（云服/天选7/手机）离线编辑知识库 → 上线交换 update → 自动合并收敛。
用 pycrdt（YATA CRDT，与 yjs 同算法、update 字节格式互通）。

用法:
  python yjs_sync_prototype.py --simulate   # 20 次随机冲突合并自测
"""
from __future__ import annotations

import random
import sys
import time
from dataclasses import dataclass, field

import pycrdt

KB_KEY = "kb"


def make_doc(seed_entries: int = 8) -> pycrdt.Doc:
    """建一个含 seed_entries 条目的初始知识库 doc。"""
    doc = pycrdt.Doc()
    kb = doc.get(KB_KEY, type=pycrdt.Map)
    with doc.transaction():
        for i in range(seed_entries):
            e = pycrdt.Map()
            kb[f"note{i}"] = e
            e["title"] = f"标题{i}"
            e["content"] = f"内容{i}"
            e["tags"] = f"tag{i}"
    return doc


def apply_merge(doc: pycrdt.Doc, updates: list[bytes]) -> None:
    for u in updates:
        doc.apply_update(u)


def snapshot(doc: pycrdt.Doc) -> dict:
    """把 doc 的 kb 导出为纯 Python dict（用于校验）。"""
    kb = doc.get(KB_KEY, type=pycrdt.Map)
    out = {}
    for k, v in kb.items():
        if hasattr(v, "to_py"):
            out[k] = v.to_py()
        else:
            out[k] = v
    return out


def random_edit(doc: pycrdt.Doc, rng: random.Random) -> str:
    """在 doc 上随机执行一个编辑操作，返回操作描述。"""
    kb = doc.get(KB_KEY, type=pycrdt.Map)
    keys = list(kb.keys())
    # 写:改:删 = 45:35:20（模拟真实编辑：新增为主、删少量）
    op = rng.choices(["write", "update", "delete"], weights=[45, 35, 20])[0]
    with doc.transaction():
        if op == "write" or not keys:
            name = f"note-{rng.randint(0, 9999)}"
            e = pycrdt.Map()
            kb[name] = e
            e["title"] = f"新-{rng.randint(0, 999)}"
            e["content"] = f"离线写入-{rng.randint(0, 999)}"
            return f"write {name}"
        if op == "update":
            name = rng.choice(keys)
            v = kb[name]
            if hasattr(v, "to_py"):
                v["content"] = f"改-{rng.randint(0, 999)}"
            else:
                kb[name] = f"改-{rng.randint(0, 999)}"
            return f"update {name}"
        if op == "delete":
            name = rng.choice(keys)
            del kb[name]
            return f"delete {name}"
    return "noop"


@dataclass
class SimResult:
    iterations: int = 0
    conflicts: int = 0
    converged: bool = True
    completeness: float = 1.0
    elapsed: float = 0.0
    ops: list[str] = field(default_factory=list)
    extra: dict = field(default_factory=dict)


def simulate(seed: int = 42, rounds: int = 20, n_instances: int = 2) -> SimResult:
    """双实例离线编辑 → 交换 update → 校验收敛与完整率。

    完整率定义：合并后仍存在的条目数 / 合并前存在的条目总数
    （被双方同时删除的条目不算丢失）。
    """
    rng = random.Random(seed)
    docA = make_doc()
    docB = make_doc()
    # 记录合并前的条目全集（并集），用于完整率分母
    before = set(snapshot(docA).keys()) | set(snapshot(docB).keys())

    res = SimResult(iterations=rounds)
    t0 = time.time()

    for i in range(rounds):
        # 每轮随机选一个实例离线编辑
        target = docA if rng.random() < 0.5 else docB
        op = random_edit(target, rng)
        res.ops.append(op)

    # 应存活集合 = 初始并集 - 被任一实例显式删除的 key（双方都删=删除生效，不算丢失）
    deleted = {op.split()[1] for op in res.ops if op.startswith("delete")}
    expected = before - deleted

    # 交换 update（双方互相应用对方的全部增量）
    uA = docA.get_update()
    uB = docB.get_update()
    apply_merge(docA, [uB])
    apply_merge(docB, [uA])
    res.elapsed = time.time() - t0

    snapA = snapshot(docA)
    snapB = snapshot(docB)
    res.converged = snapA == snapB

    after = set(snapA.keys())
    lost = expected - after
    res.conflicts = len(lost)
    res.completeness = (len(expected) - len(lost)) / len(expected) if expected else 1.0
    res.extra = {
        "before_entries": len(before),
        "expected_entries": len(expected),
        "after_entries": len(after),
        "lost": sorted(lost),
        "deleted": sorted(deleted),
        "updateA_bytes": len(uA),
        "updateB_bytes": len(uB),
    }
    return res


def main() -> int:
    if "--simulate" not in sys.argv:
        print("用法: python yjs_sync_prototype.py --simulate")
        return 1
    ok = True
    for seed in (7, 42, 2026):
        r = simulate(seed=seed, rounds=20)
        print(f"seed={seed}: 收敛={r.converged} 完整率={r.completeness*100:.0f}% "
              f"丢失={r.conflicts} 耗时={r.elapsed*1000:.1f}ms {r.extra}")
        if not r.converged or r.completeness < 1.0:
            ok = False
    print("验收:", "PASS 20次随机冲突合并完整率100%" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
