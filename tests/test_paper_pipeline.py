"""工单 275 · T1/T3/T4 验收：断点续跑、预算自停、幂等、对账、类目表。

验收不依赖网络：用 `FakeBackend`（离线、确定性）真跑，
包括"预算自停"与"kill -9 续跑"这两种最容易被 skip 掉的行为。
"""

from __future__ import annotations

import json
import pathlib

import pytest

from research.papers_pipeline.pipeline import (
    CATEGORIES,
    FakeBackend,
    Item,
    Pipeline,
    reconcile,
)

SMALL = tuple(CATEGORIES[:6])


def _wd(tmp_path: pathlib.Path) -> pathlib.Path:
    d = tmp_path / "wd"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _rows(wd: pathlib.Path) -> list[dict]:
    p = wd / "corpus.jsonl"
    return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()] if p.exists() else []


# --------------------------------------------------------------------------- #
# T1 · 预算内自停（主动收尾，exit 0）
# --------------------------------------------------------------------------- #
def test_budget_zero_stops_before_any_category(tmp_path, capsys):
    wd = _wd(tmp_path)
    rc = Pipeline(wd, backend=FakeBackend(), categories=SMALL).run(budget_s=0.0)
    out = capsys.readouterr().out
    assert rc == 0, "预算到点必须 exit 0（主动收尾 ≠ 被超时杀掉）"
    assert out.startswith("PARTIAL:")
    assert f"next={SMALL[0]}" in out
    assert _rows(wd) == [], "预算 0 时不应写任何记录"


def test_budget_stops_midway_and_next_advances(tmp_path, capsys):
    """**三次 `--budget` 连跑**：每次 exit 0、`next=` 依次前进、最后一次打印 DONE、corpus 不膨胀。

    用**可控时钟**代替真实时间：每次取时钟前进 0.02 s，预算 0.05 s ⇒ 每次只做 **2 个**类目（首个 tick 被 t0 吃掉），
    6 个类目正好「两次 PARTIAL + 一次 DONE」。这样判据不随机器速度抖动（实测曾因抖动只出现 1 次 PARTIAL）。
    """
    wd = _wd(tmp_path)
    tick = {"n": 0}

    def clock() -> float:
        tick["n"] += 1
        return tick["n"] * 0.02

    seen_next: list[str] = []
    outs: list[str] = []
    for _ in range(3):
        capsys.readouterr()
        rc = Pipeline(wd, backend=FakeBackend(), categories=SMALL).run(0.05, clock=clock)
        out = capsys.readouterr().out.strip()
        outs.append(out)
        assert rc == 0, "每次都必须 exit 0"
        if out.startswith("PARTIAL:"):
            nxt = out.split("next=")[1].split()[0]
            assert nxt not in seen_next, f"next 未前进：{seen_next} → {nxt}"
            seen_next.append(nxt)
        else:
            assert out.startswith("DONE."), out

    assert len(seen_next) == 2, f"6 类 / 每次 2 类 ⇒ 应两次 PARTIAL，实际 {seen_next}"
    assert outs[-1].startswith("DONE."), f"最后一次应 DONE，实际 {outs[-1]}"
    assert len(_rows(wd)) == len(SMALL) * 7
    # 跑完后再跑一次：行数不变（幂等）
    before = len(_rows(wd))
    Pipeline(wd, backend=FakeBackend(), categories=SMALL).run(300)
    assert len(_rows(wd)) == before, "重跑导致 corpus 膨胀 ⇒ 幂等失效"


