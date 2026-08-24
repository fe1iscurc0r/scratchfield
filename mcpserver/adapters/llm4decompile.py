"""LLM4Decompile MCP 适配层（二进制反编译，靶子 C）。

上游: albertan017/LLM4Decompile (MIT + DeepSeek License)
源码已在本仓库: mod/sources/packages/extracted/github_sweep/LLM4Decompile/
  注：该目录不在 vendor/top5/ 下，inject_vendor_path 无法注入，故本 adapter **自包含**，
      不 import LLM4Decompile 仓库的 Python 模块，而是按 README 的 Quick Start 直接实现
      反编译 pipeline（objdump 反汇编 → 取函数 → 提示词 → transformers 生成 C）。

依赖（真实机器上需具备）：
- objdump（GNU binutils，Windows 可用 llvm-objdump 或 x86_64-w64-mingw32-objdump）
- transformers + torch（HF 模型推理）
- 模型：LLM4Binary/llm4decompile-1.3b-v1.5（显存紧首选）~ 6.7b-v2（Ghidra 精炼，需更大显存）
- 可选：pefile（PE 头解析，提取 magic 字节，供 RS-BA1 场景）

退化策略：
- healthcheck 探测 torch/transformers + 目标模型是否在 HF 缓存 → 缺则返回 False，门禁自动跳过
- pe_metadata 不依赖 LLM，只要 pefile 或手工解析即可工作（Ollama/模型未就绪也能用）
"""
from __future__ import annotations

import logging
import os
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any

from mcpserver.adapters._common import register_capability_safe

logger = logging.getLogger(__name__)

# 目标模型（默认取 1.3b-v1.5，显存友好；可用 env 覆盖）
_DEFAULT_MODEL = os.environ.get("LLM4DECOMPILE_MODEL", "LLM4Binary/llm4decompile-1.3b-v1.5")
_OPT_LEVELS = ("O0", "O1", "O2", "O3")

CAPABILITY: dict = {
    "name": "llm4decompile",
    "displayName": "LLM 反编译",
    "description": "基于 LLM4Decompile 将二进制汇编反编译为可读 C 代码；附带 PE 元数据/magic 提取供逆向分析。",
    "version": "1.0",
    "license": "MIT",
    "vendor": "albertan017/LLM4Decompile",
    "degradation_mode": "skip-if-model-missing;pe-metadata-still-available",
    "_from_adapter": "llm4decompile",
}


# =====================================================================
# 依赖探测
# =====================================================================
def _find_objdump() -> str | None:
    """在 PATH 中查找可用的 objdump（含 llvm-objdump / mingw 变体）。"""
    for name in ("objdump", "llvm-objdump", "x86_64-w64-mingw32-objdump"):
        p = shutil.which(name)
        if p:
            return name
    return None


def _model_available(model_id: str) -> bool:
    """检查 HF 模型是否已缓存到本地（避免启动即联网下载）。"""
    import huggingface_hub
    try:
        # filename 为必需参数；命中返回路径，仓库在缓存中但缺文件返回 False，仓库不存在返回 None
        return bool(huggingface_hub.try_to_load_from_cache(model_id, "config.json"))
    except Exception:
        return False


def healthcheck() -> bool:
    """LLM4Decompile 健康检查。

    必须条件：
    - torch/transformers 可 import
    - 目标模型已缓存（HF cache）或环境变量显式强开
    """
    try:
        import torch  # noqa: F401
        import transformers  # noqa: F401
    except Exception as e:
        logger.warning("[adapter:llm4decompile] 缺 torch/transformers: %s，跳过", e)
        return False
    if os.environ.get("LLM4DECOMPILE_FORCE", "0").strip().lower() in ("1", "true", "yes"):
        return True
    try:
        available = _model_available(_DEFAULT_MODEL)
    except Exception as e:
        logger.warning("[adapter:llm4decompile] 模型探测失败: %s，跳过", e)
        return False
    if not available:
        logger.warning(
            "[adapter:llm4decompile] 模型 %s 未缓存（需 ollama/HF 拉取），跳过",
            _DEFAULT_MODEL,
        )
        return False
    return True


