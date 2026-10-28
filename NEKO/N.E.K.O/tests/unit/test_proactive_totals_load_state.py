"""WO-272 / P0-19 —— ``proactive_chat_totals.json`` 的三态加载与「拒绝截断」验收。

工单验收项（原文）：
  1. 写坏 ``proactive_chat_totals.json``（截断一个字符）后启动：断言 ``_loaded`` 为
     False（或 ``failed`` 标记存在）、后续 increment 不修改磁盘文件、``*.bak`` 未生成
     （因为没写）。
  2. 正常路径回归：缺失文件 → 首次 increment 建文件；正常文件 → 计数累加正确。

外加两条本单自带的契约：恢复可读时把被挡期间的增量叠回磁盘基线（既不算错也不丢账），
以及任何全量覆盖写之前先留一份 ``*.bak``。
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from main_logic.proactive_chat import state


def store_snapshot() -> dict:
    return {
        "totals": dict(state._proactive_chat_totals),
        "ever": dict(state._invite_ever_delivered),
        "loaded": state._proactive_chat_totals_loaded,
        "loaded_path": state._proactive_chat_totals_loaded_path,
        "load_state": state._proactive_chat_totals_load_state,
        "delta": dict(state._proactive_chat_totals_pending_delta),
        "pending_ever": set(state._proactive_chat_totals_pending_ever_delivered),
        "read_failures": state._proactive_chat_totals_read_failures,
        "write_refusals": state._proactive_chat_totals_write_refusals,
    }


def store_reset() -> None:
    state._proactive_chat_totals.clear()
    state._invite_ever_delivered.clear()
    state._proactive_chat_totals_pending_delta.clear()
    state._proactive_chat_totals_pending_ever_delivered.clear()
    state._proactive_chat_totals_loaded = False
    state._proactive_chat_totals_loaded_path = None
    state._proactive_chat_totals_load_state = "unloaded"
    state._proactive_chat_totals_read_failures = 0
    state._proactive_chat_totals_write_refusals = 0


def store_restore(s: dict) -> None:
    state._proactive_chat_totals.clear()
    state._proactive_chat_totals.update(s["totals"])
    state._invite_ever_delivered.clear()
    state._invite_ever_delivered.update(s["ever"])
    state._proactive_chat_totals_pending_delta.clear()
    state._proactive_chat_totals_pending_delta.update(s["delta"])
    state._proactive_chat_totals_pending_ever_delivered.clear()
    state._proactive_chat_totals_pending_ever_delivered.update(s["pending_ever"])
    state._proactive_chat_totals_loaded = s["loaded"]
    state._proactive_chat_totals_loaded_path = s["loaded_path"]
    state._proactive_chat_totals_load_state = s["load_state"]
    state._proactive_chat_totals_read_failures = s["read_failures"]
    state._proactive_chat_totals_write_refusals = s["write_refusals"]


@pytest.fixture(autouse=True)
def _pristine_totals_store(monkeypatch, tmp_path):
    """把计数存储的全部模块级状态归零，并把持久化根指到 tmp_path。

    这个存储是进程级单例，别处的残留会让本单的「缺失文件」分支变样，所以 setup /
    teardown 都要显式管一遍——包括本单新增的 load_state 与两张重放账本。
    """
    monkeypatch.setattr(
        state, "get_config_manager", lambda: SimpleNamespace(memory_dir=tmp_path)
    )
    saved = store_snapshot()
    store_reset()
    yield tmp_path
    store_restore(saved)


def _totals_path() -> state.Path:
    return state._proactive_chat_totals_path()


def _bak_path() -> state.Path:
    return state._proactive_chat_totals_backup_path(_totals_path())


def _write_valid(baseline: dict) -> bytes:
    _totals_path().write_text(
        json.dumps(
            {"version": 2, "totals": baseline, "ever_delivered": {}},
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return _totals_path().read_bytes()


def _read_disk() -> dict:
    return json.loads(_totals_path().read_text(encoding="utf-8"))


@pytest.mark.asyncio
async def test_corrupt_file_is_failed_not_loaded_and_blocks_every_write():
    """验收 1：截断一个字符 ⇒ failed；后续 increment 不动磁盘；不产生 .bak。"""
    good = _write_valid({"Yui": 7, "Akari": 3})
    _totals_path().write_bytes(good[:-1])  # 「截断一个字符」

    assert await state._ensure_proactive_chat_totals_loaded() is False
    assert state._proactive_chat_totals_loaded is False
    assert state._proactive_chat_totals_load_state == "failed"

    before = _totals_path().read_bytes()
    new_value = await state._increment_proactive_chat_total("Yui")

    # 内存照常 +1（她这一轮的判断还要用），但磁盘必须一个字节都没变
    assert new_value == 1
    assert _totals_path().read_bytes() == before
    assert _bak_path().exists() is False
    assert state._proactive_chat_totals_write_refusals >= 1

    health = state.proactive_chat_totals_load_state()
    assert health["state"] == "failed"
    assert health["loaded"] is False
    assert health["pending_delta"] == {"Yui": 1}


@pytest.mark.asyncio
async def test_recovery_replays_pending_delta_onto_the_disk_baseline():
    """文件修好后：磁盘基线不丢，被挡期间的增量与 ever_delivered 一起补回。"""
    good = _write_valid({"Yui": 7, "Akari": 3})
    _totals_path().write_bytes(good[:-1])

    assert await state._ensure_proactive_chat_totals_loaded() is False
    await state._increment_proactive_chat_total("Yui")
    # 挡住期间的 invite：+1 与 ever_delivered 都只活在内存 + 账本里
    invite_value = await state._record_invite_delivery_persistent("Yui")
    assert invite_value == 2
    assert state._proactive_chat_totals_write_refusals >= 2
    assert _totals_path().read_bytes() == good[:-1]

    _totals_path().write_bytes(good)  # 人工修好文件
    new_value = await state._increment_proactive_chat_total("Yui")

    # 7（磁盘基线）+ 2（补回）+ 1（本次）= 10；Akari 一位没掉
    assert new_value == 10
    assert state._proactive_chat_totals_load_state == "loaded"
    assert state.proactive_chat_totals_load_state()["pending_delta"] == {}
    disk = _read_disk()
    assert disk["totals"] == {"Yui": 10, "Akari": 3}
    assert disk["ever_delivered"] == {"Yui": True}
    assert state._was_invite_ever_delivered("Yui") is True
    # 覆盖写之前留了 .bak（写前的那一份）
    assert _bak_path().exists() is True


@pytest.mark.asyncio
async def test_missing_file_first_increment_creates_it_without_backup():
    """验收 2 前半：缺失文件 ⇒ missing 态（不是 failed），首次 increment 建文件。"""
    assert _totals_path().exists() is False

    assert await state._ensure_proactive_chat_totals_loaded() is True
    assert state._proactive_chat_totals_loaded is True
    assert state._proactive_chat_totals_load_state == "missing"

    assert await state._increment_proactive_chat_total("Yui") == 1
    assert _read_disk()["totals"] == {"Yui": 1}
    # 没有旧文件可备份 —— .bak 不该凭空出现
    assert _bak_path().exists() is False


@pytest.mark.asyncio
async def test_normal_file_accumulates_and_backs_up_before_each_overwrite():
    """验收 2 后半：正常文件累加正确，且每次全量覆盖写前 .bak 是写前那一版。"""
    _write_valid({"Yui": 7, "Akari": 3})

    assert await state._increment_proactive_chat_total("Yui") == 8
    assert _read_disk()["totals"] == {"Yui": 8, "Akari": 3}
    assert json.loads(_bak_path().read_text(encoding="utf-8"))["totals"] == {
        "Yui": 7,
        "Akari": 3,
    }

    assert await state._increment_proactive_chat_total("Yui") == 9
    assert await state._increment_proactive_chat_total("Akari") == 4
    assert _read_disk()["totals"] == {"Yui": 9, "Akari": 4}
    # .bak 只保最近 1 份 = 最后一次覆盖写之前的那一版
    assert json.loads(_bak_path().read_text(encoding="utf-8"))["totals"] == {
        "Yui": 9,
        "Akari": 3,
    }


@pytest.mark.asyncio
async def test_write_without_load_is_refused():
    """没读过就写（state=unloaded）同样是截断，一并挡掉——挡住的是「内存空 ⇒ 覆盖全盘」。"""
    _write_valid({"Yui": 7, "Akari": 3})
    before = _totals_path().read_bytes()

    assert await state._persist_totals_unlocked() is False
    assert _totals_path().read_bytes() == before
    assert state._proactive_chat_totals_write_refusals == 1