# --------------------------------------------------------------------------- #
# T1 · kill -9 后原位续跑，不重复写
# --------------------------------------------------------------------------- #
def test_resume_after_hard_kill_does_not_duplicate(tmp_path):
    wd = _wd(tmp_path)
    # 第一次：抓 2 个类目后被"杀掉"
    with pytest.raises(KeyboardInterrupt):
        Pipeline(wd, backend=FakeBackend(fail_after=2), categories=SMALL).run(budget_s=300)
    prog1 = [json.loads(l) for l in (wd / "progress.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    rows1 = _rows(wd)
    assert len(prog1) == 2, "被杀的进程只应留下已完成类目的进度"
    assert len(rows1) == 14  # 2 类 × 7 条

    # 第二次：正常跑完，必须从第 3 个类目继续
    rc = Pipeline(wd, backend=FakeBackend(), categories=SMALL).run(budget_s=300)
    assert rc == 0
    prog2 = [json.loads(l) for l in (wd / "progress.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    assert len(prog2) == len(SMALL), f"续跑应补齐到 {len(SMALL)} 类，实际 {len(prog2)}"
    assert len({p["category"] for p in prog2[:2]}) == 2 and len(prog2) == len(SMALL)
    # 不重复：每个 (category, base_id) 只有一行
    rows2 = _rows(wd)
    keys = [(r["category"], r["base_id"]) for r in rows2]
    assert len(keys) == len(set(keys)), "续跑产生了重复行"
    assert len(rows2) == len(SMALL) * 7


def test_idempotent_rerun(tmp_path):
    wd = _wd(tmp_path)
    Pipeline(wd, backend=FakeBackend(), categories=SMALL).run(budget_s=300)
    n1 = len(_rows(wd))
    Pipeline(wd, backend=FakeBackend(), categories=SMALL).run(budget_s=300)
    assert len(_rows(wd)) == n1


def test_new_version_updates_in_place(tmp_path):
    """同一 base 的新版本必须**更新版本字段**，而不是追加整行。"""
    wd = _wd(tmp_path)
    p = Pipeline(wd, backend=FakeBackend(per_category=2), categories=("cs.AI",))
    p.run(budget_s=300)
    assert len(_rows(wd)) == 2 and reconcile(wd)["versions"] == 0

    class V2Backend:
        def fetch(self, category, cursor, max_results):
            return [Item(category, _rows(wd)[0]["base_id"], 2, "updated", "2026-10-22")], cursor + 1, False

    p2 = Pipeline(wd, backend=V2Backend(), categories=("cs.AI",))
    p2._append_progress({"category": "cs.AI", "fetched": 2, "cursor": 2, "ts": 0})  # 绕过断点
    p2._write_items(V2Backend().fetch("cs.AI", 0, 2)[0], p2._load_index())
    rows = _rows(wd)
    assert len(rows) == 2, "版本更新不应新增行"
    assert max(r["version"] for r in rows) == 2


# --------------------------------------------------------------------------- #
# T3 · 对账三数
# --------------------------------------------------------------------------- #
def test_reconcile_three_numbers(tmp_path):
    wd = _wd(tmp_path)
    Pipeline(wd, backend=FakeBackend(), categories=SMALL).run(budget_s=300)
    res = reconcile(wd)
    assert set(res) == {"unique_base", "versions", "processed"}
    assert res["processed"] == len(_rows(wd))
    assert res["unique_base"] <= res["processed"]
    assert res["versions"] <= res["processed"]
    assert res["unique_base"] == len({(r["category"], r["base_id"]) for r in _rows(wd)})


# --------------------------------------------------------------------------- #
# T4 · 类目表
# --------------------------------------------------------------------------- #
def test_category_table_uses_cs_et_not_cs_es():
    assert "cs.ET" in CATEGORIES, "类目表必须含 cs.ET"
    assert "cs.ES" not in CATEGORIES, "cs.ES 的 totalResults=0，必须换掉"
    assert len(CATEGORIES) == 31, f"类目数应为 31，实际 {len(CATEGORIES)}"


# --------------------------------------------------------------------------- #
# T2 · 权重开关默认关
# --------------------------------------------------------------------------- #
def test_weight_switch_defaults_off():
    cfg = pathlib.Path("research/papers_pipeline/config.example.yaml").read_text(encoding="utf-8")
    assert "collect_weight_overrides:" in cfg
    assert "enabled: false" in cfg, "T2 开关必须默认关闭"
    assert "physics.app-ph" in cfg and "cs.CE" in cfg
