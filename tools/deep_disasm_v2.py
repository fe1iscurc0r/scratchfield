#!/usr/bin/env python3
"""二阶深度分析：
1. 反汇编 RemoteUty.exe WS2_32 调用点周围代码（socket/bind/recvfrom/sendto/WSAIoctl 等）
2. 反汇编 RemoteUty.exe SETUPAPI 调用点周围代码
3. 反汇编 RadioSch.dll SETUPAPI 调用点周围代码
4. 搜索关键字符串（CommandPort/AudioPort/VID_/Icom）的引用位置
"""
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

import pefile
from capstone import CS_ARCH_X86, CS_MODE_32, CS_OP_IMM, CS_OP_MEM, Cs

UTILITY_DIR = Path(r"d:\my git\RemoteUtility")
RADIO_SCH = UTILITY_DIR / "RadioSch.dll"
REMOTE_UTY = UTILITY_DIR / "RemoteUty.exe"
OUTPUT_DIR  = Path(r"d:\my git\scratchpad\tools\pe_analysis_output")


def build_iat_map(pe):
    iat = {}
    if not hasattr(pe, "DIRECTORY_ENTRY_IMPORT"):
        return iat
    for entry in pe.DIRECTORY_ENTRY_IMPORT:
        dll_name = entry.dll.decode("ascii", errors="replace")
        for imp in entry.imports:
            name = imp.name.decode("ascii", errors="replace") if imp.name else f"ordinal_{imp.ordinal}"
            iat[imp.address] = (dll_name, name)
    return iat


def build_string_xref(pe, filepath):
    raw = filepath.read_bytes()
    str_map = {}
    # ASCII
    for m in re.finditer(rb"[\x20-\x7e]{5,}", raw):
        s = m.group().decode("ascii", errors="replace")
        for section in pe.sections:
            if section.PointerToRawData <= m.start() < section.PointerToRawData + section.SizeOfRawData:
                rva = section.VirtualAddress + (m.start() - section.PointerToRawData)
                if rva not in str_map:
                    str_map[rva] = s
                break
    # UTF-16LE
    for m in re.finditer(rb"(?:[\x20-\x7e]\x00){5,}", raw):
        try:
            s = m.group().decode("utf-16-le")
        except Exception:
            continue
        for section in pe.sections:
            if section.PointerToRawData <= m.start() < section.PointerToRawData + section.SizeOfRawData:
                rva = section.VirtualAddress + (m.start() - section.PointerToRawData)
                if rva not in str_map:
                    str_map[rva] = s
                break
    return str_map


def disasm_around(pe, md, image_base, caller_rva, before=12, after=4):
    """反汇编 caller_rva 附近指令
    before: caller 之前的指令数
    after:  caller 之后的指令数
    """
    # 找 .text 起始
    text_sec = None
    for sec in pe.sections:
        if sec.Name.rstrip(b"\x00").decode("ascii", errors="replace") == ".text":
            text_sec = sec
            break
    if not text_sec:
        return [], None

    # 反汇编 caller 前后 80 字节
    pre_bytes = 80
    start_rva = caller_rva - pre_bytes
    if start_rva < text_sec.VirtualAddress:
        start_rva = text_sec.VirtualAddress
        pre_bytes = caller_rva - text_sec.VirtualAddress
    try:
        data = pe.get_data(start_rva, 200)
    except Exception:
        return [], None

    insns = list(md.disasm(data, image_base + start_rva))
    # 找到 caller 那条指令
    caller_addr = image_base + caller_rva
    caller_idx = None
    for i, ins in enumerate(insns):
        if ins.address == caller_addr:
            caller_idx = i
            break
    if caller_idx is None:
        # 重新线性反汇编到 caller
        return [], None

    start_i = max(0, caller_idx - before)
    end_i   = min(len(insns), caller_idx + after + 1)
    return [
        {
            "addr": hex(ins.address),
            "rva":  hex(ins.address - image_base),
            "mnemonic": ins.mnemonic,
            "op_str":   ins.op_str,
            "bytes":    ins.bytes.hex(),
        }
        for ins in insns[start_i:end_i]
    ], caller_idx


