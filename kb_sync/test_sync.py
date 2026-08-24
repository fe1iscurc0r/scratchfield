"""WO-04 知识库多实例离线编辑 -> 无冲突合并：随机冲突合并测试。

生成 20 轮（固定种子可复现）冲突合并，每轮覆盖三类并发冲突：
  1. 同一键双向写（Map LWW）
  2. 列表双向插入/删除（Array 序列 CRDT）
  3. 文本双向编辑（Text 文本 CRDT）

断言（真实运行，非 mock）：
  - 双副本合并后状态完全一致（收敛）
  - 无数据丢失（每个未被删除的键/元素/token 恰好出现一次）
  - 无重复键冲突（Map 同键只保留一个 LWW 胜者；列表/文本无重复元素）
  - 合并完整率 == 100%
"""

from __future__ import annotations

import random
from collections import Counter

import pytest

from kb_sync.sync import ENGINE, ENGINE_VERSION, KBDoc

SEED = 20260822
ROUNDS = 20

TOKEN_WIDTH = 6
INITIAL_TEXT_TOKENS = 10
INITIAL_ITEMS = ["s0", "s1", "s2", "s3", "s4"]
INITIAL_META = {"title": "KB-baseline", "status": "draft", "owner": "alice"}


def _tok(n: int) -> str:
    """定长 token（6 字符），保证文本可按定长切分，无子串歧义。"""
    return f"T{n:05d}"


def _new_item(n: int) -> str:
    return f"i{n:05d}"


INITIAL_TOKENS = [_tok(i) for i in range(INITIAL_TEXT_TOKENS)]


def _text_insert(doc: KBDoc, tokens: list[str], index: int, tok: str) -> None:
    tokens.insert(index, tok)
    doc.insert_text(index * TOKEN_WIDTH, tok)


def _text_delete(doc: KBDoc, tokens: list[str], index: int) -> str:
    tok = tokens.pop(index)
    doc.delete_text(index * TOKEN_WIDTH, TOKEN_WIDTH)
    return tok


def _item_insert(doc: KBDoc, items: list[str], index: int, val: str) -> None:
    items.insert(index, val)
    doc.insert_item(index, val)


def _item_delete(doc: KBDoc, items: list[str], index: int) -> str:
    val = items.pop(index)
    doc.delete_item(index)
    return val


