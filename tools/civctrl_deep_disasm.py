#!/usr/bin/env python
"""
CivCtrl.dll 深度静态分析脚本
- pefile 解析 PE
- capstone 反汇编导出函数(50条) + 关键内部方法(120条)
- 扫描 CI-V 帧字节序列 (FE FE ... FD)
- 定位串口/mailslot 字符串的 xref
- 输出 JSON 中间结果
"""
import json
import os
import struct
import sys

import pefile
from capstone import CS_ARCH_X86, CS_MODE_32, CS_OP_IMM, CS_OP_MEM, Cs

DLL_PATH = r"d:\my git\RS-BA1\RemoteController\CivCtrl.dll"
OUT_JSON = r"d:\my git\scratchpad\tools\pe_analysis_output\CivCtrl_deep_disasm.json"
IMAGE_BASE = 0x400000

# 已从初版分析中提取的内部方法地址 (VA) - setter/getter 区
INTERNAL_METHODS = [
    ("HandleResolver_0x404910",      0x404910),
    ("HandleRelease_0x40498c",       0x40498c),
    ("CIVDriver_dt0x401e28_civClose", 0x401e28),
    ("CIVDriver_0x402190_civSend",   0x402190),
    ("CIVDriver_0x402624_civRecv",   0x402624),
    ("impl_0x4025ec_GetRecvSize",    0x4025ec),
    ("impl_0x401c0c_GetConType",     0x401c0c),
    ("impl_0x401b50_GetOthAnsCount", 0x401b50),
    ("impl_0x401bc4_GetRxByteCount", 0x401bc4),
    ("impl_0x401aa0_IsSendEnable",   0x401aa0),
    ("impl_0x401b40_ResetOthAnsCount", 0x401b40),
    ("impl_0x401bb4_ResetRxByteCount", 0x401bb4),
    ("impl_0x401a80_SetAddPreamble", 0x401a80),
    ("impl_0x401a40_SetAddress",     0x401a40),
    ("impl_0x401a90_SetCivTot",      0x401a90),
    ("impl_0x401bd4_SetConType",     0x401bd4),
    ("impl_0x401b14_SetRetryFA",     0x401b14),
    ("impl_0x401b2c_SetWaitTime",    0x401b2c),
]

# 通过 string xref 新发现的状态机/IO 函数入口 (VA)
STATE_MACHINE_FUNCS = [
    ("ctor_mailslot_0x401580",       0x401580),  # 引用 civsend/civrecv mailslot
    ("civOpen_impl_0x401c30",        0x401c30),  # 引用 COM%d, baud=, civOpen()
    ("civReset_0x402008",            0x402008),  # civOpen 末尾调用
    ("state_IDLE_0x402088",          0x402088),  # 引用 --> IDLE
    ("civSendSub_0x402360",          0x402360),  # 引用 civSendSub(), -->ECHO, -->ANSWER
    ("ReadByteLoop_0x402708",        0x402708),  # 引用 ReadFile %02X
    ("civCtrlBranch_0x402b94",       0x402b94),  # 引用 civCtrlBranch(), recv transceive
    ("civAnalyze_0x402d44",          0x402d44),  # 引用 civAnalyze(), ECHO OK!!!, status=%d
    ("civAnsBranch_0x4030f0",        0x4030f0),  # 引用 civAnsBranch()
    ("AddRecvData_0x403224",         0x403224),  # 引用 AddRecvData
    ("jam_idle_handler_0x403358",    0x403358),  # 引用 JAM CIVTOT, IDLE SendRetry
    ("civRetry_0x4037ac",            0x4037ac),  # 引用 civRetry(), -->JAM
    ("civError_0x4038b0",            0x4038b0),  # 引用 civError()
    ("SendRecvThread_0x403968",      0x403968),  # CreateThread 的线程函数
]

# IAT thunk 地址 (从 civOpen 反汇编中提取的 call 目标)
IAT_THUNKS = [
    ("thunk_0x41bba2_CreateFileA?",    0x41bba2),
    ("thunk_0x41bb90_BuildCommDCBA?",  0x41bb90),
    ("thunk_0x41bcc8_SetCommState?",   0x41bcc8),
    ("thunk_0x41bcce_SetCommTimeouts?",0x41bcce),
    ("thunk_0x41bbc6_SetupComm?",      0x41bbc6),
    ("thunk_0x419e94_CreateThread?",   0x419e94),
    ("thunk_0x41bd48_CreateEvent?",    0x41bd48),
    ("thunk_0x41347c_wsprintfA?",      0x41347c),
    ("thunk_0x410c88_memset?",         0x410c88),
]