def find_callers_of_iat(pe, md, image_base, target_iat_rvas):
    """找所有调用 IAT 地址的位置"""
    callers = defaultdict(list)
    text_sec = None
    for sec in pe.sections:
        if sec.Name.rstrip(b"\x00").decode("ascii", errors="replace") == ".text":
            text_sec = sec
            break
    if not text_sec:
        return callers

    text_data = pe.get_data(text_sec.VirtualAddress, text_sec.SizeOfRawData)
    text_start_rva = text_sec.VirtualAddress

    for rva in target_iat_rvas:
        target_va = image_base + rva
        # call dword ptr [target_va] = FF 15 <4 bytes LE>
        # jmp dword ptr [target_va] = FF 25 <4 bytes LE>
        for opcode in (b"\xff\x15", b"\xff\x25"):
            pattern = opcode + target_va.to_bytes(4, "little")
            start = 0
            while True:
                idx = text_data.find(pattern, start)
                if idx < 0:
                    break
                caller_rva = text_start_rva + idx
                insns, _ = disasm_around(pe, md, image_base, caller_rva, before=8, after=2)
                callers[rva].append({
                    "caller_rva": hex(caller_rva),
                    "context":    insns,
                })
                start = idx + 1
    return callers


def find_string_xref(pe, md, image_base, str_map, target_strings):
    """找到引用目标字符串的代码位置"""
    target_rvas = []
    for rva, s in str_map.items():
        for target in target_strings:
            if target in s:
                target_rvas.append((rva, s))
                break

    # 在 .text 段中找 push 0xXXXXXXXX，其中 0xXXXXXXXX = image_base + rva
    text_sec = None
    for sec in pe.sections:
        if sec.Name.rstrip(b"\x00").decode("ascii", errors="replace") == ".text":
            text_sec = sec
            break
    if not text_sec:
        return {}

    text_data = pe.get_data(text_sec.VirtualAddress, text_sec.SizeOfRawData)
    text_start_rva = text_sec.VirtualAddress

    result = {}
    for str_rva, str_val in target_rvas:
        target_va = image_base + str_rva
        # push imm32 = 68 <4 bytes LE>
        # mov reg, imm32 = B8+rd <4 bytes LE>  (B8 mov eax, imm32)
        refs = []
        for opcode_byte in (0x68,):  # push
            pattern = bytes([opcode_byte]) + target_va.to_bytes(4, "little")
            start = 0
            while True:
                idx = text_data.find(pattern, start)
                if idx < 0:
                    break
                ref_rva = text_start_rva + idx
                insns, _ = disasm_around(pe, md, image_base, ref_rva, before=4, after=8)
                refs.append({
                    "ref_rva": hex(ref_rva),
                    "context": insns,
                })
                start = idx + 1
        # 同时找 mov reg, imm
        for reg_opcode in (0xB8, 0xB9, 0xBA, 0xBB, 0xBC, 0xBD, 0xBE, 0xBF):
            pattern = bytes([reg_opcode]) + target_va.to_bytes(4, "little")
            start = 0
            while True:
                idx = text_data.find(pattern, start)
                if idx < 0:
                    break
                ref_rva = text_start_rva + idx
                insns, _ = disasm_around(pe, md, image_base, ref_rva, before=2, after=10)
                refs.append({
                    "ref_rva": hex(ref_rva),
                    "context": insns,
                })
                start = idx + 1

        if refs:
            result[str_val] = {
                "str_rva": hex(str_rva),
                "refs":    refs,
            }
    return result


