#!/usr/bin/env python3
"""LoRaCanary v0.6 底板原理图程序化生成驱动（直焊版）。

经 easyeda-agent daemon 的 typed action 调用：
  1. lib search 解析器件 UUID（离线，不打开库浏览器）
  2. sch place 逐件放置并指定位号
  3. sch autoconnect 给每个引脚打 netflag/netport 并自动拉短桩线
  4. sch read 验证网表

网表来源：docs/SPEC-20-PCB前置资料-嘉立创AI.md（第三章完整网络清单）。

用法:
  python draw_schematic.py --current    # 画进当前工程/图页（推荐）
  python draw_schematic.py --dry-run  # 只打印计划，不执行
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time

EASYEDA = r"C:\Users\ASUS\bin\easyeda.exe"
PROJECT = "LoRaCanary-底板-v0.6"

# ─────────────────────────────────────────────────────────────────────────────
# 网络命名与类型：GND → 接地标志；电源轨 → 电源标志；其余 → 双向 netport
# ─────────────────────────────────────────────────────────────────────────────
GND_NET = "GND"
POWER_NETS = {"3V3", "5V", "VBUS", "BAT+"}

# ═════════════════════════════════════════════════════════════════════════════
# ⚠️  SuperMini 排母（2×17）参考引脚映射
# 依据 WeAct ESP32-S3 SuperMini 丝印整理；SPEC-20 明确要求「以实物丝印为准」。
# ═════════════════════════════════════════════════════════════════════════════
SUPERMINI_PINS = {
    "1": "3V3",
    "2": "EN",
    "3": "BOOT",
    "5": "LORA_DIO0",
    "7": "LORA_RST",
    "11": "SDA",
    "12": "SCL",
    "13": "LORA_NSS",
    "14": "LORA_MOSI",
    "15": "LORA_SCK",
    "16": "LORA_MISO",
    "33": "5V",
    "34": "GND",
}

# ─────────────────────────────────────────────────────────────────────────────
# 器件表：designator / sid / x,y / pins{引脚号: 网络}
# NC = 不连接。
# ─────────────────────────────────────────────────────────────────────────────
COMPONENTS = [
    dict(designator="J1", sid="C9900001620", x=800, y=1200, pins={
        "A4": "VBUS", "B4": "VBUS", "A9": "VBUS", "B9": "VBUS",
        "A1": "GND", "B1": "GND", "A12": "GND", "B12": "GND",
        "17": "GND", "18": "GND", "19": "GND", "20": "GND",
        "A5": "CC1", "B5": "CC2",
    }),
    dict(designator="D1", sid="C8678", x=1400, y=1200, pins={"2": "VBUS", "1": "5V"}),
    dict(designator="U4", sid="C6186", x=2000, y=1200, pins={"3": "VBUS", "2": "3V3", "4": "3V3", "1": "GND"}),
    dict(designator="U5", sid="C382139", x=2600, y=1200, pins={
        "4": "VBUS", "8": "VBUS", "5": "BAT+",
        "3": "GND", "9": "GND",
        "2": "PROG", "7": "CHRG", "6": "STDBY",
    }),
    dict(designator="B1", sid="C9900004923", x=3200, y=1200, pins={"1": "BAT+", "2": "GND"}),

    dict(designator="U1", sid="C9900022105", x=800, y=2400, pins=SUPERMINI_PINS),

    dict(designator="U2", sid="C90040", x=2000, y=2400, pins={
        "1": "ANT", "2": "GND", "3": "3V3",
        "4": "LORA_RST", "5": "LORA_DIO0",
        "12": "LORA_SCK", "13": "LORA_MISO", "14": "LORA_MOSI",
        "15": "LORA_NSS", "16": "GND",
    }),

    dict(designator="U3", sid="C92489", x=3200, y=2400, pins={
        "1": "GND", "2": "3V3", "3": "SDA", "4": "SCL",
        "5": "GND", "6": "3V3", "7": "GND", "8": "3V3",
    }),
    dict(designator="U6", sid="C9900209498", x=3800, y=2400, pins={
        "1": "GND", "2": "3V3", "3": "SCL", "4": "SDA",
    }),

    dict(designator="R1", sid="C17673", x=800, y=3600, pins={"1": "3V3", "2": "SDA"}),
    dict(designator="R2", sid="C17673", x=1400, y=3600, pins={"1": "3V3", "2": "SCL"}),
    dict(designator="R3", sid="C17379", x=2000, y=3600, pins={"1": "PROG", "2": "GND"}),
    dict(designator="R4", sid="C17513", x=2600, y=3600, pins={"1": "VBUS", "2": "LED_CHRG_A"}),
    dict(designator="R5", sid="C17513", x=3200, y=3600, pins={"1": "VBUS", "2": "LED_STDBY_A"}),
    dict(designator="R6", sid="C17630", x=3800, y=3600, pins={"1": "3V3", "2": "LED_PWR_A"}),
    dict(designator="R7", sid="C27834", x=800, y=4400, pins={"1": "CC1", "2": "GND"}),
    dict(designator="R8", sid="C27834", x=1400, y=4400, pins={"1": "CC2", "2": "GND"}),

    dict(designator="C1", sid="C3901446", x=2000, y=4400, pins={"1": "3V3", "2": "GND"}),
    dict(designator="C2", sid="C15850", x=2600, y=4400, pins={"1": "VBUS", "2": "GND"}),
    dict(designator="C3", sid="C15850", x=3200, y=4400, pins={"1": "3V3", "2": "GND"}),
    dict(designator="C4", sid="C3901446", x=3800, y=4400, pins={"1": "VBUS", "2": "GND"}),
    dict(designator="C5", sid="C3901446", x=800, y=5200, pins={"1": "3V3", "2": "GND"}),

    dict(designator="LED1", sid="C28105", x=1400, y=5200, pins={"2": "LED_PWR_A", "1": "GND"}),
    dict(designator="LED2", sid="C28105", x=2000, y=5200, pins={"2": "LED_CHRG_A", "1": "CHRG"}),
    dict(designator="LED3", sid="C28105", x=2600, y=5200, pins={"2": "LED_STDBY_A", "1": "STDBY"}),

    dict(designator="SW1", sid="C9900014294", x=3200, y=5200, pins={"1": "BOOT", "2": "GND"}),
    dict(designator="SW2", sid="C9900014294", x=3800, y=5200, pins={"1": "EN", "2": "GND"}),
]


# ─────────────────────────────────────────────────────────────────────────────
# daemon CLI 桥接
# ─────────────────────────────────────────────────────────────────────────────
def run_cli(args: list[str], timeout: int = 120) -> dict:
    out = subprocess.run([EASYEDA, *args], capture_output=True, text=True,
                         timeout=timeout, creationflags=0x08000000)
    txt = (out.stdout or "").strip()
    if txt.startswith("{"):
        try:
            return json.loads(txt)
        except json.JSONDecodeError:
            pass
    return {"raw": txt[:3000], "stderr": (out.stderr or "")[:500]}


def ok(resp: dict) -> dict:
    if resp.get("ok"):
        return resp.get("result", {})
    raise SystemExit(f"动作失败: {json.dumps(resp, ensure_ascii=False)[:800]}")


def resolve_devices() -> dict[str, dict]:
    """通过离线 `easyeda lib search` 解析器件库身份。"""
    devices: dict[str, dict] = {}
    seen = set()
    for comp in COMPONENTS:
        sid = comp["sid"]
        if sid in seen:
            continue
        seen.add(sid)
        resp = run_cli(["lib", "search", "--query", sid, "--limit", "1", "--project", PROJECT], timeout=60)
        if not resp.get("ok"):
            raise SystemExit(f"lib search 失败 [{sid}]: {json.dumps(resp, ensure_ascii=False)[:400]}")
        comps = resp.get("result", {}).get("components", [])
        if not comps:
            raise SystemExit(f"未找到器件 [{sid}]")
        devices[sid] = comps[0]
        print(f"  resolved {sid} -> {comps[0]['name']}", file=sys.stderr)
    return devices


def delete_primitives(ids: list[str]) -> None:
    if not ids:
        return
    run_cli(["sch", "prim-delete", "--ids", ",".join(ids), "--project", PROJECT], timeout=30)


def place_component(spec: dict, dev: dict) -> dict:
    """调用 sch place 放置一个器件；若设计器分配失败则删除重试一次。"""
    args = [
        "sch", "place",
        "--lib", dev["libraryUuid"],
        "--uuid", dev["uuid"],
        "--x", str(spec["x"]),
        "--y", str(spec["y"]),
        "--designator", spec["designator"],
        "--project", PROJECT,
    ]
    resp = run_cli(args, timeout=60)
    if resp.get("ok"):
        return resp["result"]["component"]
    err = json.dumps(resp, ensure_ascii=False)
    # 部分放置成功但位号未分配：删除该组件后重试
    import re
    m = re.search(r'Placed component "([^"]+)" but failed to assign designator', err)
    if m:
        bad_id = m.group(1)
        print(f"   place {spec['designator']} 位号分配失败，清理后重试...", file=sys.stderr)
        delete_primitives([bad_id])
        resp = run_cli(args, timeout=60)
        if resp.get("ok"):
            return resp["result"]["component"]
    raise SystemExit(f"放置 {spec['designator']} 失败: {err[:400]}")


def pin_kind(net: str) -> str:
    if net == GND_NET:
        return "gnd"
    if net in POWER_NETS:
        return "power"
    return "netport"


def autoconnect_component(spec: dict, tmp_path: str = "") -> dict:
    """调用 sch autoconnect 批量连接一个器件的所有引脚。"""
    import tempfile
    connections = []
    for pin, net in spec["pins"].items():
        if net == "NC":
            continue
        connections.append({
            "pin": f"{spec['designator']}:{pin}*",
            "kind": pin_kind(net),
            "net": net,
        })
    spec_file = tmp_path or tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, encoding="utf-8").name
    with open(spec_file, "w", encoding="utf-8") as f:
        json.dump({"connections": connections}, f, ensure_ascii=False)
    for attempt in range(3):
        resp = run_cli([
            "sch", "autoconnect",
            "--spec", spec_file,
            "--project", PROJECT,
            "--json",
        ], timeout=60)
        if resp.get("ok"):
            return resp.get("result", {})
        err = json.dumps(resp, ensure_ascii=False)
        if "connector did not respond" in err and attempt < 2:
            print(f"   autoconnect {spec['designator']} transient, retry after 3s...", file=sys.stderr)
            time.sleep(3)
            continue
        raise SystemExit(f"autoconnect {spec['designator']} 失败: {err[:400]}")


def clear_page() -> dict:
    return ok(run_cli([
        "debug", "exec", "--project", PROJECT,
        "--timeout", "20",
        "--code",
        "const c = await eda.sch_PrimitiveComponent.getAllPrimitiveId(); "
        "const w = await eda.sch_PrimitiveWire.getAllPrimitiveId(); "
        "const a = await eda.sch_PrimitiveAttribute.getAllPrimitiveId(); "
        "if (c.length) await eda.sch_PrimitiveComponent.delete(c); "
        "if (w.length) await eda.sch_PrimitiveWire.delete(w); "
        "if (a.length) await eda.sch_PrimitiveAttribute.delete(a); "
        "return { comps: c.length, wires: w.length, attrs: a.length };",
    ], timeout=30))


def list_components() -> tuple[set[str], list[dict]]:
    """读取当前图页上的器件集合：返回（位号集合, 未命名器件列表）。"""
    for attempt in range(3):
        resp = run_cli(["sch", "list", "--project", PROJECT], timeout=30)
        if resp.get("ok"):
            comps = resp.get("result", {}).get("components", [])
            designators = set()
            unnamed = []
            for c in comps:
                d = c.get("designator", "") or ""
                if d:
                    designators.add(d)
                else:
                    unnamed.append(c)
            return designators, unnamed
        if attempt < 2:
            time.sleep(3)
    raise SystemExit("无法读取当前图页器件列表")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--current", action="store_true", help="画进当前工程/图页（不新建工程）")
    ap.add_argument("--dry-run", action="store_true", help="只打印计划，不执行")
    ap.add_argument("--no-clear", action="store_true", help="不清空图页（用于断点续画）")
    a = ap.parse_args()

    print("1/4 解析器件库身份...", file=sys.stderr)
    devices = resolve_devices()

    if a.dry_run:
        print(f"将放置 {len(COMPONENTS)} 个器件，已解析 {len(devices)} 种型号", file=sys.stderr)
        return 0

    if not a.no_clear:
        print("2/4 清页...", file=sys.stderr)
        cleared = clear_page()
        print(f"   已清: {cleared}", file=sys.stderr)

    print("3/4 放置器件并连接网络...", file=sys.stderr)
    existing, _ = list_components()
    print(f"   当前图页已有: {sorted(existing)}", file=sys.stderr)

    for idx, spec in enumerate(COMPONENTS):
        if spec["designator"] in existing:
            print(f"   skip place {spec['designator']} (already on page)", file=sys.stderr)
        else:
            dev = devices[spec["sid"]]
            place_component(spec, dev)
            print(f"   placed {spec['designator']} at ({spec['x']},{spec['y']})", file=sys.stderr)
        autoconnect_component(spec)
        print(f"   wired {spec['designator']}", file=sys.stderr)
        if idx < len(COMPONENTS) - 1:
            time.sleep(2.0)  # 降低连接器负载

    print("4/4 验证...", file=sys.stderr)
    summary = ok(run_cli(["sch", "read", "--project", PROJECT], timeout=60))
    print(json.dumps({
        "components_placed": len(COMPONENTS),
        "verification": summary,
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