# 关键字符串 (用于 xref 搜索)
KEY_STRINGS = [
    r"\\.\mailslot\civsend",
    r"\\.\mailslot\civrecv",
    r"\\.\COM%d",
    "baud=%d parity=N data=8 stop=1",
    "CIVDriver::civOpen()",
    "CIVDriver::civSend()",
    "CIVDriver::civRecv",
    "CIVDriver::civAnalyze()",
    "CIVDriver::civAnsBranch()",
    "CIVDriver::SendRecvThread",
    "CIVDriver::civSendSub()",
    "CIVDriver::AddRecvData",
    "CIVDriver::civError()",
    "CIVDriver::civRetry()",
    "--> IDLE",
    "-->ECHO",
    "-->ANSWER",
    "-->JAM",
    "send data...",
    "WriteFile SendSlot",
    "ReadFile RecvSlot",
    "ReadFile %02X",
    "ECHO OK!!!",
    "ECHO NG!!!",
    "recv transceive",
    "CIVDriver::civCtrlBranch()",
    "civAnalyze status = %d, LenTx = %d, LenRx = %d",
    "  Status = JAM CIVTOT -> error",
    "  Status = IDLE SendRetry!!",
]


def rva_to_offset(pe, rva):
    try:
        return pe.get_offset_from_rva(rva)
    except Exception:
        return None


def va_to_rva(va):
    return va - IMAGE_BASE


def disasm_at(pe, md, va, count):
    """从指定 VA 反汇编 count 条指令"""
    rva = va_to_rva(va)
    off = rva_to_offset(pe, rva)
    if off is None:
        return []
    # 读取足够字节 (按 16 字节/指令估算)
    size = count * 16 + 64
    data = pe.get_data(rva, size)
    insns = []
    for ins in md.disasm(data, va):
        insns.append({
            "addr": ins.address,
            "bytes": ins.bytes.hex(),
            "mnemonic": ins.mnemonic,
            "op_str": ins.op_str,
        })
        if len(insns) >= count:
            break
    return insns


def scan_civ_frames(pe):
    """在整个镜像中扫描 CI-V 帧: FE FE [^FE/FD]+ FD"""
    results = []
    # 扫描所有可读区段
    for sec in pe.sections:
        name = sec.Name.rstrip(b'\x00').decode('ascii', errors='ignore')
        if name not in (".text", ".data", ".rdata", ".idata"):
            continue
        rva = sec.VirtualAddress
        size = sec.SizeOfRawData
        try:
            data = pe.get_data(rva, size)
        except Exception:
            continue
        i = 0
        n = len(data)
        while i < n - 3:
            # 找 FE FE
            if data[i] == 0xFE and data[i+1] == 0xFE:
                # 找下一个 FD
                j = i + 2
                ok = True
                while j < n and data[j] != 0xFD:
                    if data[j] == 0xFE:
                        # 中间出现 FE: 可能是 preamble 重复, 跳过当前
                        # 也可能是下一帧起点, 试着从 j 继续
                        break
                    j += 1
                if j < n and data[j] == 0xFD and j - i + 1 <= 32:
                    frame = data[i:j+1]
                    # 长度合理 (5..32), 且中间无 FE
                    if 0xFE not in frame[2:-1]:
                        results.append({
                            "section": name,
                            "rva": rva + i,
                            "va": IMAGE_BASE + rva + i,
                            "length": len(frame),
                            "hex": frame.hex(),
                            "ascii": "".join(chr(b) if 0x20 <= b < 0x7f else "." for b in frame),
                        })
                        i = j + 1
                        continue
                i += 1
            else:
                i += 1
    # 去重 (同一 VA 只保留一次)
    seen = set()
    deduped = []
    for r in results:
        if r["va"] not in seen:
            seen.add(r["va"])
            deduped.append(r)
    return deduped