def analyze_pe(filepath, ws2_funcs_to_disasm=None, setupapi_to_disasm=None, str_xrefs_to_find=None, label=""):
    print(f"\n[*] Analyzing {filepath.name} ({label})")
    pe = pefile.PE(str(filepath), fast_load=False)
    md = Cs(CS_ARCH_X86, CS_MODE_32)
    md.detail = True
    image_base = pe.OPTIONAL_HEADER.ImageBase
    iat = build_iat_map(pe)
    str_map = build_string_xref(pe, filepath)

    # 反向：IAT_RVA → (dll, fn, iat_va)
    iat_by_rva = {}
    for addr, (dll, fn) in iat.items():
        iat_by_rva[addr - image_base] = (dll, fn, addr)

    result = {
        "file": filepath.name,
        "image_base": hex(image_base),
        "ws2_calls": {},
        "setupapi_calls": {},
        "string_xrefs": {},
    }

    # WS2_32 调用点反汇编
    if ws2_funcs_to_disasm:
        ws2_target_rvas = []
        for rva, (dll, fn, _) in iat_by_rva.items():
            if dll.upper() == "WS2_32.DLL" and fn in ws2_funcs_to_disasm:
                ws2_target_rvas.append(rva)
        callers = find_callers_of_iat(pe, md, image_base, ws2_target_rvas)
        for rva in ws2_target_rvas:
            fn = iat_by_rva[rva][1]
            result["ws2_calls"][fn] = callers.get(rva, [])

    # SETUPAPI 调用点反汇编
    if setupapi_to_disasm:
        setupapi_target_rvas = []
        for rva, (dll, fn, _) in iat_by_rva.items():
            if dll.upper() == "SETUPAPI.DLL" and fn in setupapi_to_disasm:
                setupapi_target_rvas.append(rva)
        callers = find_callers_of_iat(pe, md, image_base, setupapi_target_rvas)
        for rva in setupapi_target_rvas:
            fn = iat_by_rva[rva][1]
            result["setupapi_calls"][fn] = callers.get(rva, [])

    # 字符串引用
    if str_xrefs_to_find:
        result["string_xrefs"] = find_string_xref(pe, md, image_base, str_map, str_xrefs_to_find)

    pe.close()
    return result


def main():
    out = {}

    # RemoteUty.exe: 反汇编 socket/bind/recvfrom/sendto/WSAIoctl/setsockopt/getsockname 调用点周围
    # 这是 CUdp::open / CUdp::recv 的核心实现
    out["remote_uty_net"] = analyze_pe(
        REMOTE_UTY,
        ws2_funcs_to_disasm={"socket", "bind", "recvfrom", "sendto", "WSAIoctl",
                             "setsockopt", "getsockname", "htons", "WSAStartup",
                             "gethostbyname", "inet_ntoa", "ntohs", "ntohl", "htonl"},
        setupapi_to_disasm={"SetupDiGetClassDevsA", "SetupDiEnumDeviceInterfaces",
                            "SetupDiGetDeviceInterfaceDetailA",
                            "SetupDiDestroyDeviceInfoList"},
        str_xrefs_to_find=[
            "CommandPort", "SerialPort", "AudioPort",
            "\\\\.\ICOM_SERIAL", "ICOM_VAUDIO",
            "SYSTEM\\CurrentControlSet\\Services\\icom_vaudio",
            "SOFTWARE\\Icom\\RS-BA1\\RemoteUty",
            "SOFTWARE\\Icom\\Remote Utility",
            "icom_vaudio.sys", "icom_vserial.sys",
            "\\Device\\IcomVSerial",
            "VAudioDevice",
            "CUdp::open", "CUdp::recv",
            "CUDPCtrl::ExOpen", "CUDPCtrl2::ExOpen",
            "baud=%d parity",
            "MUTEX_SERVER_PORTLIST",
            "FTCP", "tcPW",
        ],
        label="WS2_32 调用点 + 字符串引用",
    )

    # RadioSch.dll: 反汇编 SETUPAPI 调用点周围代码
    out["radio_sch_setupapi"] = analyze_pe(
        RADIO_SCH,
        setupapi_to_disasm={"SetupDiGetClassDevsA", "SetupDiEnumDeviceInfo",
                            "SetupDiDestroyDeviceInfoList", "SetupDiOpenDevRegKey",
                            "CM_Get_Child", "CM_Get_Device_IDA", "CM_Get_Parent",
                            "CM_Get_Sibling", "SetupDiGetDeviceInstanceIdA"},
        str_xrefs_to_find=[
            "VIDPID", "VID_",
            "SYSTEM\\CurrentControlSet\\Enum\\",
            "Icom Inc.",
            "(C) 2010-2020 Icom Inc.",
        ],
        label="SETUPAPI + USB 字符串引用",
    )

    out_path = OUTPUT_DIR / "deep_analysis_v2.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, ensure_ascii=False)
    print(f"\n[+] Wrote {out_path}")


if __name__ == "__main__":
    main()
