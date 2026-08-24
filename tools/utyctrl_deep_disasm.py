#!/usr/bin/env python
"""
UtyCtrl.dll deep static analysis.
- Disassemble 9 exports (50 instrs each)
- Deep-disassemble core mailslot function at 0x10001080
- Map all IAT call sites (which API is called where)
- Find string xrefs for mailslot/mutex names
- Find xrefs for key global vars (0x1002c86c, 0x1002c870)
"""

import json
import sys
from pathlib import Path

import pefile
from capstone import CS_ARCH_X86, CS_MODE_32, Cs

DLL = r"d:\my git\RS-BA1\RemoteController\UtyCtrl.dll"
OUT_JSON = r"d:\my git\scratchpad\tools\pe_analysis_output\UtyCtrl_deep_disasm.json"
IMAGE_BASE = 0x10000000

# Exports (name, VA)
EXPORTS = [
    ("GetCountClientTrans",        0x100011C0),
    ("GetClientTransInfo",         0x10001240),
    ("GetClientTransInfo2",        0x100012C0),
    ("GetClientTransVol",          0x10001370),
    ("GetClientTransVol3",         0x10001430),
    ("GetCommandProcCount",        0x100014E0),
    ("GetRemoteTransNetworkSet",   0x10001540),
    ("GetRemoteTransState",        0x100015F0),
    ("ExecCmd",                    0x100016A0),
]

# Core function called by every export (mailslot transaction)
CORE_FUNCS = [
    ("core_mailslot_xact",  0x10001080),   # called by every export
]

# Globals of interest
GLOBALS = {
    0x1002C86C: "g_conn_state",      # checked by every export; 0 == disconnected
    0x1002C870: "g_last_count",       # written by GetCountClientTrans
    0x10028C70: "g_security_cookie",  # xor'd with esp (stack canary)
}


def load_pe():
    pe = pefile.PE(DLL, fast_load=False)
    return pe


def build_iat_map(pe):
    """Return {VA_of_IAT_slot: 'dll!func'} for every imported function."""
    iat = {}
    if not hasattr(pe, "DIRECTORY_ENTRY_IMPORT"):
        return iat
    for entry in pe.DIRECTORY_ENTRY_IMPORT:
        dll = entry.dll.decode("ascii", errors="replace")
        for imp in entry.imports:
            if imp.address is None:
                continue
            name = imp.name.decode("ascii", errors="replace") if imp.name else f"ord{imp.ordinal}"
            iat[imp.address] = f"{dll}!{name}"
    return iat


def get_section_bytes(pe, va):
    """Return (bytes, file_offset) for the section containing va."""
    for sec in pe.sections:
        start = pe.OPTIONAL_HEADER.ImageBase + sec.VirtualAddress
        end = start + sec.Misc_VirtualSize
        if start <= va < end:
            data = sec.get_data(sec.VirtualAddress, sec.Misc_VirtualSize)
            return data, start
    return None, None


def disasm_range(pe, va_start, count):
    """Disassemble `count` instructions starting at va_start. Returns list of dicts."""
    data, base = get_section_bytes(pe, va_start)
    if data is None:
        return [{"error": f"no section for {va_start:#x}"}]
    off = va_start - base
    md = Cs(CS_ARCH_X86, CS_MODE_32)
    md.detail = True
    out = []
    for ins in md.disasm(data[off:], va_start):
        out.append({
            "addr": f"0x{ins.address:08x}",
            "bytes": ins.bytes.hex(),
            "mnemonic": ins.mnemonic,
            "op_str": ins.op_str,
        })
        if len(out) >= count:
            break
    return out


def find_call_targets(pe, va_start, max_bytes=2000):
    """Walk forward from va_start collecting call/jmp targets within the function."""
    data, base = get_section_bytes(pe, va_start)
    if data is None:
        return []
    off = va_start - base
    md = Cs(CS_ARCH_X86, CS_MODE_32)
    md.detail = True
    targets = []
    bytes_seen = 0
    for ins in md.disasm(data[off:off+max_bytes], va_start):
        bytes_seen += len(ins.bytes)
        if bytes_seen > max_bytes:
            break
        # stop at ret/retf
        if ins.mnemonic in ("ret", "retf"):
            break
        if ins.mnemonic == "call":
            # direct call e8 rel32 OR call [mem] ff 15
            op = ins.op_str.strip()
            # direct call to relative target
            try:
                tgt = int(op, 16)
                targets.append(("call_direct", f"0x{ins.address:08x}", f"0x{tgt:08x}"))
            except ValueError:
                # indirect call dword ptr [0x...]  -> IAT
                targets.append(("call_indirect", f"0x{ins.address:08x}", op))
    return targets


