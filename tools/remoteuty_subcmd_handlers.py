#!/usr/bin/env python3
"""精准逆向 RemoteUty.exe 的 4 个 ExecCmd sub_cmd handler。

背景 (mailslot_server.md §3.2):
    cmd_2 (ExecCmd) @ 0x43b02a 读取 packet[0x14] = sub_cmd (0-5),
    经跳表 0x43b0b8 分发到:
        sub_cmd 0 -> 0x43a3f0
        sub_cmd 1 -> 0x43a5f0
        sub_cmd 2 -> 0x43a800
        sub_cmd 3 -> 0x43aa70
    这些 handler 的具体语义 (CI-V 转发 / HID / UDP ...) 此前未逆向。

本脚本: 线性反汇编这 4 个 handler 函数体, 追踪其内部 call 的 API
(IAT 调用点), 找出每个 handler 是否最终写串口(CI-V) / 发 UDP / 或做其他。
"""
import json
from pathlib import Path

import pefile
from capstone import CS_ARCH_X86, CS_MODE_32, Cs

REMOTE_UTY = Path(r"d:\my git\RemoteUtility\RemoteUty.exe")
OUTPUT_DIR = Path(r"d:\my git\scratchpad\tools\pe_analysis_output")

# 目标 handler 函数 (起始地址), 按函数大小反汇编
HANDLERS = {
    "sub_cmd_0": 0x0043a3f0,
    "sub_cmd_1": 0x0043a5f0,
    "sub_cmd_2": 0x0043a800,
    "sub_cmd_3": 0x0043aa70,
}

# 每个 handler 最多反汇编的指令数 (线性, 遇到 ret 停止)
MAX_INSN = 600


def build_iat_map(pe):
    """IAT VA -> (dll, fn)"""
    iat = {}
    if not hasattr(pe, "DIRECTORY_ENTRY_IMPORT"):
        return iat
    for entry in pe.DIRECTORY_ENTRY_IMPORT:
        dll_name = entry.dll.decode("ascii", errors="replace")
        for imp in entry.imports:
            name = imp.name.decode("ascii", errors="replace") if imp.name else f"ordinal_{imp.ordinal}"
            iat[imp.address] = (dll_name, name)
    return iat


def disasm_function(pe, md, image_base, start_va, max_insn=MAX_INSN):
    """线性反汇编从 start_va 开始的函数, 遇到 ret/jmp 或超限停止。

    返回 (insns, calls): calls 是 (call_target, insn_index) 列表。
    """
    text_sec = None
    for sec in pe.sections:
        if sec.Name.rstrip(b"\x00") == b".text":
            text_sec = sec
            break
    if not text_sec:
        return [], []

    start_rva = start_va - image_base
    # 函数起始在 .text 内
    data = pe.get_data(start_rva, 0x2000)  # 8KB 预读
    insns = list(md.disasm(data, start_va))

    out = []
    calls = []
    for i, ins in enumerate(insns):
        if i >= max_insn:
            break
        out.append({
            "addr": hex(ins.address),
            "bytes": ins.bytes.hex(),
            "mnemonic": ins.mnemonic,
            "op_str": ins.op_str,
        })
        # 记录 call <imm32> (直连函数调用)
        if ins.mnemonic == "call" and ins.op_str.startswith("0x"):
            calls.append((int(ins.op_str, 16), i))
        # 遇到 ret 认为函数结束 (线性简化)
        if ins.mnemonic in ("ret", "retn"):
            break
    return out, calls


def resolve_call_meaning(call_target, iat_map, ci_v_related=None):
    """判断 call_target 是否命中 IAT (即调用 Win32 API)。

    返回字符串描述。
    """
    # IAT thunk 形式: call dword ptr [<iat_va>] 的 op_str 是内存操作
    # capstone 对 FF 15 显示为 "call dword ptr [0x...]"
    # 这里直接查 IAT map: call_target 是 IAT slot 的 VA
    if call_target in iat_map:
        dll, fn = iat_map[call_target]
        return f"API {dll}!{fn}"
    return None


def main():
    pe = pefile.PE(str(REMOTE_UTY), fast_load=False)
    md = Cs(CS_ARCH_X86, CS_MODE_32)
    image_base = pe.OPTIONAL_HEADER.ImageBase
    iat_map = build_iat_map(pe)
    print(f"[*] {REMOTE_UTY.name} image_base={hex(image_base)} iat_slots={len(iat_map)}")

    result = {}
    for name, start_va in HANDLERS.items():
        print(f"\n===== {name} @ {hex(start_va)} =====")
        insns, calls = disasm_function(pe, md, image_base, start_va)
        result[name] = {
            "start_va": hex(start_va),
            "insn_count": len(insns),
            "api_calls": [],
            "insns": insns,
        }

        # 解析每个 call 是否 API
        for target, idx in calls:
            meaning = resolve_call_meaning(target, iat_map)
            if meaning:
                result[name]["api_calls"].append({
                    "idx": idx,
                    "addr": insns[idx]["addr"],
                    "target": hex(target),
                    "meaning": meaning,
                })
                print(f"  [{idx}] {insns[idx]['addr']}: {insns[idx]['mnemonic']} "
                      f"{insns[idx]['op_str']}  ->  {meaning}")

    pe.close()

    out_path = OUTPUT_DIR / "RemoteUty_subcmd_handlers.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)
    print(f"\n[+] Wrote {out_path}")


if __name__ == "__main__":
    main()