def scan_imm_fe_fd(pe, md):
    """扫描 .text 中使用立即数 0xFE / 0xFD 的指令 (CI-V 帧构造痕迹)"""
    results = []
    text_sec = None
    for sec in pe.sections:
        if sec.Name.startswith(b".text"):
            text_sec = sec
            break
    if not text_sec:
        return results
    rva = text_sec.VirtualAddress
    size = text_sec.SizeOfRawData
    data = pe.get_data(rva, size)
    base_va = IMAGE_BASE + rva
    # 线性扫描反汇编 (从函数边界对齐, 简化: 每 16 字节起点尝试)
    # 更准确: 用 capstone 从段头开始连续反汇编
    pos = 0
    while pos < len(data) - 16:
        chunk = data[pos:pos+16]
        try:
            for ins in md.disasm(chunk, base_va + pos, count=1):
                # 检查操作数是否含 0xFE 或 0xFD 立即数
                for op in ins.operands:
                    if op.type == CS_OP_IMM and op.imm in (0xFE, 0xFD):
                        # 排除明显的 jcc/loop (0xFE FE 是 jne +2 之类, 但单字节 0xFE 在 cmp/test/mov 中才是我们要的)
                        if ins.mnemonic in ("mov", "cmp", "test", "and", "or", "xor", "add", "sub", "push", "adc", "sbb"):
                            # 找最近的函数起始
                            fstart = find_func_start_for_xref(pe, md, ins.address)
                            results.append({
                                "va": hex(ins.address),
                                "mnemonic": ins.mnemonic,
                                "op_str": ins.op_str,
                                "imm": hex(op.imm),
                                "func_start": hex(fstart) if fstart else None,
                            })
                            break
                break
        except Exception:
            pass
        pos += 1
    return results


def scan_imm_xref_in_text(pe, md, target_va):
    """在 .text 中扫描 push imm32 / mov reg,imm32 / lea 等指向 target_va 的指令"""
    xrefs = []
    text_sec = None
    for sec in pe.sections:
        if sec.Name.startswith(b".text"):
            text_sec = sec
            break
    if not text_sec:
        return xrefs
    rva = text_sec.VirtualAddress
    size = text_sec.SizeOfRawData
    data = pe.get_data(rva, size)
    base_va = IMAGE_BASE + rva
    # 扫描 4 字节立即数 == target_va
    target_bytes = struct.pack("<I", target_va)
    pos = 0
    while True:
        idx = data.find(target_bytes, pos)
        if idx < 0:
            break
        xrefs.append({
            "va": base_va + idx,
            "rva": rva + idx,
            "context_offset": idx,
        })
        pos = idx + 1
    return xrefs


def find_string_va(pe, needle):
    """在所有区段中查找 ASCII 字符串的 VA"""
    needle_b = needle.encode("ascii") if isinstance(needle, str) else needle
    for sec in pe.sections:
        rva = sec.VirtualAddress
        size = sec.SizeOfRawData
        try:
            data = pe.get_data(rva, size)
        except Exception:
            continue
        idx = data.find(needle_b)
        if idx >= 0:
            return IMAGE_BASE + rva + idx, rva + idx, sec.Name.rstrip(b'\x00').decode('ascii', errors='ignore')
    return None, None, None


def find_func_start_for_xref(pe, md, xref_va, max_back=0x200):
    """
    从 xref 向前找函数起始 (push ebp; mov ebp,esp 或 push ebp; mov ebp,esp; sub/add esp,xx)
    简化: 找最近的 55 8B EC 序列
    """
    rva = va_to_rva(xref_va)
    off = rva_to_offset(pe, rva)
    if off is None or off < max_back:
        return None
    data = pe.get_data(rva - max_back, max_back)
    # 从后向前找 55 8B EC
    for i in range(max_back - 3, -1, -1):
        if data[i] == 0x55 and data[i+1] == 0x8B and data[i+2] == 0xEC:
            return IMAGE_BASE + rva - max_back + i
    return None


def extract_imm_from_insn(insn):
    """从 capstone 指令中提取立即数操作数"""
    if not insn.operands:
        return None
    for op in insn.operands:
        if op.type == CS_OP_IMM:
            return op.imm
    return None


