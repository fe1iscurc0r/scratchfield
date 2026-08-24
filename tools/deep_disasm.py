#!/usr/bin/env python3
"""RS-BA1 V2 深度静态逆向分析脚本

针对 RadioSch.dll + RemoteUty.exe 做：
1. RadioSch.dll 5 个导出函数深度反汇编（前 80 条指令）
   - 识别 IAT 调用（kernel32/setupapi 等导入函数）
   - 识别字符串字面量引用
2. RemoteUty.exe WS2_32.dll 导入地址表（IAT）解析
   - 找出每个 WS2_32 函数被调用的位置
   - 搜索端口常量（htons 调用前的 push 0xXXXX）
3. 搜索 USB VID/PID 字符串和数字常量
4. 搜索 SETUPAPI 调用前后参数构造
5. 输出 JSON 报告
"""
import json
import os
import re
import sys
from collections import defaultdict
from pathlib import Path

import pefile
from capstone import CS_ARCH_X86, CS_GRP_CALL, CS_GRP_JUMP, CS_MODE_32, CS_OP_IMM, CS_OP_MEM, Cs

# ── 配置 ──────────────────────────────────────────────
UTILITY_DIR = Path(r"d:\my git\RemoteUtility")
OUTPUT_DIR  = Path(r"d:\my git\scratchpad\tools\pe_analysis_output")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

RADIO_SCH = UTILITY_DIR / "RadioSch.dll"
REMOTE_UTY = UTILITY_DIR / "RemoteUty.exe"

NUM_INSN = 80   # 每个导出函数反汇编前 80 条指令


def build_iat_map(pe):
    """构建 IAT: 地址 -> (dll, func_name)"""
    iat = {}
    if not hasattr(pe, "DIRECTORY_ENTRY_IMPORT"):
        return iat
    for entry in pe.DIRECTORY_ENTRY_IMPORT:
        dll_name = entry.dll.decode("ascii", errors="replace")
        for imp in entry.imports:
            name = imp.name.decode("ascii", errors="replace") if imp.name else f"ordinal_{imp.ordinal}"
            # imp.address 是 IAT 表项地址（含 image_base）
            iat[imp.address] = (dll_name, name)
            # 同时记录 thunk 地址（有些 PE 用 first_thunk）
    return iat


def build_string_xref(pe, filepath):
    """构建字符串地址表：rva -> 字符串内容
    返回 {rva: string}，反汇编时可以查到 push 0xXXXXXXXX 是否引用字符串
    """
    raw = filepath.read_bytes()
    str_map = {}

    # ASCII 字符串
    for m in re.finditer(rb"[\x20-\x7e]{5,}", raw):
        s = m.group().decode("ascii", errors="replace")
        # 该字符串在文件中的偏移 → 转 RVA
        for section in pe.sections:
            file_off_start = section.PointerToRawData
            file_off_end   = file_off_start + section.SizeOfRawData
            if file_off_start <= m.start() < file_off_end:
                rva = section.VirtualAddress + (m.start() - file_off_start)
                # 只记录第一次出现
                if rva not in str_map:
                    str_map[rva] = s
                break

    # UTF-16LE 字符串
    for m in re.finditer(rb"(?:[\x20-\x7e]\x00){5,}", raw):
        try:
            s = m.group().decode("utf-16-le")
        except Exception:
            continue
        for section in pe.sections:
            file_off_start = section.PointerToRawData
            file_off_end   = file_off_start + section.SizeOfRawData
            if file_off_start <= m.start() < file_off_end:
                rva = section.VirtualAddress + (m.start() - file_off_start)
                if rva not in str_map:
                    str_map[rva] = s
                break

    return str_map


def resolve_operand(op, image_base, iat, str_map):
    """解析操作数：是否是 IAT 调用、是否是字符串引用
    Capstone 5.x X86Op 结构：
      - op.type: CS_OP_REG / CS_OP_IMM / CS_OP_MEM
      - op.reg (when CS_OP_REG)
      - op.imm (when CS_OP_IMM)
      - op.mem.base, op.mem.index, op.mem.scale, op.mem.disp (when CS_OP_MEM)
    """
    info = {}
    if op.type == CS_OP_IMM:
        val = op.imm
        if image_base <= val < image_base + 0x400000:
            rva = val - image_base
            if rva in str_map:
                info["string_ref"] = str_map[rva]
            info["imm_rva"] = hex(rva)
        else:
            info["imm"] = hex(val)
    elif op.type == CS_OP_MEM:
        mem = op.mem
        # 仅当基址/索引为 0 时是绝对地址
        if mem.base == 0 and mem.index == 0:
            val = mem.disp
            if image_base <= val < image_base + 0x400000:
                rva = val - image_base
                if rva in iat:
                    info["iat_call"] = f"{iat[rva][0]}!{iat[rva][1]}"
                if rva in str_map:
                    info["string_ref"] = str_map[rva]
                info["mem_rva"] = hex(rva)
    elif op.type == 1:  # CS_OP_REG = 1
        info["reg"] = True
    return info