# =====================================================================
# 反汇编（objdump 优先，缺失时 capstone 兜底——Windows 无 binutils 场景）
# =====================================================================
def _capstone_text_section(path: Path) -> tuple[int, bytes]:
    """用 pefile 定位 PE 的 .text 节并返回 (虚拟地址, 节数据)。

    objdump 缺失（Windows）时的兜底路径；只取 .text 前 32KB，
    防止整段反汇编后 prompt 超上下文。
    """
    try:
        import pefile  # type: ignore

        pe = pefile.PE(str(path), fast_load=True)
        for s in pe.sections:
            name = s.Name.decode(errors="replace").rstrip("\x00")
            if name.lower() in (".text", "text"):
                data = s.get_data()
                return s.VirtualAddress, data[:0x8000]
        raise ValueError("PE 中未找到 .text 节")
    except ImportError as e:
        raise RuntimeError("capstone 兜底路径需要 pefile（pip install pefile）") from e


def _disassemble_capstone(path: Path, arch: str, opt_level: str) -> str:
    """capstone 反汇编 .text 段生成 prompt（无符号信息，函数级切分不可用）。"""
    from capstone import CS_ARCH_X86, CS_MODE_32, CS_MODE_64, Cs

    vaddr, data = _capstone_text_section(path)
    mode = CS_MODE_32 if arch.lower() in ("x86", "i386") else CS_MODE_64
    md = Cs(CS_ARCH_X86, mode)
    # MSVC 编译产物 .text 开头通常是 int3/nop 对齐填充，对反编译无信息量，
    # 跳过连续填充直到第一条真实指令（最多跳 1KB）
    _PADDING = {"int3", "nop"}
    skipped = 0
    for insn in md.disasm(data, vaddr):
        if skipped < 0x400 and insn.mnemonic in _PADDING:
            skipped += insn.size
            continue
        break
    lines: list[str] = []
    for insn in md.disasm(data[skipped:], vaddr + skipped):
        # 训练数据是 objdump 无地址列格式（README asm_clean），
        # 带地址列会让模型退化成重复模式输出
        lines.append(f"{insn.mnemonic}\t{insn.op_str}")
        if len(lines) >= 500:  # llm4decompile-1.3b 上下文 4096，防 prompt 超限
            break
    if not lines:
        raise RuntimeError("capstone 未能反汇编出任何指令（.text 节可能为空/加壳）")
    # 官方 prompt 模板（evaluation/run_evaluation_llm4decompile.py）：
    # "# This is the assembly code with {opt} optimization:\n" + asm + "\n# What is the source code?\n"
    return (
        f"# This is the assembly code with {opt_level} optimization:\n"
        + "\n".join(lines).strip()
        + "\n# What is the source code?\n"
    )


# =====================================================================
# 反编译 pipeline（自包含，不依赖 LLM4Decompile 仓库 import）
# =====================================================================
def _disassemble(path: Path, arch: str, func_name: str, opt_level: str) -> str:
    """objdump 反汇编 + 提取单个函数汇编，返回提示词文本。

    Windows 无 objdump 时回退 capstone（无函数符号，整 .text 段）。
    """
    objdump = _find_objdump()
    if objdump is None:
        return _disassemble_capstone(path, arch, opt_level)
    cmd = [objdump, "-d"]
    if arch.lower() in ("x86_64", "amd64", "x64"):
        cmd.append("-M")
        cmd.append("intel")
    cmd.append(str(path))
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"objdump 失败: {proc.stderr[:500]}")
    asm = proc.stdout
    # 提取目标函数段
    marker = f"<{func_name}>:"
    if marker not in asm:
        raise ValueError(f"未在二进制中找到函数 <{func_name}>:")
    segment = marker + asm.split(marker)[-1].split("\n\n")[0]
    lines: list[str] = []
    for raw in segment.splitlines():
        parts = raw.split("\t")
        if len(parts) < 3 and "00" in raw:
            continue
        idx = min(len(parts) - 1, 2)
        cleaned = "\t".join(parts[idx:]).split("#")[0].strip()
        if cleaned:
            lines.append(cleaned)
    prompt = (
        f"# This is the assembly code with {opt_level} optimization:\n"
        + "\n".join(lines).strip()
        + "\n# What is the source code?\n"
    )
    return prompt


