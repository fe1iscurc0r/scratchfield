"""LoRa 噪声-功耗折中表 + WuRX 占空比预算（工单255 任务B）。

## 授粉点（论文 → 本模块哪一层 → 为什么这样取舍）

| 论文 | 机制 | 落到本模块 | 取舍 |
|---|---|---|---|
| 2610.20677 | LoRa 兼容接收机 + **可编程噪声-功耗折中** + 集成唤醒（WuRX），免掉独立 WuRX 的功耗/面积/复杂度 | 表 A（SF×BW×CR 的灵敏度/ToA/每比特能耗/速率折中）+ 表 B（唤醒周期 × 主接收占空比 vs 常开监听） | **只借"折中关系"这一层的口径**，不复制任何论文电路参数；WuRX/主接收功耗是**显式可替换参数**，见 `DEFAULT_POWER` |
| 2610.22304 / 2610.21968 | 「何时传」的能量约束 | 由 `telemetry_scheduler.py` 承载（本模块只管**单次传输的物理代价**) | 分工：本模块算"发一次的代价"，调度模块算"什么时候值得发" |

⚠️ 本模块交付**口径与可跑基线**，不是论文实验数值的复现。

## 真值源纪律

所有 LoRa 物理量**一律 import `lora_phy`**（工单242 的唯一真值源）：
`sensitivity_dbm` / `time_on_air_s` / `nominal_bitrate_bps` / `energy_per_bit_j` / `DUTY_CYCLE_LIMIT_PCT`。
**不得复制粘贴公式**；发现既有公式与手册不符时**先报不改**（另开单）。

## 复现

    python -m mcpserver.rf_workflow.lora_power_tradeoff --demo
    python -m mcpserver.rf_workflow.lora_power_tradeoff --demo --json
"""
from __future__ import annotations

import argparse
import json

from .lora_phy import (
    DUTY_CYCLE_LIMIT_PCT,
    energy_per_bit_j,
    nominal_bitrate_bps,
    sensitivity_dbm,
    time_on_air_s,
)

PAYLOAD_BYTES = 16          # 工单指定：ToA 按 16 B 载荷
TX_POWER_DBM = 14.0         # 典型 LoRa 模块发射功率（非法规上限；法规口径见 lora_phy.REGULATORY_NOTE）
SF_LIST = (7, 8, 9, 10, 11, 12)
BW_LIST_HZ = (125_000.0, 250_000.0)
CR_LIST = (1, 2, 3, 4)      # 4/(4+CR) ⇒ 4/5, 4/6, 4/7, 4/8

# WuRX / 主接收机的**可替换**功耗口径（工程近似，不是某篇论文的参数）
DEFAULT_POWER = {
    "wake_receiver_uw": 10.0,      # 唤醒接收机常开功耗（µW）
    "main_rx_mw": 30.0,            # 主接收机监听功耗（mW）
    "wake_window_s": 0.1,          # 每次唤醒后主接收机开机时长（s）
    "seconds_per_day": 86_400.0,
}
WAKE_PERIODS_S = (0.5, 1.0, 2.0, 5.0, 10.0)


def link_tradeoff_table(payload_bytes: int = PAYLOAD_BYTES, tx_power_dbm: float = TX_POWER_DBM,
                        sf_list: tuple[int, ...] = SF_LIST,
                        bw_list: tuple[float, ...] = BW_LIST_HZ,
                        cr_list: tuple[int, ...] = CR_LIST) -> list[dict]:
    """表 A：SF × BW × CR 的折中关系（灵敏度 dBm / ToA ms / 每比特能耗 µJ / 标称速率 bps）。"""
    rows: list[dict] = []
    for sf in sf_list:
        for bw in bw_list:
            for cr in cr_list:
                toa = time_on_air_s(sf, bw, payload_bytes, cr=cr)
                rows.append({
                    "sf": sf,
                    "bw_khz": bw / 1000.0,
                    "cr": f"4/{4 + cr}",
                    "sensitivity_dbm": round(sensitivity_dbm(sf, bw), 2),
                    "toa_ms": round(toa * 1000.0, 2),
                    "energy_per_bit_uj": round(energy_per_bit_j(tx_power_dbm, toa, payload_bytes) * 1e6, 3),
                    "nominal_bitrate_bps": round(nominal_bitrate_bps(sf, bw, cr=cr), 1),
                })
    return rows


