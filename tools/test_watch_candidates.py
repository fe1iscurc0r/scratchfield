"""watch_candidates 的纯函数单测（不依赖网络/pytest）。

可两种方式跑：
    python3 tools/test_watch_candidates.py        # 直接跑（stdlib）
    pytest tools/test_watch_candidates.py         # 仓内惯用方式

只测 diff_one（纯函数）——网络取数（fetch_repo）不在此层，属集成验证。
"""

from watch_candidates import diff_one  # 与 tools/test_skill_gate.py 同款同级导入约定


def test_no_change_is_silent():
    before = {"stars": 10, "pushed_at": "2026-09-01T00:00:00Z", "license": "MIT", "archived": False}
    assert diff_one(before, dict(before)) == []


def test_star_change_detected():
    before = {"stars": 10, "pushed_at": "T", "license": "MIT", "archived": False}
    after = {"stars": 12, "pushed_at": "T", "license": "MIT", "archived": False}
    changes = diff_one(before, after)
    assert len(changes) == 1 and "stars 10 → 12" in changes[0]


def test_pushed_at_change_detected():
    before = {"stars": 1, "pushed_at": "2026-09-01T00:00:00Z", "license": "", "archived": False}
    after = {"stars": 1, "pushed_at": "2026-09-23T00:00:00Z", "license": "", "archived": False}
    assert "最近推送" in diff_one(before, after)[0]


def test_license_appearance_detected():
    """无许可 → 出现许可：这是最该报警的一类变化（许可铁律）。"""
    before = {"stars": 0, "pushed_at": "T", "license": "", "archived": False}
    after = {"stars": 0, "pushed_at": "T", "license": "MIT", "archived": False}
    changes = diff_one(before, after)
    assert len(changes) == 1 and "许可 无 → MIT" in changes[0]


def test_new_repo_reported_once():
    after = {"stars": 3, "pushed_at": "T", "license": "Apache-2.0", "archived": False}
    changes = diff_one(None, after)
    assert len(changes) == 1 and "新增观察" in changes[0]


def test_missing_repo_no_false_alarm_when_not_in_baseline():
    """基线里没有的仓取到 404 → 不报警（避免无谓噪音）。"""
    assert diff_one(None, {"missing": True}) == []


def test_missing_repo_alerts_when_baseline_had_it():
    """基线里有、现在 404 → 必须报警（仓被删/转私有）。"""
    before = {"stars": 5, "pushed_at": "T", "license": "MIT", "archived": False}
    changes = diff_one(before, {"missing": True})
    assert len(changes) == 1 and "不可见" in changes[0]


def test_archived_flip_detected():
    before = {"stars": 1, "pushed_at": "T", "license": "MIT", "archived": False}
    after = {"stars": 1, "pushed_at": "T", "license": "MIT", "archived": True}
    assert "归档状态" in diff_one(before, after)[0]


def test_multiple_changes_all_reported():
    before = {"stars": 1, "pushed_at": "A", "license": "", "archived": False}
    after = {"stars": 9, "pushed_at": "B", "license": "MIT", "archived": True}
    assert len(diff_one(before, after)) == 4


if __name__ == "__main__":
    import traceback

    passed = failed = 0
    for name, fn in sorted(globals().items()):
        if not name.startswith("test_") or not callable(fn):
            continue
        try:
            fn()
            print(f"PASS  {name}")
            passed += 1
        except Exception:
            print(f"FAIL  {name}")
            traceback.print_exc()
            failed += 1
    print(f"\n{passed} passed, {failed} failed")
    raise SystemExit(1 if failed else 0)