def _execute_decompile(prompt: str, max_new_tokens: int, model_id: str) -> str:
    """用 transformers 加载模型并生成 C 代码。"""
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer

    # 设备自适应：CUDA 优先；CPU-only 环境（如 docling 带入的 +cpu 轮子）
    # 用 bfloat16——fp32 实测 384 token 要 26 分钟，bf16 内存减半且
    # 现代 CPU（AVX512_BF16/AMX）矩阵乘显著更快；不支持 bf16 的老 CPU
    # 由 torch 内部回退，不会报错。
    if torch.cuda.is_available():
        device = "cuda"
    else:
        device = "cpu"
    dtype = torch.bfloat16

    tokenizer = AutoTokenizer.from_pretrained(model_id)
    model = AutoModelForCausalLM.from_pretrained(model_id, torch_dtype=dtype).to(device)
    model.eval()
    inputs = tokenizer(prompt, return_tensors="pt").to(model.device)
    with torch.no_grad():
        outputs = model.generate(
            **inputs, max_new_tokens=max_new_tokens, do_sample=False
        )
    raw = tokenizer.decode(outputs[0][len(inputs[0]):], skip_special_tokens=True)
    # llm4decompile-1.3b 词表基于 CodeLlama，生成里会夹带 Ġ(空格)/Ċ(换行)
    # 等 sentencepiece 风格特殊字符，后处理还原成真实空白，保证输出可直接编译
    return raw.replace("\u0120", " ").replace("\u010a", "\n").strip()


# =====================================================================
# PE 元数据（不依赖 LLM，RS-BA1 场景可用）
# =====================================================================
def _pe_metadata(path: Path) -> dict:
    """提取 PE 头信息与 magic 字节（优先 pefile，退化为手工解析）。"""
    try:
        import pefile  # type: ignore
        pe = pefile.PE(str(path))
        sections = [
            {
                "name": s.Name.decode(errors="replace").rstrip("\x00"),
                "virtual_address": s.VirtualAddress,
                "virtual_size": s.Misc_VirtualSize,
                "characteristics": s.Characteristics,
            }
            for s in pe.sections
        ]
        return {
            "ok": True,
            "machine": pe.FILE_HEADER.Machine,
            "timestamp": pe.FILE_HEADER.TimeDateStamp,
            "sections": sections,
            "entry_point": pe.OPTIONAL_HEADER.AddressOfEntryPoint,
        }
    except ImportError:
        pass
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}
    # 手工解析：MZ + PE signature + 节表
    raw = path.read_bytes()
    if raw[:2] != b"MZ":
        return {"ok": False, "error": "非 PE 文件（无 MZ 头）"}
    pe_off = int.from_bytes(raw[0x3C:0x40], "little")
    if raw[pe_off:pe_off + 4] != b"PE\x00\x00":
        return {"ok": False, "error": "PE signature 缺失"}
    machine = int.from_bytes(raw[pe_off + 4:pe_off + 6], "little")
    num_sections = int.from_bytes(raw[pe_off + 6:pe_off + 8], "little")
    opt_size = int.from_bytes(raw[pe_off + 20:pe_off + 22], "little")
    section_table = pe_off + 24 + opt_size
    sections = []
    for i in range(num_sections):
        off = section_table + i * 40
        name = raw[off:off + 8].decode(errors="replace").rstrip("\x00")
        vsize = int.from_bytes(raw[off + 8:off + 12], "little")
        vaddr = int.from_bytes(raw[off + 12:off + 16], "little")
        sections.append({"name": name, "virtual_address": vaddr, "virtual_size": vsize})
    return {
        "ok": True,
        "machine": machine,
        "num_sections": num_sections,
        "sections": sections,
        "note": "手工解析（pefile 未安装）",
    }