def resolve_iat_calls_in_func(pe, iat_map, va_start, max_bytes=4000):
    """Walk function, resolve every call/jmp through IAT to api name."""
    data, base = get_section_bytes(pe, va_start)
    if data is None:
        return []
    off = va_start - base
    md = Cs(CS_ARCH_X86, CS_MODE_32)
    md.detail = True
    calls = []
    bytes_seen = 0
    for ins in md.disasm(data[off:off+max_bytes], va_start):
        bytes_seen += len(ins.bytes)
        if bytes_seen > max_bytes:
            break
        if ins.mnemonic in ("ret", "retf", "jmp"):
            # jmp may be tail-call; still record, then break for ret
            if ins.mnemonic == "ret":
                break
        if ins.mnemonic in ("call", "jmp"):
            # indirect through IAT: op like "dword ptr [0x1002xxxx]"
            op = ins.op_str
            if "[" in op:
                # extract hex addr inside brackets
                inside = op[op.find("[")+1: op.find("]")]
                try:
                    addr = int(inside, 16)
                    if addr in iat_map:
                        calls.append({
                            "kind": ins.mnemonic,
                            "at": f"0x{ins.address:08x}",
                            "iat_va": f"0x{addr:08x}",
                            "api": iat_map[addr],
                        })
                except ValueError:
                    pass
    return calls


def scan_text_for_iat_calls(pe, iat_map):
    """Scan whole .text section, find all call/jmp [IAT]. Return per-API list of call sites."""
    text = None
    for sec in pe.sections:
        if sec.Name.rstrip(b"\x00") == b".text":
            text = sec
            break
    if text is None:
        return {}
    base = pe.OPTIONAL_HEADER.ImageBase + text.VirtualAddress
    data = text.get_data(text.VirtualAddress, text.Misc_VirtualSize)
    md = Cs(CS_ARCH_X86, CS_MODE_32)
    md.detail = True
    per_api = {}
    for ins in md.disasm(data, base):
        if ins.mnemonic in ("call", "jmp") and "[" in ins.op_str:
            inside = ins.op_str[ins.op_str.find("[")+1: ins.op_str.find("]")]
            try:
                addr = int(inside, 16)
                if addr in iat_map:
                    api = iat_map[addr]
                    per_api.setdefault(api, []).append(f"0x{ins.address:08x}")
            except ValueError:
                pass
    return per_api


def find_string_xrefs(pe, needle_bytes):
    """Find all references (push imm32 / mov reg,imm32 / cmp/mov dword ptr [imm32]) to addresses whose content equals needle_bytes."""
    text = None
    for sec in pe.sections:
        if sec.Name.rstrip(b"\x00") == b".text":
            text = sec
            break
    if text is None:
        return []
    base = pe.OPTIONAL_HEADER.ImageBase + text.VirtualAddress
    data = text.get_data(text.VirtualAddress, text.Misc_VirtualSize)

    # locate string VA(s)
    string_vas = []
    # search all sections for the bytes
    for sec in pe.sections:
        s_base = pe.OPTIONAL_HEADER.ImageBase + sec.VirtualAddress
        s_data = sec.get_data(sec.VirtualAddress, sec.Misc_VirtualSize)
        idx = 0
        while True:
            pos = s_data.find(needle_bytes, idx)
            if pos < 0:
                break
            string_vas.append(s_base + pos)
            idx = pos + 1

    if not string_vas:
        return []

    md = Cs(CS_ARCH_X86, CS_MODE_32)
    md.detail = True
    xrefs = []
    for ins in md.disasm(data, base):
        # push imm32 / mov reg,imm32 / lea reg,[imm32] / cmp dword ptr [imm32],imm
        if ins.mnemonic in ("push", "mov", "lea", "cmp") and "0x" in ins.op_str:
            for sv in string_vas:
                hexv = f"0x{sv:08x}"
                # also short form like 0x100xxxxx
                if hexv in ins.op_str or f"0x{sv:x}" in ins.op_str:
                    xrefs.append({
                        "string_va": hexv,
                        "ref_at": f"0x{ins.address:08x}",
                        "insn": f"{ins.mnemonic} {ins.op_str}",
                    })
                    break
    return xrefs


def find_global_xrefs(pe, target_va):
    """Find all instructions referencing target_va (mov/cmp/push/lea with imm operand == target_va or [target_va])."""
    text = None
    for sec in pe.sections:
        if sec.Name.rstrip(b"\x00") == b".text":
            text = sec
            break
    if text is None:
        return []
    base = pe.OPTIONAL_HEADER.ImageBase + text.VirtualAddress
    data = text.get_data(text.VirtualAddress, text.Misc_VirtualSize)
    md = Cs(CS_ARCH_X86, CS_MODE_32)
    md.detail = True
    xrefs = []
    hex_long = f"0x{target_va:08x}"
    hex_short = f"0x{target_va:x}"
    for ins in md.disasm(data, base):
        if hex_long in ins.op_str or hex_short in ins.op_str:
            xrefs.append({
                "at": f"0x{ins.address:08x}",
                "insn": f"{ins.mnemonic} {ins.op_str}",
            })
    return xrefs


