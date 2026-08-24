#!/usr/bin/env python3
"""RS-BA1 PE 全量静态分析脚本

对 RemoteController + RemoteUtility 全部 PE 文件做：
1. PE 头/区段/导入表/导出表/资源段解析
2. capstone 反汇编导出函数入口
3. 字符串提取（ASCII + UTF-16LE）
4. 交叉引用分析（DLL 间调用关系）
"""

import json
import os
import re
import sys
from collections import defaultdict
from pathlib import Path

import pefile
from capstone import CS_ARCH_X86, CS_MODE_32, CS_MODE_64, Cs

# ── 配置 ──────────────────────────────────────────────
CONTROLLER_DIR = Path(r"d:\my git\RS-BA1\RemoteController")
UTILITY_DIR = Path(r"d:\my git\RemoteUtility")
OUTPUT_DIR = Path(r"d:\my git\scratchpad\tools\pe_analysis_output")

PE_FILES = {
    # RemoteController 层
    "RemoteCtrl.exe":   CONTROLLER_DIR / "RemoteCtrl.exe",
    "CivCtrl.dll":      CONTROLLER_DIR / "CivCtrl.dll",
    "HidCtrl.dll":      CONTROLLER_DIR / "HidCtrl.dll",
    "UtyCtrl.dll":      CONTROLLER_DIR / "UtyCtrl.dll",
    "RS-BA1V2Ck.dll":   CONTROLLER_DIR / "RS-BA1V2Ck.dll",
    # RemoteUtility 层
    "RemoteUty.exe":    UTILITY_DIR / "RemoteUty.exe",
    "RadioSch.dll":     UTILITY_DIR / "RadioSch.dll",
    "UtilityCk.dll":    UTILITY_DIR / "UtilityCk.dll",
    # 语言包
    "english.dll":      UTILITY_DIR / "english.dll",
}


