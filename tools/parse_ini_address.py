#!/usr/bin/env python
"""
Parse all RS-BA1 V2 INI config files and generate a complete radio model
address table in markdown format.

Output: d:\\my git\\scratchpad\\tools\\pe_analysis_output\\ini_address_table.md
"""

import glob
import os
import re
from collections import OrderedDict

MODELS_DIR = r"d:\my git\RS-BA1\RemoteController\models"
MODELS_INI = r"d:\my git\RemoteUtility\models.ini"
RADIOSCH_INI = r"d:\my git\RemoteUtility\RadioSch.ini"
OUTPUT_MD = r"d:\my git\scratchpad\tools\pe_analysis_output\ini_address_table.md"

# BAUD code -> baud rate mapping (Icom CI-V standard baud rate code table).
# In radio INIs BAUD is a comma list of supported codes; in models.ini it is
# the real default rate. Verified against models.ini defaults:
#   IC-705 code=7 -> 115200; IC-7300 codes 2..7 default 115200;
#   old radios codes 0..4 default 19200 (code 4).
BAUD_CODE_MAP = {
    0: 300,
    1: 1200,
    2: 4800,
    3: 9600,
    4: 19200,
    5: 38400,
    6: 57600,
    7: 115200,
}

# CI-V mode code -> mode name (Icom CI-V mode sub-command 0x04)
MODE_NAMES = {
    0: "LSB",
    1: "USB",
    2: "AM",
    3: "CW",
    4: "RTTY",
    5: "FM",
    6: "WFM",
    7: "CW-R",
    8: "RTTY-R",
    12: "PSK",
    13: "PSK-R",
    17: "DD",
}

TYPE_NAMES = {0: "Single", 1: "Dual", 2: "Split"}


def parse_ini(path):
    """Parse an INI file that uses TAB as the key/value delimiter.

    Returns an OrderedDict: section -> {key: value}.
    """
    sections = OrderedDict()
    current = None
    with open(path, encoding="cp932", errors="replace") as f:
        for raw in f:
            line = raw.rstrip("\r\n")
            if not line.strip():
                continue
            if line.lstrip().startswith(";"):
                continue
            stripped = line.strip()
            if stripped.startswith("[") and stripped.endswith("]"):
                current = stripped[1:-1].strip()
                sections[current] = OrderedDict()
                continue
            if current is None:
                continue
            # split on first '=' (handles both "KEY=VAL" and "KEY\t= VAL")
            if "=" in line:
                key, val = line.split("=", 1)
            elif "\t" in line:
                key, val = line.split("\t", 1)
            else:
                continue
            key = key.strip()
            val = val.strip()
            if key:
                sections[current][key] = val
    return sections


def fmt_freq(hz):
    """Format a frequency in Hz to a human readable string."""
    try:
        hz = int(hz)
    except (TypeError, ValueError):
        return str(hz)
    if hz >= 1_000_000:
        return f"{hz/1_000_000:.4g} MHz"
    if hz >= 1_000:
        return f"{hz/1_000:.4g} kHz"
    return f"{hz} Hz"


def parse_baud(val):
    """Return list of baud rates for a BAUD field value."""
    if not val:
        return []
    parts = [p.strip() for p in val.split(",") if p.strip()]
    out = []
    for p in parts:
        try:
            code = int(p)
            out.append(BAUD_CODE_MAP.get(code, code))
        except ValueError:
            try:
                out.append(int(p))
            except ValueError:
                out.append(p)
    return out


def collect_ranges(section, prefix="RANGE"):
    """Collect non-empty RANGE<n> = lo, hi entries in order."""
    out = []
    if not section:
        return out
    i = 0
    while True:
        key = f"{prefix}{i}"
        if key not in section:
            break
        val = section[key]
        if val and val.strip():
            parts = [p.strip() for p in val.split(",") if p.strip()]
            out.append(parts)
        i += 1
    return out


