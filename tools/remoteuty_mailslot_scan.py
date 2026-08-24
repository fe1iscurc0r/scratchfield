#!/usr/bin/env python
"""
RemoteUty.exe Mailslot server-side scan (step 1: quick recon).
- Locate all mailslot-related string occurrences (Cmd/Res/Civ/Hid + mutex names).
- Find IAT call sites for CreateMailslotA / GetMailslotInfo / ReadFile / WriteFile / CreateFileA / WaitForSingleObject / CreateMutexA / ReleaseMutex / CloseHandle.
- Find code xrefs to mailslot name strings.
- Dump short context (20 before / 20 after) around CreateMailslotA and GetMailslotInfo call sites and mailslot-string xrefs.
"""

import json
import sys
from pathlib import Path

import pefile
from capstone import CS_ARCH_X86, CS_MODE_32, Cs

EXE = r"d:\my git\RemoteUtility\RemoteUty.exe"
OUT_JSON = r"d:\my git\scratchpad\tools\pe_analysis_output\RemoteUty_mailslot_scan.json"

TARGET_API_SUBSTR = (
    "CreateMailslotA", "GetMailslotInfo",
    "ReadFile", "WriteFile", "CreateFileA",
    "WaitForSingleObject", "CreateMutexA", "ReleaseMutex", "CloseHandle",
)

EXACT_STRINGS = {
    "mailslot_cmd_ut":  b"\\\\.\\mailslot\\RemoteUtyCtrlCmd\x00",
    "mailslot_res_ut":  b"\\\\.\\mailslot\\RemoteUtyCtrlRes\x00",
    "mailslot_cmd_civ": b"\\\\.\\mailslot\\RemoteCivCtrlCmd\x00",
    "mailslot_res_civ": b"\\\\.\\mailslot\\RemoteCivCtrlRes\x00",
    "mailslot_cmd_hid": b"\\\\.\\mailslot\\RemoteHidCtrlCmd\x00",
    "mailslot_res_hid": b"\\\\.\\mailslot\\RemoteHidCtrlRes\x00",
    "mutex_ut":         b"Icom RemoteUtyCtrl\x00",
    "mutex_civ":        b"Icom RemoteCivCtrl\x00",
    "mutex_hid":        b"Icom RemoteHidCtrl\x00",
}

PREFIX_STRINGS = {
    "mailslot_prefix": b"\\\\.\\mailslot\\",
    "mutex_prefix":    b"Icom Remote",
}


def load_pe():
    return pefile.PE(EXE, fast_load=False)


def build_iat_map(pe):
    iat = {}
    for entry in pe.DIRECTORY_ENTRY_IMPORT:
        dll = entry.dll.decode("ascii", errors="replace")
        for imp in entry.imports:
            if imp.address is None:
                continue
            name = imp.name.decode("ascii", errors="replace") if imp.name else f"ord{imp.ordinal}"
            iat[imp.address] = f"{dll}!{name}"
    return iat


def get_text_section(pe):
    for sec in pe.sections:
        if sec.Name.rstrip(b"\x00") == b".text":
            return sec
    return None


def find_string_locations(pe, needle):
    locs = []
    for sec in pe.sections:
        s_base = pe.OPTIONAL_HEADER.ImageBase + sec.VirtualAddress
        s_data = sec.get_data(sec.VirtualAddress, sec.Misc_VirtualSize)
        idx = 0
        while True:
            pos = s_data.find(needle, idx)
            if pos < 0:
                break
            locs.append(s_base + pos)
            idx = pos + 1
    return locs


def scan_text_for_iat_calls(pe, iat_map):
    sec = get_text_section(pe)
    base = pe.OPTIONAL_HEADER.ImageBase + sec.VirtualAddress
    data = sec.get_data(sec.VirtualAddress, sec.Misc_VirtualSize)
    md = Cs(CS_ARCH_X86, CS_MODE_32)
    md.detail = True
    per_api = {}
    for ins in md.disasm(data, base):
        if ins.mnemonic in ("call", "jmp") and "[" in ins.op_str:
            inside = ins.op_str[ins.op_str.find("[") + 1: ins.op_str.find("]")]
            try:
                addr = int(inside, 16)
                if addr in iat_map:
                    api = iat_map[addr]
                    per_api.setdefault(api, []).append(ins.address)
            except ValueError:
                pass
    return per_api


def find_string_xrefs(pe, string_vas):
    sec = get_text_section(pe)
    base = pe.OPTIONAL_HEADER.ImageBase + sec.VirtualAddress
    data = sec.get_data(sec.VirtualAddress, sec.Misc_VirtualSize)
    md = Cs(CS_ARCH_X86, CS_MODE_32)
    md.detail = True
    xrefs = {sv: [] for sv in string_vas}
    for ins in md.disasm(data, base):
        if ins.mnemonic in ("push", "mov", "lea", "cmp"):
            for sv in string_vas:
                hexv = f"0x{sv:08x}"
                hexv_short = f"0x{sv:x}"
                if hexv in ins.op_str or hexv_short in ins.op_str:
                    xrefs[sv].append(ins.address)
    return xrefs


def disasm_around(pe, va, before=24, after=16, back_bytes=192):
    sec = get_text_section(pe)
    base = pe.OPTIONAL_HEADER.ImageBase + sec.VirtualAddress
    data = sec.get_data(sec.VirtualAddress, sec.Misc_VirtualSize)
    start_off = max(0, va - base - back_bytes)
    md = Cs(CS_ARCH_X86, CS_MODE_32)
    md.detail = True
    insns = list(md.disasm(data[start_off:], base + start_off))
    idx = None
    for i, ins in enumerate(insns):
        if ins.address == va:
            idx = i
            break
    if idx is None:
        return [{"note": "va not at instruction boundary", "va": f"0x{va:08x}"}]
    lo = max(0, idx - before)
    hi = min(len(insns), idx + after + 1)
    return [{
        "addr": f"0x{ins.address:08x}",
        "bytes": ins.bytes.hex(),
        "mnemonic": ins.mnemonic,
        "op_str": ins.op_str,
    } for ins in insns[lo:hi]]