def wurex_duty_budget(wake_periods_s: tuple[float, ...] = WAKE_PERIODS_S,
                      power: dict | None = None) -> list[dict]:
    """表 B：唤醒周期 × 主接收占空比 vs 常开监听 → 日均能耗 + 占空比合规检查。

    占空比 = 唤醒窗长 / 唤醒周期；超过 `lora_phy.DUTY_CYCLE_LIMIT_PCT` 记 ``VIOLATION``。
    """
    p = dict(DEFAULT_POWER if power is None else power)
    day = p["seconds_per_day"]
    wake_rx_w = p["wake_receiver_uw"] * 1e-6
    main_rx_w = p["main_rx_mw"] * 1e-3
    always_on_j = main_rx_w * day

    rows: list[dict] = []
    for period in wake_periods_s:
        duty_pct = 100.0 * p["wake_window_s"] / period
        wakes_per_day = day / period
        main_rx_j = main_rx_w * p["wake_window_s"] * wakes_per_day
        wake_rx_j = wake_rx_w * day
        total_j = main_rx_j + wake_rx_j
        rows.append({
            "wake_period_s": period,
            "main_rx_duty_pct": round(duty_pct, 2),
            "wakes_per_day": round(wakes_per_day, 1),
            "daily_energy_j": round(total_j, 2),
            "always_on_energy_j": round(always_on_j, 2),
            "energy_saved_pct": round(100.0 * (1.0 - total_j / always_on_j), 2),
            "duty_limit_pct": DUTY_CYCLE_LIMIT_PCT,
            "compliance": "VIOLATION" if duty_pct > DUTY_CYCLE_LIMIT_PCT else "OK",
        })
    return rows


def _fmt_table(rows: list[dict], columns: list[tuple[str, str]]) -> str:
    """把 dict 行渲染成等宽表；列名带单位。"""
    head = tuple(label for _, label in columns)
    body = [tuple(str(r[key]) for key, _ in columns) for r in rows]
    widths = [max(len(str(head[i])), max((len(b[i]) for b in body), default=0)) for i in range(len(head))]
    lines = ["  ".join(str(c).ljust(widths[i]) for i, c in enumerate(head))]
    lines.append("  ".join("-" * w for w in widths))
    lines += ["  ".join(b[i].ljust(widths[i]) for i in range(len(head))) for b in body]
    return "\n".join(lines)


LINK_COLUMNS = [
    ("sf", "SF"), ("bw_khz", "BW(kHz)"), ("cr", "CR"),
    ("sensitivity_dbm", "灵敏度(dBm)"), ("toa_ms", "ToA(ms)"),
    ("energy_per_bit_uj", "每比特能耗(µJ)"), ("nominal_bitrate_bps", "标称速率(bps)"),
]
BUDGET_COLUMNS = [
    ("wake_period_s", "唤醒周期(s)"), ("main_rx_duty_pct", "主接收占空比(%)"),
    ("wakes_per_day", "唤醒次数/日"), ("daily_energy_j", "日均能耗(J)"),
    ("always_on_energy_j", "常开监听(J)"), ("energy_saved_pct", "省电(%)"),
    ("duty_limit_pct", "限值(%)"), ("compliance", "合规"),
]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="LoRa 噪声-功耗折中表 + WuRX 占空比预算（工单255 任务B）")
    ap.add_argument("--demo", action="store_true", help="打印两张表")
    ap.add_argument("--json", action="store_true", help="输出 JSON（机读）")
    ap.add_argument("--tx-power-dbm", type=float, default=TX_POWER_DBM,
                    help=f"发射功率（dBm），默认 {TX_POWER_DBM}")
    args = ap.parse_args(argv)

    link = link_tradeoff_table(tx_power_dbm=args.tx_power_dbm)
    budget = wurex_duty_budget()

    if args.json:
        print(json.dumps({"link_tradeoff": link, "wurex_duty_budget": budget},
                         ensure_ascii=False, indent=1))
        return 0

    print("LoRa 噪声-功耗折中表（工单255 任务B）")
    print(f"发射功率 = {args.tx_power_dbm} dBm；载荷 = {PAYLOAD_BYTES} B；灵敏度按 125 kHz 手册表做热噪声缩放（工程近似）")
    print()
    print("表 A · SF × BW × CR（真值源：mcpserver/rf_workflow/lora_phy.py）")
    print(_fmt_table(link, LINK_COLUMNS))
    print()
    print("表 B · WuRX 唤醒占空比预算（唤醒窗 %.2f s；主接收 %.0f mW；唤醒接收 %.0f µW）"
          % (DEFAULT_POWER["wake_window_s"], DEFAULT_POWER["main_rx_mw"], DEFAULT_POWER["wake_receiver_uw"]))
    print(_fmt_table(budget, BUDGET_COLUMNS))
    print()
    viol = [r for r in budget if r["compliance"] == "VIOLATION"]
    print(f"占空比合规：{len(budget) - len(viol)}/{len(budget)} 通过；"
          f"VIOLATION {len(viol)} 个（唤醒周期 {', '.join(str(r['wake_period_s']) for r in viol) or '无'} s）")
    print("注：限值取 lora_phy.DUTY_CYCLE_LIMIT_PCT（ERC/REC 70-03 Annex 1，433.05–434.79 MHz）；"
          "部署前须按落地地区与天线型式复核。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