def summarize_radio_ini(path):
    d = parse_ini(path)
    desc = d.get("DESCRIPTION", {})
    com = d.get("COM", {})
    typ = d.get("TYPE", {})
    setting = d.get("SETTING", {})
    freq = d.get("FREQUENCY", {})
    bandgrp = d.get("BAND GROUP", {})
    txband = d.get("TX BAND", {})
    antband = d.get("ANT BAND", {})
    scope = d.get("SCOPE", {})
    transpwr = d.get("TRANSPWR", {})
    support = d.get("SUPPORT", {})
    ui = d.get("UI", {})

    adr = com.get("ADR", "")
    baud_raw = com.get("BAUD", "")
    bauds = parse_baud(baud_raw)
    type_code = int(typ.get("TYPE", "0") or "0")
    dual = int(typ.get("DUAL", "0") or "0")
    dual_kind = int(typ.get("DUAL_KIND", "0") or "0")

    # modes
    modes_raw = setting.get("MODE", "")
    mode_names = []
    if modes_raw:
        for m in modes_raw.split(","):
            m = m.strip()
            if not m:
                continue
            try:
                code = int(m)
                mode_names.append(f"{code}={MODE_NAMES.get(code, '?')}")
            except ValueError:
                mode_names.append(m)

    # frequency ranges
    freq_ranges = collect_ranges(freq)
    band_ranges = collect_ranges(bandgrp)
    tx_ranges = collect_ranges(txband)

    return {
        "path": path,
        "name": desc.get("MODEL", os.path.basename(path).replace(".ini", "")),
        "adr": adr,
        "baud_raw": baud_raw,
        "bauds": bauds,
        "type_code": type_code,
        "type_name": TYPE_NAMES.get(type_code, str(type_code)),
        "dual": dual,
        "dual_kind": dual_kind,
        "ver17": support.get("VER17", ""),
        "modes_raw": modes_raw,
        "mode_names": mode_names,
        "pre": setting.get("PRE", ""),
        "ant": setting.get("ANT", ""),
        "att": setting.get("ATT", ""),
        "fil": setting.get("FIL", ""),
        "tone": setting.get("TONE", ""),
        "dsql": setting.get("DSQL", ""),
        "rise_time": setting.get("RISE_TIME", ""),
        "freq_ranges": freq_ranges,
        "band_ranges": band_ranges,
        "tx_ranges": tx_ranges,
        "scope_type": scope.get("TYPE", ""),
        "scope_connect": scope.get("CONNECT", ""),
        "transpwr_ctrl": transpwr.get("CONTROL", ""),
        "transpwr_cmd_on": transpwr.get("CMD_ON", ""),
        "transpwr_cmd_off": transpwr.get("CMD_OFF", ""),
        "bsr": {k: v for k, v in ui.items()},
        "full": d,
    }


