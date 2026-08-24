"""
LLM4Decompile 推理封装。

对 LLM4Decompile 模型（llama.cpp GGUF）做一层薄封装，提供两条路径：
  A. decompile_binary()   —— 直接反编译 Linux x86_64 ELF 二进制
  B. polish_ghidra_output()—— 将 Ghidra/IDA 伪 C 润色为人类可读 C（RS-BA1 PE 主用）

设计要点：
  - 模型通过 llama-cpp-python 惰性加载（首次调用才加载，避免无模型时启动失败）。
  - 汇编提取优先用系统 objdump，缺失时回退到纯 Python capstone。
  - 反编译 prompt 遵循 LLM4Decompile 官方模板（assembly 在前，模型补全 C 代码）。
"""

from __future__ import annotations

import json
import logging
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger("llm4decompile.inference")


class ModelNotLoadedError(RuntimeError):
    """模型未加载或加载失败时抛出。"""


class LLM4Decompile:
    """LLM4Decompile 模型推理封装。"""

    # LLM4Decompile 官方反编译 prompt 模板
    DECOMPILE_PROMPT = (
        "Below is the assembly code of a Linux x86_64 function "
        "compiled with {opt} optimization.\n"
        "Please decompile it into human-readable C source code.\n\n"
        "[assembly code here]\n\n{assembly}\n\n"
        "Decompiled C code:\n"
    )

    # Ghidra 润色 prompt（路径 B）
    POLISH_PROMPT = (
        "The following is Ghidra's decompilation output of a function "
        "from a Windows binary.\n"
        "{context_line}"
        "Please rewrite it into clean, readable C code with meaningful "
        "variable names and comments.\n\n"
        "[Ghidra pseudo-C here]\n\n{pseudo_c}\n\n"
        "Rewritten C code:\n"
    )

    def __init__(self, model_path: str, n_gpu_layers: int = -1,
                 n_ctx: int = 16384, verbose: bool = False) -> None:
        """
        参数：
          model_path: GGUF 模型文件绝对路径
          n_gpu_layers: GPU 卸载层数，-1 表示全部上 GPU，0 表示纯 CPU
          n_ctx: 上下文窗口大小
          verbose: 是否输出 llama.cpp 调试日志
        """
        self.model_path = model_path
        self.n_gpu_layers = n_gpu_layers
        self.n_ctx = n_ctx
        self.verbose = verbose
        self._model: Optional[Any] = None

    # ------------------------------------------------------------------ #
    # 模型加载
    # ------------------------------------------------------------------ #
    def load(self) -> Any:
        """加载模型（幂等）。返回底层 Llama 实例。"""
        if self._model is not None:
            return self._model
        if not self.model_path or not os.path.exists(self.model_path):
            raise ModelNotLoadedError(
                f"模型文件不存在: {self.model_path!r}（请在 config 中配置 model_path）"
            )
        try:
            from llama_cpp import Llama
        except ImportError as e:  # pragma: no cover - 依赖缺失时的兜底提示
            raise ModelNotLoadedError(
                "缺少 llama-cpp-python 依赖，请先 pip install llama-cpp-python"
            ) from e
        try:
            self._model = Llama(
                model_path=self.model_path,
                n_gpu_layers=self.n_gpu_layers,
                n_ctx=self.n_ctx,
                verbose=self.verbose,
            )
        except Exception as e:
            raise ModelNotLoadedError(f"模型加载失败: {e}") from e
        return self._model

    def is_loaded(self) -> bool:
        return self._model is not None

    # ------------------------------------------------------------------ #
    # 汇编提取
    # ------------------------------------------------------------------ #
    def _extract_assembly_objdump(self, binary_path: str, optimization: str) -> str:
        """用 objdump -d 提取函数汇编（Linux 环境）。"""
        cmd = ["objdump", "-d", "--disassemble-zeroes", binary_path]
        try:
            proc = subprocess.run(
                cmd, capture_output=True, text=True, timeout=60, check=False
            )
        except (OSError, subprocess.TimeoutExpired) as e:
            raise ModelNotLoadedError(f"objdump 执行失败: {e}") from e
        if proc.returncode != 0:
            raise ModelNotLoadedError(
                f"objdump 返回 {proc.returncode}: {proc.stderr[:500]}"
            )
        return proc.stdout

    def _extract_assembly_capstone(self, binary_path: str) -> str:
        """用 Python capstone 提取汇编（跨平台，Windows 无 objdump 时使用）。"""
        try:
            from capstone import Cs, CS_ARCH_X86, CS_MODE_64
            from capstone.x86 import X86_OP_REG, X86_OP_IMM, X86_OP_MEM
        except ImportError as e:  # pragma: no cover
            raise ModelNotLoadedError(
                "Windows 下无 objdump，需要 capstone 提取汇编（pip install capstone）"
            ) from e

        data = Path(binary_path).read_bytes()
        # 尝试定位可执行代码段：简单启发式从 0x1000 偏移开始反汇编
        md = Cs(CS_ARCH_X86, CS_MODE_64)
        lines: list[str] = []
        start = min(0x1000, len(data))
        for insn in md.disasm(data[start:start + 0x20000], start):
            mnem = f"{insn.mnemonic}\t{insn.op_str}".strip()
            lines.append(f"{insn.address:#x}:\t{mnem}")
        if not lines:
            raise ModelNotLoadedError("capstone 未能反汇编出任何指令")
        return "\n".join(lines[:2000])  # 截断防止超长

    def _get_assembly(self, binary_path: str, optimization: str) -> str:
        """提取汇编：优先 objdump，缺失时回退 capstone。"""
        if shutil.which("objdump"):
            return self._extract_assembly_objdump(binary_path, optimization)
        return self._extract_assembly_capstone(binary_path)

    # ------------------------------------------------------------------ #
    # 推理
    # ------------------------------------------------------------------ #
    def _complete(self, prompt: str, max_tokens: int = 4096) -> str:
        model = self.load()
        resp = model.create_completion(prompt=prompt, max_tokens=max_tokens,
                                       stop=["[END]", "</s>"], temperature=0.0)
        return (resp.get("choices") or [{}])[0].get("text", "").strip()

    @staticmethod
    def _extract_c_code(text: str) -> str:
        """后处理：去除 markdown 包裹，提取 C 代码块。"""
        text = text.strip()
        # 去掉 ```c ... ``` 包裹
        m = re.search(r"```(?:c|C)?\s*\n(.*?)\n```", text, re.DOTALL)
        if m:
            return m.group(1).strip()
        # 去掉行首的 ``` 或散落的 ``` 标记
        text = re.sub(r"^```[a-zA-Z]*\s*$", "", text, flags=re.MULTILINE)
        return text.strip()

    # ------------------------------------------------------------------ #
    # 路径 A：直接反编译
    # ------------------------------------------------------------------ #
    def decompile_binary(self, binary_path: str, optimization: str = "auto",
                         max_tokens: int = 4096) -> str:
        """反编译 ELF 二进制 → 人类可读 C。

        注意：LLM4Decompile 仅支持 Linux x86_64 ELF，PE（Windows）请走
        polish_ghidra_output() 迂回路径。
        """
        opt = optimization
        if opt == "auto":
            # 简单启发式：由文件时间戳/大小不可靠，默认按 O2 处理（最常见的发布优化）
            opt = "O2"
        assembly = self._get_assembly(binary_path, opt)
        prompt = self.DECOMPILE_PROMPT.format(opt=opt, assembly=assembly)
        raw = self._complete(prompt, max_tokens=max_tokens)
        return self._extract_c_code(raw)

    # ------------------------------------------------------------------ #
    # 路径 B：Ghidra 润色
    # ------------------------------------------------------------------ #
    def polish_ghidra_output(self, pseudo_c: str, function_name: str = "",
                             context_hint: str = "") -> str:
        """将 Ghidra/IDA 伪 C 润色为可读 C（RS-BA1 PE 主用路径）。"""
        ctx = ""
        if function_name:
            ctx += f"The function name is: {function_name}\n"
        if context_hint:
            ctx += f"The function is related to: {context_hint}\n"
        context_line = ctx if ctx else "Context: unknown\n"
        prompt = self.POLISH_PROMPT.format(pseudo_c=pseudo_c, context_line=context_line)
        raw = self._complete(prompt, max_tokens=4096)
        return self._extract_c_code(raw)

    # ------------------------------------------------------------------ #
    # 状态
    # ------------------------------------------------------------------ #
    def get_status(self) -> dict:
        """返回模型加载状态（health check 用）。"""
        status: dict[str, Any] = {
            "model_path": self.model_path,
            "model_loaded": self.is_loaded(),
            "n_ctx": self.n_ctx,
            "n_gpu_layers": self.n_gpu_layers,
            "status": "ready" if self.is_loaded() else "not_loaded",
        }
        if self.is_loaded():
            model = self._model
            status["max_context"] = getattr(model, "n_ctx", self.n_ctx)
            try:
                status["vram_used_mb"] = getattr(model, "n_gpu_layers", 0) * 0  # 无法精确获取时置 0
            except Exception:  # pragma: no cover
                status["vram_used_mb"] = 0
        return status

    def unload(self) -> None:
        """卸载模型，释放显存/内存。"""
        self._model = None