# =====================================================================
# 注册
# =====================================================================
def register(mcp_server: Any, mcp_registry: Any = None) -> None:
    """注册反编译相关工具。"""

    async def decompile_binary(
        path: str,
        func_name: str = "main",
        arch: str = "x86_64",
        opt_level: str = "O0",
        max_new_tokens: int = 2048,
        model_id: str = _DEFAULT_MODEL,
    ) -> dict:
        """反编译二进制中的单个函数，返回可再编译的 C 代码。

        Args:
            path: 二进制文件绝对路径
            func_name: 目标函数名（如 main / sub_401000）
            arch: 架构（x86 / x86_64 / amd64）
            opt_level: 编译优化级别 O0-O3（影响 LLM 提示措辞）
            max_new_tokens: 生成上限
            model_id: HF 模型 id（默认 1.3b-v1.5）
        """
        # fail-fast：opt_level 直接进 prompt 措辞，静默回落 O0 会误导模型输出，
        # 不如拒绝让调用方修参数
        if opt_level.upper() not in _OPT_LEVELS:
            return {
                "ok": False,
                "error": f"非法优化级别 {opt_level!r}，可选: {'/'.join(_OPT_LEVELS)}",
            }
        try:
            src = Path(path).resolve(strict=True)
            if not src.is_file():
                return {"ok": False, "error": f"路径不是文件: {path}"}
            t0 = time.time()
            prompt = _disassemble(src, arch, func_name, opt_level.upper())
            c_code = _execute_decompile(prompt, max_new_tokens, model_id)
            return {
                "ok": True,
                "c_code": c_code,
                "func_name": func_name,
                "arch": arch,
                "opt_level": opt_level.upper(),
                "model": model_id,
                "elapsed_sec": round(time.time() - t0, 2),
            }
        except Exception as e:
            return {"ok": False, "error": f"{type(e).__name__}: {e}"}

    async def pe_metadata(path: str) -> dict:
        """提取 PE 文件头信息与 magic 字节（反编译前置/快速标识，无需 LLM）。

        Args:
            path: PE/DLL/EXE 绝对路径
        """
        try:
            src = Path(path).resolve(strict=True)
            if not src.is_file():
                return {"ok": False, "error": f"路径不是文件: {path}"}
            return _pe_metadata(src)
        except Exception as e:
            return {"ok": False, "error": f"{type(e).__name__}: {e}"}

    async def decompile_status() -> dict:
        """LLM4Decompile 运行状态（模型/objdump/依赖就绪情况）。"""
        deps: dict[str, Any] = {}
        try:
            import torch
            deps["torch"] = torch.__version__
        except Exception as e:
            deps["torch"] = f"missing ({e})"
        try:
            import transformers
            deps["transformers"] = transformers.__version__
        except Exception as e:
            deps["transformers"] = f"missing ({e})"
        from importlib.util import find_spec
        deps["pefile"] = "yes" if find_spec("pefile") else "no"
        deps["objdump"] = _find_objdump() or "missing"
        try:
            deps["model_cached"] = _model_available(_DEFAULT_MODEL)
        except Exception as e:
            deps["model_cached"] = f"check-failed ({e})"
        return {"ok": True, "model": _DEFAULT_MODEL, "dependencies": deps}

    if hasattr(mcp_server, "add_tool"):
        mcp_server.add_tool(decompile_binary, name="decompile_binary")
        mcp_server.add_tool(pe_metadata, name="pe_metadata")
        mcp_server.add_tool(decompile_status, name="decompile_status")

    register_capability_safe(mcp_registry, CAPABILITY)