def analyze_pe(filepath: Path) -> dict:
    """对一个 PE 文件做全量静态分析"""
    name = filepath.name
    result = {
        "file": name,
        "path": str(filepath),
        "size_bytes": filepath.stat().st_size,
        "sections": [],
        "imports": [],
        "exports": [],
        "resources": [],
        "strings_ascii": [],
        "strings_unicode": [],
        "entry_point": None,
        "image_base": None,
        "machine": None,
        "subsystem": None,
        "is_dll": False,
        "timestamp": None,
        "compiler": None,
        "disasm_exports": [],
    }

    try:
        pe = pefile.PE(str(filepath), fast_load=False)
    except Exception as e:
        result["error"] = f"PE 解析失败: {e}"
        return result

    # ── 基本头信息 ──
    result["is_dll"] = pe.is_dll()
    result["entry_point"] = hex(pe.OPTIONAL_HEADER.AddressOfEntryPoint)
    result["image_base"] = hex(pe.OPTIONAL_HEADER.ImageBase)
    machine_map = {0x14c: "x86", 0x8664: "x64"}
    result["machine"] = machine_map.get(pe.FILE_HEADER.Machine, hex(pe.FILE_HEADER.Machine))
    result["subsystem"] = pe.OPTIONAL_HEADER.Subsystem
    if hasattr(pe.FILE_HEADER, 'TimeDateStamp'):
        import datetime
        ts = pe.FILE_HEADER.TimeDateStamp
        result["timestamp"] = datetime.datetime.utcfromtimestamp(ts).strftime('%Y-%m-%d %H:%M:%S')

    # 编译器推断
    if hasattr(pe, 'VS_FIXEDFILEINFO'):
        try:
            ffi = pe.VS_FIXEDFILEINFO[0]
            result["compiler"] = f"MSVC {ffi.FileVersionMS >> 16}.{ffi.FileVersionMS & 0xFFFF}"
        except (IndexError, AttributeError):
            pass

    # ── 区段 ──
    for section in pe.sections:
        result["sections"].append({
            "name": section.Name.rstrip(b'\x00').decode('ascii', errors='replace'),
            "vaddr": hex(section.VirtualAddress),
            "vsize": section.Misc_VirtualSize,
            "raw_size": section.SizeOfRawData,
            "entropy": round(section.get_entropy(), 2),
            "characteristics": hex(section.Characteristics),
        })

    # ── 导入表 ──
    if hasattr(pe, 'DIRECTORY_ENTRY_IMPORT'):
        for entry in pe.DIRECTORY_ENTRY_IMPORT:
            dll_name = entry.dll.decode('ascii', errors='replace')
            functions = []
            for imp in entry.imports:
                if imp.name:
                    functions.append(imp.name.decode('ascii', errors='replace'))
                else:
                    functions.append(f"ordinal_{imp.ordinal}")
            result["imports"].append({
                "dll": dll_name,
                "functions": functions,
                "count": len(functions),
            })

    # ── 导出表 ──
    if hasattr(pe, 'DIRECTORY_ENTRY_EXPORT'):
        for exp in pe.DIRECTORY_ENTRY_EXPORT.symbols:
            if exp.name:
                export_name = exp.name.decode('ascii', errors='replace')
            else:
                export_name = f"ordinal_{exp.ordinal}"
            result["exports"].append({
                "name": export_name,
                "ordinal": exp.ordinal,
                "address": hex(pe.OPTIONAL_HEADER.ImageBase + exp.address),
                "rva": hex(exp.address),
            })

    # ── 资源段 ──
    if hasattr(pe, 'DIRECTORY_ENTRY_RESOURCE'):
        def walk_resources(entries, parent_path=""):
            for entry in entries:
                if entry.name is not None:
                    name = str(entry.name) if isinstance(entry.name, bytes) else entry.name.string.decode('utf-8', errors='replace') if hasattr(entry.name, 'string') else str(entry.name)
                else:
                    type_map = {1: "CURSOR", 2: "BITMAP", 3: "ICON", 4: "MENU", 5: "DIALOG",
                                6: "STRING", 7: "FONTDIR", 8: "FONT", 9: "ACCELERATOR",
                                10: "RCDATA", 11: "MESSAGETABLE", 12: "GROUP_CURSOR",
                                14: "GROUP_ICON", 16: "VERSION", 24: "MANIFEST"}
                    name = type_map.get(entry.id, f"type_{entry.id}")
                full_path = f"{parent_path}/{name}" if parent_path else name
                if hasattr(entry, 'directory') and entry.directory:
                    walk_resources(entry.directory.entries, full_path)
                elif hasattr(entry, 'data') and entry.data:
                    result["resources"].append({
                        "type": full_path,
                        "offset": hex(entry.data.struct.OffsetToData),
                        "size": entry.data.struct.Size,
                    })
        try:
            walk_resources(pe.DIRECTORY_ENTRY_RESOURCE.entries)
        except Exception:
            pass

    # ── 字符串提取 ──
    result["strings_ascii"] = extract_strings(pe, filepath, encoding='ascii', min_len=4)
    result["strings_unicode"] = extract_strings(pe, filepath, encoding='utf-16-le', min_len=4)

    # ── capstone 反汇编导出函数入口 ──
    if result["exports"] and result["machine"] == "x86":
        result["disasm_exports"] = disasm_exports(pe, filepath, max_bytes=256)

    pe.close()
    return result


def extract_strings(pe, filepath: Path, encoding: str = 'ascii', min_len: int = 4) -> list:
    """从 PE 文件提取字符串"""
    try:
        raw = filepath.read_bytes()
    except Exception:
        return []

    strings = []
    if encoding == 'ascii':
        pattern = rb'[\x20-\x7e]{%d,}' % min_len
        for m in re.finditer(pattern, raw):
            s = m.group().decode('ascii')
            # 过滤掉无意义字符串
            if len(s.strip()) >= min_len:
                strings.append(s)
    elif encoding == 'utf-16-le':
        pattern = rb'(?:[\x20-\x7e]\x00){%d,}' % min_len
        for m in re.finditer(pattern, raw):
            try:
                s = m.group().decode('utf-16-le')
                if len(s.strip()) >= min_len:
                    strings.append(s)
            except Exception:
                pass

    # 去重 + 按类型分类
    seen = set()
    unique = []
    for s in strings:
        if s not in seen:
            seen.add(s)
            unique.append(s)
    return unique


