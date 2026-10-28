"""工单255 任务B 的测试：LoRa 折中表 + WuRX 占空比预算（离线）。

关键纪律：本模块**必须** import 复用 `lora_phy`（工单242 唯一真值源），不得复制公式。
跑法（仓库根）：
    python -m pytest tools/test_lora_power_tradeoff.py -q
"""
from __future__ import annotations

import json
import math
from pathlib import Path

from mcpserver.rf_workflow import lora_phy
from mcpserver.rf_workflow import lora_power_tradeoff as lt


def test_link_table_shape() -> None:
    """SF7–12 × BW 125/250 × CR4/5–4/8 ⇒ 6×2×4 = 48 行。"""
    rows = lt.link_tradeoff_table()
    assert len(rows) == len(lt.SF_LIST) * len(lt.BW_LIST_HZ) * len(lt.CR_LIST) == 48
    assert {r["sf"] for r in rows} == set(lt.SF_LIST)
    assert {r["bw_khz"] for r in rows} == {125.0, 250.0}
    assert {r["cr"] for r in rows} == {"4/5", "4/6", "4/7", "4/8"}


def test_sensitivity_scales_with_bw() -> None:
    """带宽翻倍 ⇒ 灵敏度按 10*log10(2) ≈ +3.01 dB 变差（热噪声缩放口径）。"""
    for sf in lt.SF_LIST:
        s125 = lora_phy.sensitivity_dbm(sf, 125_000.0)
        s250 = lora_phy.sensitivity_dbm(sf, 250_000.0)
        assert math.isclose(s250 - s125, 10.0 * math.log10(2.0), abs_tol=1e-9)


def test_table_matches_lora_phy_directly() -> None:
    """表里的值必须与直接调 lora_phy 一致（证明走的是复用而不是抄公式）。"""
    row = next(r for r in lt.link_tradeoff_table() if r["sf"] == 9 and r["bw_khz"] == 125.0
               and r["cr"] == "4/5")
    toa = lora_phy.time_on_air_s(9, 125_000.0, lt.PAYLOAD_BYTES, cr=1)
    assert row["toa_ms"] == round(toa * 1000.0, 2)
    assert row["sensitivity_dbm"] == round(lora_phy.sensitivity_dbm(9, 125_000.0), 2)
    assert row["nominal_bitrate_bps"] == round(lora_phy.nominal_bitrate_bps(9, 125_000.0, cr=1), 1)
    assert row["energy_per_bit_uj"] == round(
        lora_phy.energy_per_bit_j(lt.TX_POWER_DBM, toa, lt.PAYLOAD_BYTES) * 1e6, 3)


def test_toa_increases_with_sf_and_bitrate_decreases() -> None:
    rows = [r for r in lt.link_tradeoff_table() if r["bw_khz"] == 125.0 and r["cr"] == "4/5"]
    rows.sort(key=lambda r: r["sf"])
    toas = [r["toa_ms"] for r in rows]
    rates = [r["nominal_bitrate_bps"] for r in rows]
    assert toas == sorted(toas) and len(set(toas)) == len(toas), "ToA 应随 SF 单调递增"
    assert rates == sorted(rates, reverse=True), "标称速率应随 SF 单调递减"


def test_no_formula_duplication() -> None:
    """源码里必须出现 `from .lora_phy import`（工单验收 3 的口径）。"""
    src = Path(lt.__file__).read_text(encoding="utf-8")
    assert "from .lora_phy import" in src
    # 反向：不允许出现 ToA/灵敏度的手写公式碎片
    for forbidden in ("log10(2**", "4.25 * ", "(28", "SENSITIVITY_DBM_BW125.get("):
        assert forbidden not in src, f"疑似复制公式：{forbidden}"


def test_duty_budget_rows_and_violation() -> None:
    """5 个唤醒周期；0.5 s ⇒ 占空比 20% > 限值 ⇒ VIOLATION；10 s ⇒ OK。"""
    rows = lt.wurex_duty_budget()
    assert len(rows) == len(lt.WAKE_PERIODS_S) == 5
    by_period = {r["wake_period_s"]: r for r in rows}
    assert by_period[0.5]["main_rx_duty_pct"] == 20.0
    assert by_period[0.5]["compliance"] == "VIOLATION"
    assert by_period[10.0]["main_rx_duty_pct"] == 1.0
    assert by_period[10.0]["compliance"] == "OK"
    # 限值来自 lora_phy（不是本模块自己写死）
    assert all(r["duty_limit_pct"] == lora_phy.DUTY_CYCLE_LIMIT_PCT for r in rows)
    # 省电率随唤醒周期放宽而单调上升
    saved = [r["energy_saved_pct"] for r in rows]
    assert saved == sorted(saved)


def test_violation_threshold_is_strictly_greater() -> None:
    """恰好等于限值时不算违例（1.0 s ⇒ 10.0% == 限值 ⇒ OK）。"""
    row = next(r for r in lt.wurex_duty_budget() if r["wake_period_s"] == 1.0)
    assert row["main_rx_duty_pct"] == lora_phy.DUTY_CYCLE_LIMIT_PCT
    assert row["compliance"] == "OK"


def test_json_mode_serializable(capsys) -> None:
    assert lt.main(["--demo", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert len(payload["link_tradeoff"]) == 48
    assert len(payload["wurex_duty_budget"]) == 5


def test_cli_demo_prints_units(capsys) -> None:
    """表头必须带单位（dBm / ms / µJ / bps）。"""
    assert lt.main(["--demo"]) == 0
    out = capsys.readouterr().out
    for unit in ("dBm", "ms", "µJ", "bps"):
        assert unit in out, f"表头缺单位 {unit}"
    assert "VIOLATION" in out