def disasm_function(pe, md, image_base, iat, str_map, rva, name, num_insn=NUM_INSN):
    """反汇编单个函数前 num_insn 条指令"""
    try:
        data = pe.get_data(rva, 1024)
    except Exception as e:
        return {"name": name, "rva": hex(rva), "error": str(e), "instructions": []}

    instructions = []
    count = 0
    base_addr = image_base + rva
    for insn in md.disasm(data, base_addr):
        entry = {
            "addr": hex(insn.address),
            "bytes": insn.bytes.hex(),
            "mnemonic": insn.mnemonic,
            "op_str": insn.op_str,
        }

        # 解析操作数
        op_infos = []
        for op in insn.operands:
            info = resolve_operand(op, image_base, iat, str_map)
            if info:
                op_infos.append(info)
        if op_infos:
            entry["operands_resolved"] = op_infos

        # call 指令特殊处理
        if insn.mnemonic == "call" and insn.operands:
            first = insn.operands[0]
            if first.type == CS_OP_IMM:
                target = first.imm
                # 直接 call 内部函数（在 .text 范围内）
                if image_base <= target < image_base + 0x400000:
                    entry["call_target_rva"] = hex(target - image_base)
            elif first.type == CS_OP_MEM:
                mem = first.mem
                if mem.base == 0 and mem.index == 0:
                    target_rva = mem.disp - image_base
                    if 0 <= target_rva < 0x400000 and target_rva in iat:
                        entry["call_target"] = f"IAT: {iat[target_rva][0]}!{iat[target_rva][1]}"

        instructions.append(entry)
        count += 1
        if count >= num_insn:
            break

        if insn.mnemonic in ("ret", "retn"):
            break

    return {"name": name, "rva": hex(rva), "instructions": instructions}


def find_callers_of_iat(pe, md, image_base, target_iat_rvas, code_section):
    """在 .text 段中搜索调用特定 IAT 地址的指令位置
    target_iat_rvas: set of RVA (IAT 表项的 RVA)
    返回: {iat_rva: [(caller_addr, caller_rva, insn_str), ...]}
    """
    callers = defaultdict(list)
    text_section = None
    for sec in pe.sections:
        sec_name = sec.Name.rstrip(b"\x00").decode("ascii", errors="replace")
        if sec_name == ".text":
            text_section = sec
            break
    if text_section is None:
        return callers

    text_data = pe.get_data(text_section.VirtualAddress, text_section.SizeOfRawData)
    text_start_rva = text_section.VirtualAddress
    text_start_va  = image_base + text_start_rva

    # 对整个 .text 反汇编扫描太慢，改为字节模式搜索 FF 15 [4字节地址] (call [mem])
    # call dword ptr [addr] = FF 15 <addr32LE>
    # 也要找 FF 25 jmp [addr] (thunk)
    target_addrs = set()
    for rva in target_iat_rvas:
        target_addrs.add(image_base + rva)

    for target_va in target_addrs:
        # FF 15 <target_va_LE>
        pattern = b"\xff\x15" + target_va.to_bytes(4, "little")
        start = 0
        while True:
            idx = text_data.find(pattern, start)
            if idx < 0:
                break
            caller_rva = text_start_rva + idx
            caller_va  = text_start_va + idx
            # 反汇编这一条指令
            try:
                insn_data = text_data[idx:idx+16]
                for insn in md.disasm(insn_data, caller_va):
                    callers[target_va - image_base].append({
                        "caller_addr": hex(caller_va),
                        "caller_rva":  hex(caller_rva),
                        "insn":        f"{insn.mnemonic} {insn.op_str}",
                    })
                    break
            except Exception:
                pass
            start = idx + 1

    return callers