def main():
    pe = pefile.PE(DLL_PATH, fast_load=False)
    md = Cs(CS_ARCH_X86, CS_MODE_32)
    md.detail = True

    out = {
        "file": os.path.basename(DLL_PATH),
        "image_base": hex(IMAGE_BASE),
        "exports_deep": [],
        "internal_methods": [],
        "state_machine_funcs": [],
        "iat_thunks": [],
        "civ_frames": [],
        "imm_fe_fd_usage": [],
        "string_xrefs": [],
        "serial_config": {},
    }

    # 1. 反汇编所有导出函数 (前 50 条)
    for exp in pe.DIRECTORY_ENTRY_EXPORT.symbols:
        name = exp.name.decode() if exp.name else f"ord_{exp.ordinal}"
        rva = exp.address
        va = IMAGE_BASE + rva
        insns = disasm_at(pe, md, va, 50)
        out["exports_deep"].append({
            "name": name,
            "ordinal": exp.ordinal,
            "rva": hex(rva),
            "va": hex(va),
            "instructions": insns,
        })

    # 2. 反汇编关键内部方法 (前 120 条)
    for label, va in INTERNAL_METHODS:
        insns = disasm_at(pe, md, va, 120)
        out["internal_methods"].append({
            "label": label,
            "va": hex(va),
            "instructions": insns,
        })

    # 2b. 反汇编状态机/IO 函数 (前 250 条 - 这些函数较长)
    for label, va in STATE_MACHINE_FUNCS:
        insns = disasm_at(pe, md, va, 250)
        out["state_machine_funcs"].append({
            "label": label,
            "va": hex(va),
            "instructions": insns,
        })

    # 2c. 反汇编 IAT thunk (前 5 条 - jmp dword ptr [iat])
    for label, va in IAT_THUNKS:
        insns = disasm_at(pe, md, va, 5)
        out["iat_thunks"].append({
            "label": label,
            "va": hex(va),
            "instructions": insns,
        })

    # 3. 扫描 CI-V 帧
    out["civ_frames"] = scan_civ_frames(pe)

    # 3b. 扫描立即数 0xFE / 0xFD 的使用 (CI-V 帧构造痕迹)
    out["imm_fe_fd_usage"] = scan_imm_fe_fd(pe, md)

    # 4. 字符串 xref
    for s in KEY_STRINGS:
        sva, srva, sec = find_string_va(pe, s)
        if sva is None:
            out["string_xrefs"].append({"string": s, "found": False})
            continue
        xrefs = scan_imm_xref_in_text(pe, md, sva)
        # 对每个 xref 找最近的函数起始
        enriched = []
        for x in xrefs[:8]:  # 限制前 8 个
            fstart = find_func_start_for_xref(pe, md, x["va"])
            enriched.append({
                "xref_va": hex(x["va"]),
                "func_start": hex(fstart) if fstart else None,
            })
        out["string_xrefs"].append({
            "string": s,
            "found": True,
            "string_va": hex(sva),
            "string_section": sec,
            "xref_count": len(xrefs),
            "xrefs": enriched,
        })

    # 5. 串口配置深度分析: 找 baud= 字符串 xref 的函数, 反汇编该函数
    baud_sva, _, _ = find_string_va(pe, "baud=%d parity=N data=8 stop=1")
    if baud_sva:
        baud_xrefs = scan_imm_xref_in_text(pe, md, baud_sva)
        if baud_xrefs:
            fstart = find_func_start_for_xref(pe, md, baud_xrefs[0]["va"])
            if fstart:
                insns = disasm_at(pe, md, fstart, 200)
                out["serial_config"] = {
                    "baud_string_va": hex(baud_sva),
                    "xref_va": hex(baud_xrefs[0]["va"]),
                    "func_start": hex(fstart),
                    "func_disasm": insns,
                }

    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)

    # 控制台摘要
    print(f"[+] Exports deep: {len(out['exports_deep'])}")
    print(f"[+] Internal methods: {len(out['internal_methods'])}")
    print(f"[+] State machine funcs: {len(out['state_machine_funcs'])}")
    print(f"[+] IAT thunks: {len(out['iat_thunks'])}")
    print(f"[+] CI-V frames found: {len(out['civ_frames'])}")
    print(f"[+] Imm 0xFE/0xFD usage: {len(out['imm_fe_fd_usage'])}")
    print(f"[+] String xrefs: {sum(1 for x in out['string_xrefs'] if x.get('found'))}/{len(KEY_STRINGS)}")
    print(f"[+] Serial config func: {out['serial_config'].get('func_start', 'N/A')}")
    print(f"[+] Output: {OUT_JSON}")


if __name__ == "__main__":
    main()