def _run_round(case: int) -> dict:
    rng = random.Random(SEED + case)

    # 初始文档 + 两个离线副本（共享初始 item ID）
    base = KBDoc(
        client_id=1,
        meta=dict(INITIAL_META),
        items=list(INITIAL_ITEMS),
        content="".join(INITIAL_TOKENS),
    )
    a = base.clone(2)
    b = base.clone(3)

    # 本地 Python 模型（用于决定随机操作位置 / 独立 oracle）
    a_meta = dict(INITIAL_META)
    b_meta = dict(INITIAL_META)
    a_items = list(INITIAL_ITEMS)
    b_items = list(INITIAL_ITEMS)
    a_tokens = list(INITIAL_TOKENS)
    b_tokens = list(INITIAL_TOKENS)

    next_item_id = len(INITIAL_ITEMS)
    next_token_id = INITIAL_TEXT_TOKENS

    inserted_items: set[str] = set()
    deleted_items: set[str] = set()
    inserted_tokens: set[str] = set()
    deleted_tokens: set[str] = set()

    # ---- 1) 同一键双向写（LWW 冲突） ----
    conflict_key = "status"
    a_val = f"A-{case}-a"
    b_val = f"B-{case}-b"
    a.set_meta(conflict_key, a_val)
    a_meta[conflict_key] = a_val
    b.set_meta(conflict_key, b_val)
    b_meta[conflict_key] = b_val

    # 双方各自独立新增键（无丢失）
    a.set_meta(f"onlyA-{case}", "a")
    a_meta[f"onlyA-{case}"] = "a"
    b.set_meta(f"onlyB-{case}", "b")
    b_meta[f"onlyB-{case}"] = "b"

    # ---- 2) 列表双向插入 + 删除 ----
    shared_item_idx = rng.randint(0, len(INITIAL_ITEMS))
    ia = _new_item(next_item_id)
    next_item_id += 1
    inserted_items.add(ia)
    ib = _new_item(next_item_id)
    next_item_id += 1
    inserted_items.add(ib)
    _item_insert(a, a_items, shared_item_idx, ia)
    _item_insert(b, b_items, shared_item_idx, ib)

    da = _item_delete(a, a_items, rng.randrange(len(a_items)))
    deleted_items.add(da)
    db = _item_delete(b, b_items, rng.randrange(len(b_items)))
    deleted_items.add(db)

    # ---- 3) 文本双向编辑 ----
    shared_text_idx = rng.randint(0, len(INITIAL_TOKENS))
    ta = _tok(next_token_id)
    next_token_id += 1
    inserted_tokens.add(ta)
    tb = _tok(next_token_id)
    next_token_id += 1
    inserted_tokens.add(tb)
    _text_insert(a, a_tokens, shared_text_idx, ta)
    _text_insert(b, b_tokens, shared_text_idx, tb)

    dta = _text_delete(a, a_tokens, rng.randrange(len(a_tokens)))
    deleted_tokens.add(dta)
    dtb = _text_delete(b, b_tokens, rng.randrange(len(b_tokens)))
    deleted_tokens.add(dtb)

    # ---- 追加随机操作（增删改混合） ----
    for _ in range(rng.randint(3, 8)):
        side = rng.choice(["a", "b"])
        if side == "a":
            doc, items, tokens, meta = a, a_items, a_tokens, a_meta
        else:
            doc, items, tokens, meta = b, b_items, b_tokens, b_meta

        op = rng.choice(
            ["meta", "meta", "item_ins", "item_del", "text_ins", "text_del"]
        )
        if op == "meta":
            key = rng.choice(
                ["status", "owner", f"rnd-{case}-{rng.randrange(1000)}"]
            )
            val = f"{side}-{case}-{rng.randrange(100000)}"
            doc.set_meta(key, val)
            meta[key] = val
        elif op == "item_ins":
            val = _new_item(next_item_id)
            next_item_id += 1
            inserted_items.add(val)
            idx = rng.randint(0, len(items))
            _item_insert(doc, items, idx, val)
        elif op == "item_del" and items:
            val = _item_delete(doc, items, rng.randrange(len(items)))
            deleted_items.add(val)
        elif op == "text_ins":
            tok = _tok(next_token_id)
            next_token_id += 1
            inserted_tokens.add(tok)
            idx = rng.randint(0, len(tokens))
            _text_insert(doc, tokens, idx, tok)
        elif op == "text_del" and tokens:
            tok = _text_delete(doc, tokens, rng.randrange(len(tokens)))
            deleted_tokens.add(tok)

    # ---- 同步合并（双向交换 update） ----
    a.merge(b)
    b.merge(a)

    merged_a = a.to_py()
    merged_b = b.to_py()

    # 收敛性
    assert merged_a == merged_b, f"case {case}: 双副本合并后状态不一致"

    merged_meta = merged_a["meta"]
    expected_keys = set(a_meta) | set(b_meta)

    # Map：无重复键冲突 + 无丢失（键只增不删，合并键集合 == 双方键集合的并集）
    assert set(merged_meta) == expected_keys, (
        f"case {case}: meta 键集合不一致，差集={set(merged_meta) ^ expected_keys}"
    )
    assert len(merged_meta) == len(expected_keys), (
        f"case {case}: meta 存在重复键"
    )
    for k in expected_keys:
        if k in a_meta and k in b_meta:
            # 同键双向写按 LWW 收敛，胜者必须是二者之一
            assert merged_meta[k] in (a_meta[k], b_meta[k]), (
                f"case {case}: 同键写 key={k!r} 未按 LWW 收敛 "
                f"merged={merged_meta[k]!r} a={a_meta[k]!r} b={b_meta[k]!r}"
            )
        else:
            want = a_meta[k] if k in a_meta else b_meta[k]
            assert merged_meta[k] == want, f"case {case}: 独立键丢失 key={k!r}"

    # Array：无数据丢失、无重复元素（未被删除的元素恰好出现一次）
    survivor_items = (set(INITIAL_ITEMS) | inserted_items) - deleted_items
    merged_items = merged_a["items"]
    assert Counter(merged_items) == Counter(survivor_items), (
        f"case {case}: 列表数据不一致 "
        f"merged={Counter(merged_items)} expected={Counter(survivor_items)}"
    )
    assert len(merged_items) == len(survivor_items), (
        f"case {case}: 列表存在重复元素"
    )

    # Text：无数据丢失、无重复 token
    survivor_tokens = (set(INITIAL_TOKENS) | inserted_tokens) - deleted_tokens
    text = merged_a["content"]
    assert len(text) % TOKEN_WIDTH == 0, f"case {case}: 文本长度不是 token 整数倍"
    merged_tokens = [text[i : i + TOKEN_WIDTH] for i in range(0, len(text), TOKEN_WIDTH)]
    assert Counter(merged_tokens) == Counter(survivor_tokens), (
        f"case {case}: 文本数据不一致 "
        f"merged={Counter(merged_tokens)} expected={Counter(survivor_tokens)}"
    )
    assert len(merged_tokens) == len(survivor_tokens), (
        f"case {case}: 文本存在重复 token"
    )

    # 完整率 = 实际保留记录数 / 预期保留记录数
    expected_total = len(expected_keys) + len(survivor_items) + len(survivor_tokens)
    actual_total = len(merged_meta) + len(merged_items) + len(merged_tokens)
    completeness = actual_total / expected_total
    assert completeness == 1.0, f"case {case}: 合并完整率 {completeness} != 100%"

    return {
        "meta_keys": len(expected_keys),
        "items": len(survivor_items),
        "text_tokens": len(survivor_tokens),
        "completeness": completeness,
    }


@pytest.mark.parametrize("case", list(range(ROUNDS)))
def test_conflict_merge_round(case: int) -> None:
    """单轮随机冲突合并：收敛 + 无丢失 + 无重复 + 完整率 100%。"""
    _run_round(case)


def test_engine_is_pycrdt() -> None:
    """诚实标注：确认实际使用的是 pycrdt（Yjs 兼容 CRDT），非纯 Python 回退。"""
    assert ENGINE == "pycrdt"
    assert ENGINE_VERSION
    import pycrdt  # noqa: F401

    assert hasattr(pycrdt, "__version__")
