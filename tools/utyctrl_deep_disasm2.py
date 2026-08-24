#!/usr/bin/env python
"""
UtyCtrl.dll deep analysis pass 2.
- Disassemble init function 0x10001000..0x1000107f (CreateMutexA here)
- Disassemble ExecCmd subfunc 0x10015390 (param packer)
- Disassemble ExecCmd complete (100 instrs)
- Dump IAT slots of interest
- Find all uses of immediate 0x1388 (5000ms timeout)
- Find all 0x1002C870 (g_last_count) refs
- Dump strings near 0x10023854 (mutex + mailslot names cluster)
"""
import json
import sys

import pefile
from capstone import CS_ARCH_X86, CS_MODE_32, Cs

DLL = r"d:\my git\RS-BA1\RemoteController\UtyCtrl.dll"
OUT = r"d:\my git\scratchpad\tools\pe_analysis_output\UtyCtrl_deep_disasm2.json"
IB = 0x10000000

IAT_SLOTS_OF_INTEREST = [
    0x10020210,  # ReadFile ?
    0x10020214,  # Sleep ?
    0x10020218,  # GetMailslotInfo ?
    0x1002021c,  # WriteFile ?
    0x10020220,  # CreateMailslotA ?
    0x10020224,  # CreateFileA ?
    0x10020228,  # WaitForSingleObject ?
    0x1002022c,  # CloseHandle ?
    0x10020230,  # ReleaseMutex ?
]


def load():
    return pefile.PE(DLL, fast_load=False)


def sec_bytes(pe, va):
    for s in pe.sections:
        start = IB + s.VirtualAddress
        end = start + s.Misc_VirtualSize
        if start <= va < end:
            return s.get_data(s.VirtualAddress, s.Misc_VirtualSize), start
    return None, None


def disasm(pe, va, count):
    data, base = sec_bytes(pe, va)
    if data is None:
        return [{"error": f"no section for {va:#x}"}]
    md = Cs(CS_ARCH_X86, CS_MODE_32)
    md.detail = True
    out = []
    for ins in md.disasm(data[va - base:], va):
        out.append({
            "addr": f"0x{ins.address:08x}",
            "bytes": ins.bytes.hex(),
            "mnemonic": ins.mnemonic,
            "op_str": ins.op_str,
        })
        if len(out) >= count:
            break
    return out


def iat_name(pe, slot_va):
    for e in pe.DIRECTORY_ENTRY_IMPORT:
        dll = e.dll.decode("ascii", errors="replace")
        for imp in e.imports:
            if imp.address == slot_va:
                n = imp.name.decode() if imp.name else f"ord{imp.ordinal}"
                return f"{dll}!{n}"
    return None


def dump_strings(pe, start_va, length):
    data, base = sec_bytes(pe, start_va)
    if data is None:
        return []
    chunk = data[start_va - base: start_va - base + length]
    out = []
    cur = []
    cur_start = start_va
    for i, b in enumerate(chunk):
        if b == 0:
            if cur:
                s = bytes(cur).decode("ascii", errors="replace")
                out.append({"va": f"0x{cur_start:08x}", "str": s})
                cur = []
            cur_start = start_va + i + 1
        elif 32 <= b < 127:
            if not cur:
                cur_start = start_va + i
            cur.append(b)
        else:
            if cur:
                s = bytes(cur).decode("ascii", errors="replace")
                out.append({"va": f"0x{cur_start:08x}", "str": s})
                cur = []
            cur_start = start_va + i + 1
    if cur:
        s = bytes(cur).decode("ascii", errors="replace")
        out.append({"va": f"0x{cur_start:08x}", "str": s})
    return out


def find_imm_refs(pe, imm_value):
    """Find push imm32 / mov reg,imm32 with given value across .text."""
    text = None
    for s in pe.sections:
        if s.Name.rstrip(b"\x00") == b".text":
            text = s
            break
    if not text:
        return []
    base = IB + text.VirtualAddress
    data = text.get_data(text.VirtualAddress, text.Misc_VirtualSize)
    md = Cs(CS_ARCH_X86, CS_MODE_32)
    md.detail = True
    refs = []
    hexl = f"0x{imm_value:x}"
    hexlong = f"0x{imm_value:08x}"
    dec = str(imm_value)
    for ins in md.disasm(data, base):
        if (hexl in ins.op_str) or (hexlong in ins.op_str) or (dec in ins.op_str and ins.mnemonic in ("push", "mov", "cmp")):
            refs.append({
                "at": f"0x{ins.address:08x}",
                "insn": f"{ins.mnemonic} {ins.op_str}",
            })
    return refs


def main():
    pe = load()
    result = {
        "iat_slots": {},
        "init_func_0x10001000": disasm(pe, 0x10001000, 40),
        "exec_cmd_subfunc_0x10015390": disasm(pe, 0x10015390, 60),
        "exec_cmd_full": disasm(pe, 0x100016A0, 100),
        "strings_near_mailslot_cluster": dump_strings(pe, 0x10023840, 0x200),
        "imm_5000_refs": find_imm_refs(pe, 5000),
        "imm_260_refs": find_imm_refs(pe, 260),
        "imm_0x1388_refs": find_imm_refs(pe, 0x1388),
    }

    for slot in IAT_SLOTS_OF_INTEREST:
        result["iat_slots"][f"0x{slot:08x}"] = iat_name(pe, slot)

    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)
    print(f"[+] wrote {OUT}", file=sys.stderr)

    print("\n=== IAT slots ===", file=sys.stderr)
    for slot, name in result["iat_slots"].items():
        print(f"  {slot}  ->  {name}", file=sys.stderr)

    print("\n=== strings near mailslot cluster (0x10023840..0x10023a40) ===", file=sys.stderr)
    for s in result["strings_near_mailslot_cluster"]:
        if s["str"]:
            print(f"  {s['va']}  {s['str']!r}", file=sys.stderr)

    print("\n=== 0x1388 (5000ms timeout) refs ===", file=sys.stderr)
    for r in result["imm_0x1388_refs"]:
        print(f"  {r['at']}: {r['insn']}", file=sys.stderr)

    print("\n=== 260 (0x104) refs ===", file=sys.stderr)
    for r in result["imm_260_refs"]:
        print(f"  {r['at']}: {r['insn']}", file=sys.stderr)


if __name__ == "__main__":
    main()