def main():
    # ---- radio model INIs ----
    radio_files = sorted(glob.glob(os.path.join(MODELS_DIR, "IC-*.ini")))
    radios = [summarize_radio_ini(p) for p in radio_files]

    # ---- models.ini (RemoteUtility) ----
    models_ini = parse_ini(MODELS_INI)
    data_sec = models_ini.get("DATA", {})
    cnt = data_sec.get("CNT", "?")
    models_map = OrderedDict()
    i = 1
    while f"MODEL{i}" in models_ini:
        m = models_ini[f"MODEL{i}"]
        models_map[m.get("NAME", f"MODEL{i}")] = {
            "adr": m.get("ADR", ""),
            "baud": m.get("BAUD", ""),
            "type": m.get("TYPE", ""),
        }
        i += 1

    # ---- RadioSch.ini ----
    radiosch = parse_ini(RADIOSCH_INI)

    # ---- Build markdown ----
    lines = []
    L = lines.append

    L("# RS-BA1 V2 INI 配置文件完整电台型号地址表")
    L("")
    L("> 本文档由解析 RS-BA1 V2 全部 INI 配置文件自动生成。")
    L(f"> INI 目录: `{MODELS_DIR}`")
    L(f"> RemoteUtility: `{MODELS_INI}` / `{RADIOSCH_INI}`")
    L("")
    L("## 目录")
    L("")
    L("1. [RemoteUtility models.ini 型号映射总表](#1-remoteutility-modelsini-型号映射总表)")
    L("2. [RemoteController 电台型号 INI 地址表](#2-remotecontroller-电台型号-ini-地址表)")
    L("3. [general_single / general_dual / general_split 区别说明](#3-generalsingle--generaldual--generalsplit-区别说明)")
    L("4. [RadioSch.ini 调度配置说明](#4-radioschini-调度配置说明)")
    L("5. [各电台频率范围 / 发射频段明细](#5-各电台频率范围--发射频段明细)")
    L("6. [CI-V 模式代码表](#6-ci-v-模式代码表)")
    L("7. [波特率代码映射表](#7-波特率代码映射表)")
    L("8. [IC-705.ini 特别说明](#8-ic-705ini-特别说明)")
    L("")
    L("---")
    L("")

    # ---- Section 1: models.ini ----
    L("## 1. RemoteUtility models.ini 型号映射总表")
    L("")
    L(f"`models.ini` 是 RemoteUtility (RemoteUty.exe) 维护的型号映射总表，共 **{cnt}** 条记录。")
    L("该表是 RS-BA1 在 USB/LAN 连接设置里识别电台型号的权威来源。`TYPE=0` 为收发信机，`TYPE=1` 为接收机。")
    L("")
    L("| # | 型号 | CI-V 地址 (HEX) | 波特率 | TYPE | 备注 |")
    L("|---|------|----------------|--------|------|------|")
    type_note = {0: "收发信机", 1: "接收机"}
    for idx, (name, m) in enumerate(models_map.items(), 1):
        L(f"| {idx} | {name} | 0x{m['adr']} | {m['baud']} | {m['type']} | {type_note.get(int(m['type']), '')} |")
    L("")
    L("**说明：**")
    L("- `IC-746PRO` 与 `IC-7400` 共用 CI-V 地址 `0x66`（746PRO 是 7400 的海外/前代型号）。")
    L("- `IC-7851` 与 `IC-7850` 共用 CI-V 地址 `0x8E`（7851 是 7850 的美规/升级型号）。")
    L("- `IC-R8600` 为 `TYPE=1` 接收机，在 RemoteController/models 目录下没有专用 INI，由 `general_*.ini` 兜底。")
    L("- `IC-705`、`IC-7300`、`IC-7610`、`IC-7850/7851`、`IC-9700`、`IC-R8600` 均使用 **115200** 波特率；")
    L("  其余型号使用 19200 波特率。")
    L("")
    L("---")
    L("")

    # ---- Section 2: radio model INIs ----
    L("## 2. RemoteController 电台型号 INI 地址表")
    L("")
    L("下表汇总 `RemoteController/models/` 目录下所有 `IC-*.ini` 的 `[COM]`/`[TYPE]`/`[FREQUENCY]`/`[SETTING]` 关键字段。")
    L("")
    L("| INI 文件 | 型号 | CI-V 地址 | 波特率(代码) | TYPE | 频率范围 (Hz) | 模式列表 |")
    L("|----------|------|-----------|-------------|------|---------------|----------|")
    for r in radios:
        fname = os.path.basename(r["path"])
        adr = f"0x{r['adr']}" if r["adr"] else "—"
        bauds_str = f"{r['baud_raw']} ({', '.join(str(b) for b in r['bauds'])})" if r["bauds"] else r["baud_raw"]
        freq_str = "; ".join(
            f"{lo}–{hi}" for rng in r["freq_ranges"] for lo, hi in [rng[:2]]
        ) if r["freq_ranges"] else "—"
        modes_str = ", ".join(r["mode_names"]) if r["mode_names"] else "—"
        L(f"| {fname} | {r['name']} | {adr} | {bauds_str} | {r['type_code']}={r['type_name']} | {freq_str} | {modes_str} |")
    L("")
    L("> `IC-7610_d.ini` / `IC-7850_d.ini` 是 Dual VFO 变体（`TYPE=1`），分别对应 IC-7610 / IC-7850 的双接收模式。")
    L("")
    L("---")
    L("")

    # ---- Section 3: general INIs ----
    L("## 3. general_single / general_dual / general_split 区别说明")
    L("")
    L("`general_*.ini` 是 RS-BA1 的通用兜底定义文件，用于未被专用 INI 覆盖的 Icom 电台（含 IC-R8600）。")
    L("三者的核心区别在 `[TYPE] TYPE` 字段以及由此启用的 VFO/收发命令集合：")
    L("")
    L("| 文件 | TYPE | 含义 | CIV2(Split) | Exe_Vfoa/Vfob | Exe_Abeq/Ab/Mseq | Exe_Dualoff/On | INITIAL CMD2 |")
    L("|------|------|------|-------------|---------------|------------------|----------------|--------------|")
    gen_files = ["general_single.ini", "general_dual.ini", "general_split.ini"]
    for gf in gen_files:
        gp = os.path.join(MODELS_DIR, gf)
        gd = parse_ini(gp)
        typ = gd.get("TYPE", {})
        cmd = gd.get("COMMAND", {})
        ini = gd.get("INITIAL", {})
        L(f"| {gf} | {typ.get('TYPE','')} | {TYPE_NAMES.get(int(typ.get('TYPE','0')),'')} | {cmd.get('CIV2','')} | "
          f"{cmd.get('CIV211','')}/{cmd.get('CIV212','')} | "
          f"{cmd.get('CIV213','')}/{cmd.get('CIV214','')}/{cmd.get('CIV215','')} | "
          f"{cmd.get('CIV217','')}/{cmd.get('CIV218','')} | {ini.get('CMD2','')} |")
    L("")
    L("**详细差异：**")
    L("")
    L("- **general_single.ini (`TYPE=0`, Single)**")
    L("  - 单 VFO 模式，最简命令集。`CIV2(Split)=0`、`Exe_Vfoa/Vfob=0`、`Exe_Abeq/Ab/Mseq=0`。")
    L("  - `[INITIAL] CMD2 = 164600`（仅设置 VFO），不发送双 watch / Satellite 命令。")
    L("  - 适用于：单接收老型号电台、IC-R8600 等接收机。")
    L("")
    L("- **general_dual.ini (`TYPE=1`, Dual)**")
    L("  - 双 VFO / 双接收模式。`CIV2(Split)=1`、`Exe_Vfoa/Vfob=1`、`Exe_Abeq/Ab/Mseq=1`。")
    L("  - 显式带双 watch 切换命令：`Exe_Dualoff CMD217=07C0`、`Exe_Dualon CMD218=07C1`、")
    L("    `Exe_Macc CMD220=07D0`、`Exe_Sacc CMD221=07D1`、`Exe_Acc CMD219=07D2`。")
    L("  - `[INITIAL] CMD2 = 07C0`（开机即关闭双 watch，避免冲突）。")
    L("  - 适用于：IC-7610_d / IC-7850_d 等双接收变体。")
    L("")
    L("- **general_split.ini (`TYPE=2`, Split)**")
    L("  - 异频 (Split) 模式。`CIV2(Split)=1`、`Exe_Vfoa/Vfob=1`、`Exe_Abeq/Ab=1`。")
    L("  - **不**带双 watch 命令（`Exe_Mseq=0`、`Exe_Dualoff/On=0`、`Exe_Acc/Macc/Sacc=0`）。")
    L("  - `[INITIAL] CMD2 = 164600`（仅设 VFO，不强制双 watch 状态）。")
    L("  - 适用于：仅做收发异频、不需要双接收的电台。")
    L("")
    L("**三者共同的兜底字段：** `ADR` 为空（运行时由 models.ini 注入），`BAUD=0,1,2,3,4`（允许 300/1200/4800/9600/19200 老式五档全可选），")
    L("`MODE = 0,1,2,3,4,5,7,8,12,13,17`（覆盖 LSB/USB/AM/CW/RTTY/FM/CW-R/RTTY-R/PSK/PSK-R/DD），")
    L("`FREQUENCY RANGE0 = 5000 – 3335000000`（极宽兜底范围），`[TX BAND]` 全部为空（发射能力由具体电台决定）。")
    L("")
    L("---")
    L("")

    # ---- Section 4: RadioSch.ini ----
    L("## 4. RadioSch.ini 调度配置说明")
    L("")
    L("`RadioSch.ini` 是 RemoteUtility 用来识别 Icom 原厂 USB 驱动线缆（HUB/Audio/COM 三合一）的 VID/PID 调度表。")
    L("`[MAIN] CNT=4` 表示定义了 4 组线缆 VID/PID 组合。匹配到任一组即自动加载虚拟声卡 + 虚拟串口驱动。")
    L("")
    L("`RadioSch.dll` 在运行时读取此 INI，枚举系统 USB 设备，按 HUB→AUDIO→COM 三级 VID/PID 比对识别线缆型号。")
    L("")
    L("| 组号 | HUB (VID/PID) | AUDIO (VID/PID) | COM (VID/PID) | 备注 |")
    L("|------|---------------|-----------------|---------------|------|")
    main = radiosch.get("MAIN", {})
    cnt_sch = int(main.get("CNT", "0"))
    for i in range(1, cnt_sch + 1):
        sec = radiosch.get(f"VIDPID{i}", {})
        hub = sec.get("HUB", "")
        audio = sec.get("AUDIO", "")
        com = sec.get("COM", "")
        extra = sec.get("ID", "")
        note = f"ID={extra}" if extra else ""
        L(f"| VIDPID{i} | {hub} | {audio} | {com} | {note} |")
    L("")
    L("**VID/PID 厂商解读：**")
    L("- `VID_0424` = Microchip (原 SMSC) USB Hub 控制器；`VID_0451` = Texas Instruments USB Hub。")
    L("- `VID_08BB` = Texas Instruments PCM2901 USB Audio CODEC（线缆内的 USB 声卡）。")
    L("- `VID_10C4` = Silicon Labs CP210x USB-to-UART（线缆内的 USB 转串口）；")
    L("  `VID_0C26` = ICOM 自家 OEM 串口芯片（仅 VIDPID4，带 `ID=A` 标记，可能是特殊固件版本）。")
    L("")
    L("---")
    L("")

    # ---- Section 5: per-radio freq/tx ranges ----
    L("## 5. 各电台频率范围 / 发射频段明细")
    L("")
    L("以下逐型号列出 `[FREQUENCY]`（接收范围）、`[TX BAND]`（发射范围，单位 Hz）及关键 `[SETTING]` 字段。")
    L("")
    for r in radios:
        L(f"### {r['name']}  (`{os.path.basename(r['path'])}`)")
        L("")
        L(f"- **CI-V 地址:** `0x{r['adr']}`" if r["adr"] else "- **CI-V 地址:** —")
        bauds_str = ", ".join(str(b) for b in r["bauds"]) if r["bauds"] else r["baud_raw"]
        L(f"- **波特率:** {r['baud_raw']} → {bauds_str}")
        L(f"- **TYPE:** {r['type_code']} = {r['type_name']}; DUAL={r['dual']}; DUAL_KIND={r['dual_kind']}; VER17={r['ver17']}")
        L(f"- **模式 (MODE):** {', '.join(r['mode_names']) if r['mode_names'] else '—'}")
        L(f"- **PRE:** {r['pre']} | **ANT:** {r['ant']} | **ATT:** {r['att']} | **FIL:** {r['fil']} | **TONE:** {r['tone']} | **DSQL:** {r['dsql']} | **RISE_TIME:** {r['rise_time']}")
        # frequency ranges
        if r["freq_ranges"]:
            L("- **[FREQUENCY] 接收范围:**")
            for rng in r["freq_ranges"]:
                if len(rng) >= 2:
                    L(f"  - RANGE: {rng[0]} Hz ({fmt_freq(rng[0])}) – {rng[1]} Hz ({fmt_freq(rng[1])})")
                else:
                    L(f"  - RANGE: {rng}")
        else:
            L("- **[FREQUENCY] 接收范围:** —")
        # tx band ranges
        if r["tx_ranges"]:
            L("- **[TX BAND] 发射范围:**")
            for rng in r["tx_ranges"]:
                if len(rng) >= 2:
                    L(f"  - RANGE: {rng[0]} Hz ({fmt_freq(rng[0])}) – {rng[1]} Hz ({fmt_freq(rng[1])})")
                else:
                    L(f"  - RANGE: {rng}")
        else:
            L("- **[TX BAND] 发射范围:** — （general 兜底或接收机无发射）")
        # scope / transpwr
        scope_bits = []
        if r["scope_type"]:
            scope_bits.append(f"TYPE={r['scope_type']}")
        if r["scope_connect"]:
            scope_bits.append(f"CONNECT={r['scope_connect']}")
        if scope_bits:
            L(f"- **[SCOPE]:** {', '.join(scope_bits)}")
        tp = []
        if r["transpwr_ctrl"]:
            tp.append(f"CONTROL={r['transpwr_ctrl']}")
        if r["transpwr_cmd_on"]:
            tp.append(f"CMD_ON={r['transpwr_cmd_on']}")
        if r["transpwr_cmd_off"]:
            tp.append(f"CMD_OFF={r['transpwr_cmd_off']}")
        if tp:
            L(f"- **[TRANSPWR]:** {', '.join(tp)}")
        # BSR
        if r["bsr"]:
            bsr_str = ", ".join(f"{k}={v}" for k, v in r["bsr"].items())
            L(f"- **[UI] BSR:** {bsr_str}")
        L("")

    L("---")
    L("")

    # ---- Section 6: mode codes ----
    L("## 6. CI-V 模式代码表")
    L("")
    L("`[SETTING] MODE` 字段使用 CI-V 模式代码（对应 Icom CI-V 命令 `0x06` 子命令）：")
    L("")
    L("| 代码 | 模式 | 代码 | 模式 |")
    L("|------|------|------|------|")
    items = list(MODE_NAMES.items())
    half = (len(items) + 1) // 2
    for i in range(half):
        left = items[i]
        right = items[i + half] if i + half < len(items) else (None, None)
        L(f"| {left[0]} | {left[1]} | {right[0] if right[0] is not None else ''} | {right[1] if right[1] is not None else ''} |")
    L("")
    L("---")
    L("")

    # ---- Section 7: baud code map ----
    L("## 7. 波特率代码映射表")
    L("")
    L("`[COM] BAUD` 字段在电台 INI 里是代码（可多选，逗号分隔）；在 `models.ini` 里直接是数值波特率。")
    L("")
    L("| 代码 | 波特率 (bps) | 说明 |")
    L("|------|-------------|------|")
    for code, rate in sorted(BAUD_CODE_MAP.items()):
        note = ""
        if code == 0:
            note = "低速（老型号）"
        elif code == 4:
            note = "老型号默认（19200）"
        elif code == 7:
            note = "新型号默认（115200）；IC-705 仅支持此档"
        L(f"| {code} | {rate} | {note} |")
    L("")
    L("> 注意：`general_*.ini` 的 `BAUD=0,1,2,3,4` 表示老式 5 档（300–19200）全可选；")
    L("> 新型号（IC-7300/7610/9700/7850）的 `BAUD=2,3,4,5,6,7` 表示 4800–115200 全可选；")
    L("> IC-705 的 `BAUD=7` 表示仅 115200 一档。`models.ini` 中给出的是各型号的默认波特率。")
    L("")
    L("---")
    L("")

    # ---- Section 8: IC-705 special ----
    L("## 8. IC-705.ini 特别说明")
    L("")
    ic705 = next((r for r in radios if r["name"] == "IC-705"), None)
    if ic705:
        L(f"- **CI-V 地址:** `0x{ic705['adr']}` （0xA4，与 models.ini 一致，IC-705 专用）")
        L(f"- **波特率:** 代码 `{ic705['baud_raw']}` → 115200 bps（与 models.ini 的 `BAUD=115200` 一致）")
        L(f"- **TYPE:** {ic705['type_code']} = {ic705['type_name']}（Split 模式，IC-705 原生支持异频）")
        L(f"- **VER17:** {ic705['ver17']} （V1.7 新增型号标记，启用 WLAN/USB 直连与 SD 记录等扩展命令）")
        L(f"- **模式列表:** {', '.join(ic705['mode_names'])}")
        L("- **连接方式:** `[CONNECT] CON0=1,0,3,USB` / `CON1=3,0,2,WLAN` —— 同时支持 USB 与 WLAN 两种直连。")
        L("- **接收频率范围:** 30 kHz – 470 MHz（HF/VHF/UHF 全段，分两段：0.03–199.999999 MHz + 400–470 MHz）。")
        L("- **发射频段:** 5 段 —— HF(30k–30M)、50M、60M(仅美规 6–7.48M)、VHF(74.8M–200M)、UHF(400–470M)。")
        L("- **发射功率:** DC 13.8V: 0.5/1/2.5/5/10 W；电池: 0.5/1/2.5/5 W。")
        L("- **特色扩展命令（非通用 INI 没有的）:**")
        L("  - `CMD70=1A0B` (MaxTxPower)、`CMD71=1A050036` (Battery)、`CMD72=1A050037` (DC)")
        L("  - `CMD29=1A04` (AGC)、`CMD33=1A050359` (Vox dly)、`CMD34=1A050360` (Vox vc dly)")
        L("  - `CMD47=1658` (SSB TX BW)、`CMD51=1A03` (FilW)、`CMD53=1656` (Slope)、`CMD57=1657` (MnotchW)")
        L("  - `CMD120=1A050110`/`CMD121=1A050111` (USB AF/SQL)、`CMD123=1A050115` (WLAN SQL)")
        L("  - `CMD124=1A050252` (CW ratio)、`CMD125=1A050253` (CW rise time)、`CMD126=1A050070` (CW rev)")
        L("  - 完整 Scope 频谱命令集（CIV182–CIV197），含 17 段 SCOPE RANGE 覆盖 HF/VHF/UHF。")
        L("- **[SCOPE] TYPE=1, GRID=8, EDGE=3**, span 8 档（2.5k–500k）；**[TRANSPWR] CONTROL=1** 支持外置功放控制 (CMD_ON=1801/CMD_OFF=1800)。")
        L("")
    L("---")
    L("")

    # ---- footer ----
    L("## 附录：INI 文件结构总览")
    L("")
    L("每个电台 INI 由以下 section 组成（general_*.ini 与专用 INI 结构一致）：")
    L("")
    L("| Section | 用途 |")
    L("|---------|------|")
    L("| `[DESCRIPTION]` | 文件描述与型号名 (`MODEL`) |")
    L("| `[SUPPORT]` | 版本支持标记 (`VER17`=1 表示 V1.7 新增型号) |")
    L("| `[TYPE]` | 电台类型 (`TYPE`: 0=Single 1=Dual 2=Split; `DUAL`/`DUAL_KIND`) |")
    L("| `[COM]` | CI-V 通信参数 (`ADR` 地址, `BAUD` 波特率代码) |")
    L("| `[CONNECT]` | 连接方式表 (`CON0..CON5`: 串口/USB/LAN/WLAN; `INITIAL` 自动连接标志) |")
    L("| `[COMMAND]` | CI-V 命令使能位 + 命令码 (`CIV0..CIV222`/`CMD0..CMD222`) |")
    L("| `[INITIAL]` | 开机初始化命令序列 (`CMD0..CMD19`) |")
    L("| `[UI]` | UI 显示开关 (`BSRHF50/144/430/1200` 频段扫描按钮) |")
    L("| `[SETTING]` | 可设选项枚举 (`MODE/PRE/ANT/ATT/FIL/TONE/DSQL/RISE_TIME`) |")
    L("| `[METER]` | 表头刻度 (S/PO/ALC/SWR/COMP/RFG/PO_TYPE/SWR_TYPE) |")
    L("| `[SQLVR]` | SQL 电压-代码映射 (CI-V↔VR) |")
    L("| `[BAND GROUP]` | 频段分组总范围 |")
    L("| `[FREQUENCY]` | 接收频率范围 (多 RANGE) |")
    L("| `[ANT BAND]` | 天线频段切换点 |")
    L("| `[TX BAND]` | 发射频段范围 (多 RANGE) |")
    L("| `[DUP OFFSET]` | 差频最大值 (`MAX`) |")
    L("| `[NB]` | 噪声抑制频段 (`BAND`) |")
    L("| `[FILTER]` | FM/AM/SLOPE 滤波器参数 |")
    L("| `[BW]` | 各模式带宽范围 (SSB/CW/PSK/RTTY/AM) |")
    L("| `[PBT]` | 通带调谐参数 |")
    L("| `[MOD_OFF]`/`[MOD]` | 调制源选择 (MIC/ACC/USB/WLAN) |")
    L("| `[RX IO]` | 接收 IO 选项 |")
    L("| `[AGC]` | AGC 速度选项 (FAST/MID/SLOW) |")
    L("| `[ROOF]` | Roofing filter 选项 |")
    L("| `[TBW]` | TX 带宽 (LOW/HIGH cutoff) |")
    L("| `[CW]` | CW 速度类型 |")
    L("| `[VR]` | 各功能 VR 类型 (APF/NRL/PBT/CWP/COMP/BKIND/AGC/DSEL) |")
    L("| `[VALID_RANGE]` | Roofing filter 有效范围 |")
    L("| `[DSEL_RANGE]` | D-SEL 范围 |")
    L("| `[TX_POWER]` | 发射功率档位 (`DISP/MAX/POWER0/POWER1`) |")
    L("| `[TRANSPWR]` | 外置功放控制 (`CONTROL/CONNECT/CMD_ON/CMD_OFF/ADDPREAMBLE/WAIT_OFF`) |")
    L("| `[SCOPE]` | 频谱功能参数 (`CONNECT/TYPE/GRID/SPAN/EDGE/RANGE0..19/REFLV/WAVELV`) |")
    L("| `[CONNECTOR]` | ACC/USB 连接器配置 (`ACCUSB`) |")
    L("")
    L("> 文档生成自实际 INI 文件解析，非官方手册；CI-V 地址/波特率以 `models.ini` 为权威，")
    L("> 频率/模式/命令以各 `RemoteController/models/IC-*.ini` 为权威。")
    L("")

    os.makedirs(os.path.dirname(OUTPUT_MD), exist_ok=True)
    with open(OUTPUT_MD, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    print(f"[OK] wrote {OUTPUT_MD}")
    print(f"[OK] parsed {len(radios)} radio INIs, {len(models_map)} models.ini entries, {cnt_sch} RadioSch VIDPID groups")
    # quick sanity: list name->adr
    for r in radios:
        print(f"  {r['name']:14s} ADR=0x{r['adr']:>2s} BAUD={r['baud_raw']} TYPE={r['type_code']}")


if __name__ == "__main__":
    main()