def find_string_in_image(pe, needle_bytes):
    """Return list of VAs where needle_bytes occurs anywhere in the image."""
    found = []
    for sec in pe.sections:
        s_base = pe.OPTIONAL_HEADER.ImageBase + sec.VirtualAddress
        s_data = sec.get_data(sec.VirtualAddress, sec.Misc_VirtualSize)
        idx = 0
        while True:
            pos = s_data.find(needle_bytes, idx)
            if pos < 0:
                break
            found.append(s_base + pos)
            idx = pos + 1
    return found


def main():
    pe = load_pe()
    iat_map = build_iat_map(pe)
    print(f"[*] IAT entries: {len(iat_map)}", file=sys.stderr)

    result = {
        "dll": DLL,
        "image_base": f"0x{pe.OPTIONAL_HEADER.ImageBase:08x}",
        "exports_disasm": {},
        "core_funcs_disasm": {},
        "core_funcs_calls": {},
        "iat_callsites_per_api": {},
        "string_xrefs": {},
        "global_xrefs": {},
        "string_locations": {},
    }

    # 1. disassemble exports
    for name, va in EXPORTS:
        print(f"[*] disasm export {name} @ {va:#x}", file=sys.stderr)
        result["exports_disasm"][name] = {
            "va": f"0x{va:08x}",
            "instructions": disasm_range(pe, va, 50),
        }
        # also list IAT calls inside this export (forward 4KB)
        result["exports_disasm"][name]["iat_calls"] = resolve_iat_calls_in_func(pe, iat_map, va, max_bytes=1500)
        result["exports_disasm"][name]["direct_call_targets"] = find_call_targets(pe, va, max_bytes=1500)

    # 2. core function 0x10001080 — deep disasm (200 instrs) and IAT calls
    for name, va in CORE_FUNCS:
        print(f"[*] disasm core {name} @ {va:#x}", file=sys.stderr)
        result["core_funcs_disasm"][name] = {
            "va": f"0x{va:08x}",
            "instructions": disasm_range(pe, va, 200),
        }
        result["core_funcs_calls"][name] = resolve_iat_calls_in_func(pe, iat_map, va, max_bytes=2000)
        result["core_funcs_disasm"][name]["direct_call_targets"] = find_call_targets(pe, va, max_bytes=2000)

    # 3. scan whole .text for IAT call sites
    print("[*] scanning .text for all IAT calls", file=sys.stderr)
    per_api = scan_text_for_iat_calls(pe, iat_map)
    # sort by call site count desc
    result["iat_callsites_per_api"] = dict(sorted(per_api.items(), key=lambda kv: -len(kv[1])))

    # 4. string xrefs — mailslot names + mutex
    strings_to_find = {
        "mailslot_cmd":      b"\\\\.\\mailslot\\RemoteUtyCtrlCmd\x00",
        "mailslot_res":      b"\\\\.\\mailslot\\RemoteUtyCtrlRes\x00",
        "mutex_name":        b"Icom RemoteUtyCtrl\x00",
        "pdb_path":          b"C:\\Release\\dll\\UtyCtrl\\Release\\UtyCtrl.pdb",
    }
    for label, needle in strings_to_find.items():
        locs = find_string_in_image(pe, needle)
        result["string_locations"][label] = [f"0x{v:08x}" for v in locs]
        if locs:
            # xref the first occurrence
            xrefs = find_string_xrefs(pe, needle)
            result["string_xrefs"][label] = xrefs
        else:
            result["string_xrefs"][label] = []

    # 5. global var xrefs
    for va, label in GLOBALS.items():
        print(f"[*] xref global {label} @ {va:#x}", file=sys.stderr)
        result["global_xrefs"][label] = {
            "va": f"0x{va:08x}",
            "xrefs": find_global_xrefs(pe, va),
        }

    # write
    out = Path(OUT_JSON)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)
    print(f"[+] wrote {out}", file=sys.stderr)

    # also print a summary table to stderr for quick scan
    print("\n=== IAT call site counts ===", file=sys.stderr)
    for api, sites in result["iat_callsites_per_api"].items():
        if any(k in api for k in ("Mailslot", "File", "Mutex", "WaitFor", "Sleep",
                                  "CloseHandle", "Heap", "Global", "Write", "Read",
                                  "Create", "GetLastError", "Interlocked", "QueryPerformance")):
            print(f"  {api:45s} x{len(sites):3d}  e.g. {sites[0]}", file=sys.stderr)

    print("\n=== string locations ===", file=sys.stderr)
    for label, locs in result["string_locations"].items():
        print(f"  {label:20s}: {locs}", file=sys.stderr)

    print("\n=== string xref counts ===", file=sys.stderr)
    for label, xrefs in result["string_xrefs"].items():
        print(f"  {label:20s}: {len(xrefs)} xrefs", file=sys.stderr)

    print("\n=== global xref counts ===", file=sys.stderr)
    for label, info in result["global_xrefs"].items():
        print(f"  {label:20s} ({info['va']}): {len(info['xrefs'])} xrefs", file=sys.stderr)


if __name__ == "__main__":
    main()