def disasm_exports(pe, filepath: Path, max_bytes: int = 256) -> list:
    """用 capstone 反汇编导出函数入口前 N 字节"""
    results = []
    is_64 = pe.FILE_HEADER.Machine == 0x8664
    mode = CS_MODE_64 if is_64 else CS_MODE_32
    md = Cs(CS_ARCH_X86, mode)

    image_base = pe.OPTIONAL_HEADER.ImageBase

    for exp in pe.DIRECTORY_ENTRY_EXPORT.symbols:
        if not exp.name:
            continue
        name = exp.name.decode('ascii', errors='replace')
        rva = exp.address

        # 找到所在区段
        try:
            data = pe.get_data(rva, max_bytes)
        except Exception:
            continue

        instructions = []
        count = 0
        for insn in md.disasm(data, image_base + rva):
            instructions.append({
                "address": hex(insn.address),
                "bytes": insn.bytes.hex(),
                "mnemonic": insn.mnemonic,
                "op_str": insn.op_str,
            })
            count += 1
            if count >= 20:  # 每个函数前 20 条指令
                break

        results.append({
            "name": name,
            "rva": hex(rva),
            "instructions": instructions,
        })

    return results


def analyze_cross_references(all_results: dict) -> dict:
    """分析 DLL 间交叉引用"""
    xref = {
        "dll_dependencies": defaultdict(list),
        "shared_apis": defaultdict(list),
        "export_import_map": defaultdict(list),
    }

    # 每个 PE import 了哪些 DLL
    for name, result in all_results.items():
        for imp in result.get("imports", []):
            dll = imp["dll"]
            xref["dll_dependencies"][name].append({
                "imports_from": dll,
                "function_count": imp["count"],
                "functions": imp["functions"],
            })

    # 哪些 export 被谁 import 了
    all_exports = {}
    for name, result in all_results.items():
        for exp in result.get("exports", []):
            all_exports[exp["name"]] = name

    for name, result in all_results.items():
        for imp in result.get("imports", []):
            for fn in imp["functions"]:
                if fn in all_exports and all_exports[fn] != name:
                    xref["export_import_map"][fn].append({
                        "exported_by": all_exports[fn],
                        "imported_by": name,
                    })

    return xref


def classify_strings(strings: list) -> dict:
    """字符串分类（URL/IP/路径/CI-V/串口/网络）"""
    categories = {
        "ci_v_commands": [],
        "serial_port": [],
        "network": [],
        "file_paths": [],
        "registry": [],
        "audio": [],
        "com_ports": [],
        "error_msgs": [],
        "format_strings": [],
        "interesting": [],
    }

    for s in strings:
        sl = s.lower()
        # CI-V 相关
        if any(kw in sl for kw in ['ci-v', 'civ', '0xfe', 'pipe', 'frequency', 'baudrate', 'transceive']):
            categories["ci_v_commands"].append(s)
        # 串口
        elif any(kw in sl for kw in ['com', 'serial', 'baud', 'parity', 'stopbit', 'dtr', 'rts']):
            categories["serial_port"].append(s)
        # 网络
        elif any(kw in sl for kw in ['udp', 'tcp', 'socket', 'listen', 'bind', 'connect', 'port', 'wlan', 'ip_addr', '127.0.0.1', '0.0.0.0']):
            categories["network"].append(s)
        # 文件路径
        elif '\\' in s or '/' in s:
            if len(s) > 3:
                categories["file_paths"].append(s)
        # 注册表
        elif 'registry' in sl or 'hkey' in sl or 'software\\' in sl:
            categories["registry"].append(s)
        # 音频
        elif any(kw in sl for kw in ['wave', 'audio', 'pcm', 'sample', 'codec', 'voice']):
            categories["audio"].append(s)
        # COM 端口
        elif re.match(r'^COM\d+', s):
            categories["com_ports"].append(s)
        # 错误信息
        elif any(kw in sl for kw in ['error', 'fail', 'invalid', 'cannot', 'not found']):
            categories["error_msgs"].append(s)
        # 格式化字符串
        elif '%' in s and len(s) < 100:
            categories["format_strings"].append(s)
        # 有趣的（调试信息、函数名等）
        elif any(kw in sl for kw in ['debug', 'log', 'thread', 'mutex', 'event', 'create', 'open', 'close', 'read', 'write', 'send', 'recv']):
            categories["interesting"].append(s)

    return {k: v for k, v in categories.items() if v}


