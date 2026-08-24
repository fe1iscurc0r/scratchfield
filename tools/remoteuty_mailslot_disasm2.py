#!/usr/bin/env python
"""RemoteUty.exe Mailslot server step 2: deep disasm of key sites."""

import json
import sys
from pathlib import Path

import pefile
from capstone import CS_ARCH_X86, CS_MODE_32, Cs

EXE = r"d:\my git\RemoteUtility\RemoteUty.exe"
OUT_JSON = r"d:\my git\scratchpad\tools\pe_analysis_output\RemoteUty_mailslot_disasm2.json"


def load_pe():
    return pefile.PE(EXE, fast_load=False)


def get_text_section(pe):
    for sec in pe.sections:
        if sec.Name.rstrip(b"\x00") == b".text":
            return sec
    return None


def disasm_from(pe, va, count=60):
    sec = get_text_section(pe)
    base = pe.OPTIONAL_HEADER.ImageBase + sec.VirtualAddress
    data = sec.get_data(sec.VirtualAddress, sec.Misc_VirtualSize)
    off = va - base
    if off < 0 or off >= len(data):
        return [{"error": f"offset {off:#x} out of range for va {va:#x}"}]
    md = Cs(CS_ARCH_X86, CS_MODE_32)
    md.detail = True
    out = []
    for ins in md.disasm(data[off:], va):
        out.append({
            "addr": f"0x{ins.address:08x}",
            "bytes": ins.bytes.hex(),
            "mnemonic": ins.mnemonic,
            "op_str": ins.op_str,
        })
        if len(out) >= count:
            break
    return out


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


def read_dwords(pe, va, count=9):
    out = []
    for sec in pe.sections:
        s_base = pe.OPTIONAL_HEADER.ImageBase + sec.VirtualAddress
        if s_base <= va < s_base + sec.Misc_VirtualSize:
            data = sec.get_data(sec.VirtualAddress, sec.Misc_VirtualSize)
            off = va - s_base
            for i in range(count):
                pos = off + i * 4
                if pos + 4 > len(data):
                    out.append(None)
                else:
                    val = int.from_bytes(data[pos:pos + 4], "little")
                    out.append(f"0x{val:08x}")
            return out
    return [None] * count


def main():
    pe = load_pe()
    result = {"exe": EXE, "image_base": f"0x{pe.OPTIONAL_HEADER.ImageBase:08x}"}

    print("[*] disasm thread entry 0x43adc0", file=sys.stderr)
    result["thread_entry_0x43adc0"] = disasm_from(pe, 0x43adc0, 80)

    print("[*] disasm around ReadFile 0x43ae3c", file=sys.stderr)
    result["readfile_0x43ae3c"] = disasm_around(pe, 0x43ae3c, before=30, after=12, back_bytes=240)

    print("[*] disasm around ReadFile 0x43ae85", file=sys.stderr)
    result["readfile_0x43ae85"] = disasm_around(pe, 0x43ae85, before=20, after=20, back_bytes=192)

    print("[*] reading jump table 0x43b094", file=sys.stderr)
    jt = read_dwords(pe, 0x43b094, 12)
    result["jump_table_0x43b094"] = {
        "raw_dwords": jt,
        "cmd_handlers": {f"cmd_{i}": jt[i] for i in range(min(9, len(jt))) if jt[i]},
    }

    result["cmd_handler_disasm"] = {}
    for i in range(9):
        addr_str = jt[i] if i < len(jt) else None
        if not addr_str:
            continue
        addr = int(addr_str, 16)
        print(f"[*] disasm cmd_{i} handler {addr_str}", file=sys.stderr)
        result["cmd_handler_disasm"][f"cmd_{i}_at_{addr_str}"] = disasm_from(pe, addr, 20)

    print("[*] disasm CreateMailslotA caller 0x434180", file=sys.stderr)
    result["createmailslot_caller"] = disasm_from(pe, 0x434180, 80)

    print("[*] disasm around CreateFileA 0x41136d", file=sys.stderr)
    result["createfilea_0x41136d"] = disasm_around(pe, 0x41136d, before=24, after=16, back_bytes=256)

    print("[*] disasm around ReadFile 0x411b43", file=sys.stderr)
    result["readfile_0x411b43"] = disasm_around(pe, 0x411b43, before=20, after=16, back_bytes=192)

    print("[*] disasm around WriteFile 0x41191b", file=sys.stderr)
    result["writefile_0x41191b"] = disasm_around(pe, 0x41191b, before=20, after=16, back_bytes=192)

    out = Path(OUT_JSON)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)
    print(f"[+] wrote {out}", file=sys.stderr)

    print("\n=== jump table @ 0x43b094 ===", file=sys.stderr)
    for i, a in enumerate(jt[:9]):
        print(f"  cmd_{i}: {a}", file=sys.stderr)


if __name__ == "__main__":
    main()