def main():
    pe = load_pe()
    iat_map = build_iat_map(pe)
    print(f"[*] IAT entries: {len(iat_map)}", file=sys.stderr)

    result = {
        "exe": EXE,
        "image_base": f"0x{pe.OPTIONAL_HEADER.ImageBase:08x}",
        "exact_string_locations": {},
        "prefix_string_locations": {},
        "string_xrefs": {},
        "iat_callsites": {},
        "disasm_around_create_mailslot": [],
        "disasm_around_get_mailslot_info": [],
        "disasm_around_string_xrefs": {},
    }

    # 1. exact string locations
    for label, needle in EXACT_STRINGS.items():
        locs = find_string_locations(pe, needle)
        result["exact_string_locations"][label] = {
            "needle": needle.decode("latin-1").rstrip("\x00"),
            "locations": [f"0x{v:08x}" for v in locs],
        }

    # 2. prefix string locations (find ALL mailslot/mutex names)
    for label, needle in PREFIX_STRINGS.items():
        locs = find_string_locations(pe, needle)
        # for each location, extract the null-terminated string
        entries = []
        for va in locs:
            sec = None
            for s in pe.sections:
                s_base = pe.OPTIONAL_HEADER.ImageBase + s.VirtualAddress
                if s_base <= va < s_base + s.Misc_VirtualSize:
                    sec = s
                    break
            if not sec:
                continue
            s_data = sec.get_data(sec.VirtualAddress, sec.Misc_VirtualSize)
            off = va - (pe.OPTIONAL_HEADER.ImageBase + sec.VirtualAddress)
            end = s_data.find(b"\x00", off)
            if end < 0:
                end = off + 64
            raw = s_data[off:end]
            try:
                txt = raw.decode("ascii")
            except UnicodeDecodeError:
                txt = raw.decode("latin-1")
            entries.append({"va": f"0x{va:08x}", "string": txt})
        result["prefix_string_locations"][label] = entries

    # 3. xrefs to exact mailslot/mutex strings
    all_string_vas = []
    for label, needle in EXACT_STRINGS.items():
        locs = find_string_locations(pe, needle)
        for va in locs:
            all_string_vas.append((label, va))
    xref_map = find_string_xrefs(pe, [va for _, va in all_string_vas])
    for label, va in all_string_vas:
        sites = xref_map.get(va, [])
        result["string_xrefs"].setdefault(label, []).append({
            "string_va": f"0x{va:08x}",
            "xref_sites": [f"0x{a:08x}" for a in sites],
        })

    # 4. IAT call sites
    print("[*] scanning .text for IAT calls...", file=sys.stderr)
    per_api = scan_text_for_iat_calls(pe, iat_map)
    for api, sites in per_api.items():
        if any(t in api for t in TARGET_API_SUBSTR):
            result["iat_callsites"][api] = [f"0x{a:08x}" for a in sites]

    # 5. disasm around CreateMailslotA call sites
    for api, sites in result["iat_callsites"].items():
        if api.endswith("!CreateMailslotA"):
            for site_str in sites:
                site = int(site_str, 16)
                ctx = disasm_around(pe, site, before=24, after=12)
                result["disasm_around_create_mailslot"].append({
                    "call_at": site_str,
                    "api": api,
                    "context": ctx,
                })
        elif api.endswith("!GetMailslotInfo"):
            for site_str in sites:
                site = int(site_str, 16)
                ctx = disasm_around(pe, site, before=20, after=16)
                result["disasm_around_get_mailslot_info"].append({
                    "call_at": site_str,
                    "api": api,
                    "context": ctx,
                })

    # 6. disasm around mailslot string xrefs
    for label, entries in result["string_xrefs"].items():
        for entry in entries:
            for site_str in entry["xref_sites"]:
                site = int(site_str, 16)
                ctx = disasm_around(pe, site, before=16, after=24)
                result["disasm_around_string_xrefs"].setdefault(label, []).append({
                    "xref_at": site_str,
                    "string_va": entry["string_va"],
                    "context": ctx,
                })

    # write
    out = Path(OUT_JSON)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)
    print(f"[+] wrote {out}", file=sys.stderr)

    # summary
    print("\n=== exact string locations ===", file=sys.stderr)
    for label, info in result["exact_string_locations"].items():
        print(f"  {label:25s}: {info['locations']}", file=sys.stderr)

    print("\n=== prefix string locations (ALL mailslot/mutex names) ===", file=sys.stderr)
    for label, entries in result["prefix_string_locations"].items():
        print(f"  {label}:", file=sys.stderr)
        for e in entries:
            print(f"    {e['va']}: {e['string']!r}", file=sys.stderr)

    print("\n=== string xref counts ===", file=sys.stderr)
    for label, entries in result["string_xrefs"].items():
        total = sum(len(e["xref_sites"]) for e in entries)
        print(f"  {label:25s}: {total} xrefs", file=sys.stderr)

    print("\n=== IAT call sites (mailslot-related) ===", file=sys.stderr)
    for api, sites in result["iat_callsites"].items():
        print(f"  {api:45s} x{len(sites):3d}  {sites[:6]}", file=sys.stderr)


if __name__ == "__main__":
    main()