def generate_markdown(name: str, result: dict, xref: dict) -> str:
    """生成单个 PE 的 markdown 分析报告"""
    md = f"# {name} 静态分析报告\n\n"
    md += f"> 文件大小: {result['size_bytes']:,} bytes | 机器: {result['machine']} | "
    md += f"类型: {'DLL' if result['is_dll'] else 'EXE'} | "
    md += f"入口: {result['entry_point']} | ImageBase: {result['image_base']}\n"
    if result.get('timestamp'):
        md += f"> 编译时间: {result['timestamp']}\n"
    md += "\n---\n\n"

    # 区段
    md += "## 区段\n\n"
    md += "| 名称 | 虚拟地址 | 虚拟大小 | 原始大小 | 熵值 |\n"
    md += "|---|---|---|---|---|\n"
    for s in result["sections"]:
        md += f"| {s['name']} | {s['vaddr']} | {s['vsize']:,} | {s['raw_size']:,} | {s['entropy']} |\n"
    md += "\n"

    # 导入表
    if result["imports"]:
        md += "## 导入表\n\n"
        for imp in result["imports"]:
            md += f"### {imp['dll']} ({imp['count']} 函数)\n\n"
            # 只显示前 30 个，其余省略
            fns = imp["functions"][:30]
            for fn in fns:
                md += f"- `{fn}`\n"
            if len(imp["functions"]) > 30:
                md += f"- ... 其余 {len(imp['functions']) - 30} 个\n"
            md += "\n"

    # 导出表
    if result["exports"]:
        md += "## 导出表\n\n"
        md += "| 名称 | Ordinal | RVA | 虚拟地址 |\n"
        md += "|---|---|---|---|\n"
        for exp in result["exports"]:
            md += f"| `{exp['name']}` | {exp['ordinal']} | {exp['rva']} | {exp['address']} |\n"
        md += "\n"

    # 反汇编
    if result.get("disasm_exports"):
        md += "## 导出函数反汇编（前 20 条指令）\n\n"
        for func in result["disasm_exports"][:10]:  # 前 10 个函数
            md += f"### `{func['name']}` (RVA: {func['rva']})\n\n"
            md += "```asm\n"
            for insn in func["instructions"]:
                md += f"  {insn['address']}:  {insn['mnemonic']}"
                if insn['op_str']:
                    md += f" {insn['op_str']}"
                md += f"  ; {insn['bytes']}\n"
            md += "```\n\n"
        if len(result["disasm_exports"]) > 10:
            md += f"\n> 其余 {len(result['disasm_exports']) - 10} 个函数的反汇编见 JSON 输出\n\n"

    # 字符串分类
    all_strings = result.get("strings_ascii", []) + result.get("strings_unicode", [])
    if all_strings:
        classified = classify_strings(all_strings)
        if classified:
            md += "## 字符串分类\n\n"
            for cat, items in classified.items():
                md += f"### {cat} ({len(items)} 条)\n\n"
                for s in items[:50]:
                    md += f"- `{s}`\n"
                if len(items) > 50:
                    md += f"- ... 其余 {len(items) - 50} 条\n"
                md += "\n"

    # 资源
    if result["resources"]:
        md += f"## 资源段 ({len(result['resources'])} 项)\n\n"
        md += "| 类型 | 偏移 | 大小 |\n"
        md += "|---|---|---|\n"
        for r in result["resources"][:30]:
            md += f"| {r['type']} | {r['offset']} | {r['size']} |\n"
        if len(result["resources"]) > 30:
            md += f"\n> 其余 {len(result['resources']) - 30} 项\n"
        md += "\n"

    # 交叉引用
    deps = xref["dll_dependencies"].get(name, [])
    if deps:
        md += "## DLL 依赖\n\n"
        md += "| 导入自 | 函数数 |\n"
        md += "|---|---|\n"
        for d in deps:
            md += f"| {d['imports_from']} | {d['function_count']} |\n"
        md += "\n"

    return md


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    all_results = {}

    print("=" * 60)
    print("RS-BA1 PE 全量静态分析")
    print("=" * 60)

    for name, filepath in PE_FILES.items():
        if not filepath.exists():
            print(f"  [SKIP] {name} — 文件不存在")
            continue
        print(f"  [ANALYZE] {name} ({filepath.stat().st_size:,} bytes)...", end=" ")
        result = analyze_pe(filepath)
        all_results[name] = result

        # 保存 JSON
        json_path = OUTPUT_DIR / f"{name}.json"
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        print(f"→ {json_path.name}")

    # 交叉引用
    print("\n[CROSS-REF] 分析 DLL 间交叉引用...", end=" ")
    xref = analyze_cross_references(all_results)
    xref_path = OUTPUT_DIR / "cross_references.json"
    with open(xref_path, 'w', encoding='utf-8') as f:
        json.dump({k: dict(v) if isinstance(v, defaultdict) else v for k, v in xref.items()},
                  f, ensure_ascii=False, indent=2)
    print(f"→ {xref_path.name}")

    # 生成 markdown
    print("\n[MARKDOWN] 生成分析报告...", end=" ")
    for name, result in all_results.items():
        md = generate_markdown(name, result, xref)
        md_path = OUTPUT_DIR / f"{name}.md"
        with open(md_path, 'w', encoding='utf-8') as f:
            f.write(md)
    print(f"→ {len(all_results)} 个 .md 文件")

    # 汇总
    print("\n[SUMMARY] 生成汇总...", end=" ")
    summary_path = OUTPUT_DIR / "summary.md"
    with open(summary_path, 'w', encoding='utf-8') as f:
        f.write("# RS-BA1 PE 全量静态分析汇总\n\n")
        f.write("| 文件 | 大小 | 类型 | 机器 | 导出数 | 导入DLL数 | ASCII字符串 | Unicode字符串 |\n")
        f.write("|---|---|---|---|---|---|---|---|\n")
        for name, result in all_results.items():
            f.write(f"| {name} | {result['size_bytes']:,} | "
                    f"{'DLL' if result['is_dll'] else 'EXE'} | "
                    f"{result['machine']} | "
                    f"{len(result['exports'])} | "
                    f"{len(result['imports'])} | "
                    f"{len(result['strings_ascii'])} | "
                    f"{len(result['strings_unicode'])} |\n")
        f.write("\n## DLL 间交叉引用\n\n")
        f.write("| 消费者 | 导入自 | 函数数 |\n")
        f.write("|---|---|---|\n")
        for name, deps in xref["dll_dependencies"].items():
            for d in deps:
                f.write(f"| {name} | {d['imports_from']} | {d['function_count']} |\n")
        f.write("\n## 导出函数 → 被谁导入\n\n")
        f.write("| 函数名 | 导出者 | 导入者 |\n")
        f.write("|---|---|---|\n")
        for fn, refs in xref["export_import_map"].items():
            for r in refs:
                f.write(f"| `{fn}` | {r['exported_by']} | {r['imported_by']} |\n")
    print(f"→ {summary_path.name}")

    print("\n" + "=" * 60)
    print("✅ 全量分析完成")
    print(f"   输出目录: {OUTPUT_DIR}")
    print(f"   JSON: {len(all_results)} 个 | MD: {len(all_results)} 个 | 交叉引用: 1 个")
    print("=" * 60)


if __name__ == "__main__":
    main()