def analyze_radio_sch():
    """RadioSch.dll 深度分析"""
    print(f"[*] Analyzing {RADIO_SCH}")
    pe = pefile.PE(str(RADIO_SCH), fast_load=False)
    md = Cs(CS_ARCH_X86, CS_MODE_32)
    md.detail = True
    image_base = pe.OPTIONAL_HEADER.ImageBase
    iat = build_iat_map(pe)
    str_map = build_string_xref(pe, RADIO_SCH)

    result = {
        "file": "RadioSch.dll",
        "image_base": hex(image_base),
        "exports_disasm": [],
        "setupapi_callers": {},
        "usb_vid_pid_strings": [],
        "setupapi_strings": [],
    }

    # 导出函数反汇编
    if hasattr(pe, "DIRECTORY_ENTRY_EXPORT"):
        for exp in pe.DIRECTORY_ENTRY_EXPORT.symbols:
            if not exp.name:
                continue
            name = exp.name.decode("ascii", errors="replace")
            rva  = exp.address
            print(f"  - Disasm export: {name} @ RVA {hex(rva)}")
            entry = disasm_function(pe, md, image_base, iat, str_map, rva, name)
            result["exports_disasm"].append(entry)

    # 找到 SETUPAPI IAT 地址
    setupapi_iat_rvas = []
    for addr, (dll, fn) in iat.items():
        if dll.upper() == "SETUPAPI.DLL":
            setupapi_iat_rvas.append((addr - image_base, fn))
    setupapi_rva_set = set(rva for rva, _ in setupapi_iat_rvas)

    # 找调用者
    print(f"  - Finding SETUPAPI callers ({len(setupapi_iat_rvas)} functions)")
    callers = find_callers_of_iat(pe, md, image_base, setupapi_rva_set, None)
    for iat_rva, fn_name in setupapi_iat_rvas:
        result["setupapi_callers"][fn_name] = callers.get(iat_rva, [])

    # USB VID/PID 字符串
    for rva, s in str_map.items():
        if re.search(r"VID_?PID|VID_|0x[0-9a-fA-F]{4}|\\\\\\?\\(hid|usb)", s, re.IGNORECASE):
            if "VID" in s.upper() or "USB" in s.upper() or "HID" in s.upper():
                result["usb_vid_pid_strings"].append({"rva": hex(rva), "str": s})

    # SETUPAPI / 设备相关字符串
    for rva, s in str_map.items():
        if re.search(r"SetupDi|HID|\\\\\\?\\|SYSTEM\\\\CurrentControlSet|DevNode|USB", s):
            result["setupapi_strings"].append({"rva": hex(rva), "str": s})

    pe.close()
    return result


def analyze_remote_uty():
    """RemoteUty.exe 深度分析"""
    print(f"[*] Analyzing {REMOTE_UTY}")
    pe = pefile.PE(str(REMOTE_UTY), fast_load=False)
    md = Cs(CS_ARCH_X86, CS_MODE_32)
    md.detail = True
    image_base = pe.OPTIONAL_HEADER.ImageBase
    iat = build_iat_map(pe)
    str_map = build_string_xref(pe, REMOTE_UTY)

    result = {
        "file": "RemoteUty.exe",
        "image_base": hex(image_base),
        "ws2_32_iat": [],
        "ws2_32_callers": {},
        "setupapi_iat": [],
        "setupapi_callers": {},
        "port_constants": [],
        "virtual_driver_strings": [],
        "network_protocol_strings": [],
        "udp_protocol_strings": [],
    }

    # WS2_32 IAT 解析
    ws2_iat_rvas = []
    for addr, (dll, fn) in iat.items():
        if dll.upper() == "WS2_32.DLL":
            rva = addr - image_base
            ws2_iat_rvas.append((rva, fn, addr))
            result["ws2_32_iat"].append({
                "function": fn,
                "iat_rva": hex(rva),
                "iat_va":  hex(addr),
            })

    # 找 WS2_32 调用者
    print(f"  - Finding WS2_32 callers ({len(ws2_iat_rvas)} functions)")
    ws2_rva_set = set(rva for rva, _, _ in ws2_iat_rvas)
    callers = find_callers_of_iat(pe, md, image_base, ws2_rva_set, None)
    for iat_rva, fn, _ in ws2_iat_rvas:
        result["ws2_32_callers"][fn] = callers.get(iat_rva, [])

    # 找端口常量：搜索 "push 0xNNNN; call htons" 或 "push imm; ... call [htons]"
    # 端口在网络上是大端，htons 的参数是小端 imm
    # 常见端口：5005 = 0x138D, 1900 = 0x076C, 50000 = 0xC350
    print("  - Scanning port constants near htons/bind calls")
    # 找 htons IAT 地址
    htons_iat_addr = None
    for rva, fn, addr in ws2_iat_rvas:
        if fn == "htons":
            htons_iat_addr = addr
            break
    if htons_iat_addr:
        # 搜索 htons 调用前的 push imm 16
        # 实际上 htons 调用模式：push 0xNNNN ; call [htons]
        # 但更常见是 mov reg, imm; push reg; call htons
        # 暴力搜索 .text 中所有 htons 调用，反汇编前 5 条指令
        text_section = None
        for sec in pe.sections:
            if sec.Name.rstrip(b"\x00").decode("ascii", errors="replace") == ".text":
                text_section = sec
                break
        if text_section:
            text_data = pe.get_data(text_section.VirtualAddress, text_section.SizeOfRawData)
            pattern = b"\xff\x15" + htons_iat_addr.to_bytes(4, "little")
            idx = 0
            while True:
                pos = text_data.find(pattern, idx)
                if pos < 0:
                    break
                caller_rva = text_section.VirtualAddress + pos
                caller_va  = image_base + caller_rva
                # 反汇编前 16 字节 + 这条指令
                start = max(0, pos - 32)
                pre_insn = []
                try:
                    pre_data = text_data[start:pos+6]
                    for insn in md.disasm(pre_data, image_base + text_section.VirtualAddress + start):
                        pre_insn.append({
                            "addr": hex(insn.address),
                            "mnemonic": insn.mnemonic,
                            "op_str": insn.op_str,
                            "bytes": insn.bytes.hex(),
                        })
                        if insn.address >= caller_va:
                            break
                except Exception:
                    pass
                # 提取 push imm
                port_imm = None
                for ins in reversed(pre_insn):
                    if ins["mnemonic"] == "push" and ins["op_str"].startswith("0x"):
                        try:
                            port_imm = int(ins["op_str"], 16)
                        except ValueError:
                            pass
                        break
                result["port_constants"].append({
                    "caller_rva": hex(caller_rva),
                    "caller_addr": hex(caller_va),
                    "port_imm": port_imm,
                    "port_dec": port_imm if port_imm else None,
                    "pre_insns": pre_insn[-6:],
                })
                idx = pos + 1

    # SETUPAPI
    setupapi_iat_rvas = []
    for addr, (dll, fn) in iat.items():
        if dll.upper() == "SETUPAPI.DLL":
            setupapi_iat_rvas.append((addr - image_base, fn))
    setupapi_rva_set = set(rva for rva, _ in setupapi_iat_rvas)
    callers = find_callers_of_iat(pe, md, image_base, setupapi_rva_set, None)
    for iat_rva, fn_name in setupapi_iat_rvas:
        result["setupapi_callers"][fn_name] = callers.get(iat_rva, [])
        result["setupapi_iat"].append({"function": fn_name, "iat_rva": hex(iat_rva)})

    # 虚拟驱动字符串
    for rva, s in str_map.items():
        if re.search(r"icom_v|vaudio|vserial|IcomVSerial|ICOM_VAUDIO|ICOM_SERIAL|Icom\\\\RemoteUty|Virtual", s, re.IGNORECASE):
            result["virtual_driver_strings"].append({"rva": hex(rva), "str": s})

    # 网络协议字符串
    for rva, s in str_map.items():
        if re.search(r"CUdp|CUDPCtrl|AudioPort|CommandPort|SerialPort|MUTEX_SERVER|MUTEX_REMOTEUTY|FTCP|tcPW|sendPacket|recvProc|sendReq|ExecSync|ExecFsync|ExecCmd|KeepAlive", s, re.IGNORECASE):
            result["network_protocol_strings"].append({"rva": hex(rva), "str": s})
        if re.search(r"udp|UDP|recvfrom|sendto|recvCallback|sendUdp|closeUdp|audioSendThread|audioRecvThread", s, re.IGNORECASE):
            result["udp_protocol_strings"].append({"rva": hex(rva), "str": s})

    pe.close()
    return result


def main():
    out = {
        "radio_sch": analyze_radio_sch(),
        "remote_uty": analyze_remote_uty(),
    }

    out_path = OUTPUT_DIR / "deep_analysis.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, ensure_ascii=False)
    print(f"[+] Wrote {out_path}")
    print(f"    RadioSch.dll: {len(out['radio_sch']['exports_disasm'])} exports disassembled")
    print(f"    RadioSch.dll: {sum(len(v) for v in out['radio_sch']['setupapi_callers'].values())} SETUPAPI call sites")
    print(f"    RemoteUty.exe: {len(out['remote_uty']['ws2_32_iat'])} WS2_32 imports")
    print(f"    RemoteUty.exe: {sum(len(v) for v in out['remote_uty']['ws2_32_callers'].values())} WS2_32 call sites")
    print(f"    RemoteUty.exe: {len(out['remote_uty']['port_constants'])} htons call sites with port constants")
    print(f"    RemoteUty.exe: {sum(len(v) for v in out['remote_uty']['setupapi_callers'].values())} SETUPAPI call sites")


if __name__ == "__main__":
    main()
