"""台账⑥ LLM4Decompile MCP 收尾：flat adapter 管线单测。

真实 1.3b 推理（CPU bf16 ~3 分钟/次）不进单测，走手工验收
（papers 同级的 llm4decompile_result.json 留档）。这里覆盖：
- capstone 反汇编管线（objdump 缺失的 Windows 兜底路径）prompt 构造
- 生成后处理：sentencepiece 特殊字符 Ġ/Ċ 还原为空白
- decompile_binary 端到端（mock 推理层）：成功/文件不存在 fail-fast
- pe_metadata 不依赖 LLM 也能工作
- register 挂载 3 个工具 + healthcheck 语义
"""
from __future__ import annotations

import asyncio
import importlib.util
import sys
import types
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[1]
_ADAPTER_PATH = _REPO_ROOT / "mcpserver" / "adapters" / "llm4decompile.py"

# 真实 PE 样本：Windows 系统自带，体积小、.text 有内容
_SAMPLE_PE = Path(r"C:\Windows\System32\version.dll")


@pytest.fixture()
def adapter(monkeypatch) -> types.ModuleType:
    """文件级加载 adapter，假父包避免拉起 mcpserver/__init__ 全量依赖。"""
    for name in ("mcpserver", "mcpserver.adapters"):
        if name not in sys.modules:
            pkg = types.ModuleType(name)
            pkg.__path__ = [str(_REPO_ROOT / name.replace(".", "/"))]  # type: ignore[attr-defined]
            monkeypatch.setitem(sys.modules, name, pkg)
    # _common.register_capability_safe 用 stub，不触发真 registry
    common_stub = types.ModuleType("mcpserver.adapters._common")
    common_stub.register_capability_safe = lambda registry, cap: None
    monkeypatch.setitem(sys.modules, "mcpserver.adapters._common", common_stub)

    spec = importlib.util.spec_from_file_location(
        "mcpserver.adapters.llm4decompile", _ADAPTER_PATH
    )
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, "mcpserver.adapters.llm4decompile", module)
    spec.loader.exec_module(module)
    return module


class _ToolBag:
    """收集 register() 挂上的工具函数。"""

    def __init__(self):
        self.tools: dict = {}

    def add_tool(self, fn, name=None):
        self.tools[name or fn.__name__] = fn


@pytest.fixture()
def tools(adapter):
    bag = _ToolBag()
    adapter.register(bag)
    return bag.tools


# ---------------------------------------------------------------------------
# 反汇编管线（capstone 兜底路径，Windows 无 objdump）
# ---------------------------------------------------------------------------
def test_disassemble_builds_prompt_with_instructions(adapter):
    if not _SAMPLE_PE.exists():
        pytest.skip("非 Windows 环境缺样本")
    prompt = adapter._disassemble(_SAMPLE_PE, "x86_64", "main", "O0")
    # LLM4Decompile 官方 prompt 模板要素
    assert "decompile" in prompt.lower() or "source code" in prompt.lower()
    assert "O0" in prompt
    # 必须含真实汇编指令行（地址: 助记符），且已跳过 int3/nop 填充
    assert "\t" in prompt
    assert "int3" not in prompt.split("\n")[0]


def test_disassemble_caps_instruction_count(adapter):
    """1.3b 上下文 4096，prompt 内指令行数不许失控。"""
    if not _SAMPLE_PE.exists():
        pytest.skip("非 Windows 环境缺样本")
    prompt = adapter._disassemble(_SAMPLE_PE, "x86_64", "main", "O0")
    # 每行一条指令；上限 500 条 + 模板头尾
    assert len(prompt.splitlines()) < 600


# ---------------------------------------------------------------------------
# 生成后处理：Ġ/Ċ 特殊字符还原
# ---------------------------------------------------------------------------
def test_special_tokens_restored_to_whitespace(adapter, monkeypatch):
    """decode 后 sentencepiece 风格 Ġ(空格)/Ċ(换行) 必须还原成真实空白。"""
    captured = {}

    class _Inputs(dict):
        def to(self, device):
            return self

        def __getitem__(self, key):
            # 模拟张量批索引：inputs[0] → 第一条序列
            if key == 0:
                return dict.__getitem__(self, "input_ids")[0]
            return dict.__getitem__(self, key)

    class _FakeTok:
        def __call__(self, prompt, return_tensors=None):
            captured["prompt"] = prompt
            return _Inputs({"input_ids": [[1, 2, 3]]})

        def decode(self, ids, skip_special_tokens=True):
            return "int\u0120add(int\u0120a,\u0120int\u0120b)\u010a{\u010a\u0120\u0120return\u0120a\u0120+\u0120b;\u010a}"

    class _FakeModel:
        device = "cpu"

        def eval(self):
            return self

        def generate(self, **kw):
            return [[1, 2, 3, 9, 9]]

    class _FakeAutoModel:
        @staticmethod
        def from_pretrained(model_id, torch_dtype=None):
            class _M:
                device = "cpu"

                def to(self, device):
                    return _FakeModel()

            return _M()

    class _FakeAutoTok:
        @staticmethod
        def from_pretrained(model_id):
            return _FakeTok()

    fake_torch = types.SimpleNamespace(
        cuda=types.SimpleNamespace(is_available=lambda: False),
        bfloat16="bf16",
        float32="f32",
        no_grad=lambda: _NullCtx(),
    )
    fake_transformers = types.SimpleNamespace(
        AutoModelForCausalLM=_FakeAutoModel, AutoTokenizer=_FakeAutoTok
    )
    monkeypatch.setitem(sys.modules, "torch", fake_torch)
    monkeypatch.setitem(sys.modules, "transformers", fake_transformers)

    out = adapter._execute_decompile("prompt", 64, "fake/model")
    assert out == "int add(int a, int b)\n{\n  return a + b;\n}"
    assert "\u0120" not in out and "\u010a" not in out


class _NullCtx:
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


# ---------------------------------------------------------------------------
# decompile_binary 端到端（mock 推理层）
# ---------------------------------------------------------------------------
def test_decompile_binary_end_to_end_with_mock(tools, adapter, monkeypatch):
    if not _SAMPLE_PE.exists():
        pytest.skip("非 Windows 环境缺样本")
    monkeypatch.setattr(adapter, "_execute_decompile", lambda p, n, m: "int main(void) { return 0; }")

    r = asyncio.run(tools["decompile_binary"](str(_SAMPLE_PE)))
    assert r["ok"] is True
    assert "int main" in r["c_code"]
    assert r["model"]
    assert r["elapsed_sec"] >= 0


def test_decompile_binary_missing_file_fails_fast(tools):
    r = asyncio.run(tools["decompile_binary"](r"C:\no\such\file.dll"))
    assert r["ok"] is False
    assert "error" in r


def test_decompile_binary_bad_opt_level_rejected(tools, adapter, monkeypatch):
    """非法优化级别应在进推理前被拒（防 prompt 注入垃圾参数）。"""
    if not _SAMPLE_PE.exists():
        pytest.skip("非 Windows 环境缺样本")
    monkeypatch.setattr(adapter, "_execute_decompile", lambda p, n, m: "x")
    r = asyncio.run(tools["decompile_binary"](str(_SAMPLE_PE), opt_level="O9"))
    assert r["ok"] is False


# ---------------------------------------------------------------------------
# pe_metadata：不依赖 LLM（模型没装也能用的降级能力）
# ---------------------------------------------------------------------------
def test_pe_metadata_without_llm(tools):
    if not _SAMPLE_PE.exists():
        pytest.skip("非 Windows 环境缺样本")
    r = asyncio.run(tools["pe_metadata"](str(_SAMPLE_PE)))
    assert r["ok"] is True
    assert r["machine"] in (0x14C, 0x8664)  # i386 / AMD64
    assert any(s["name"].lower() == ".text" for s in r["sections"])


def test_pe_metadata_non_pe_rejected(tools, tmp_path):
    f = tmp_path / "not_pe.bin"
    f.write_bytes(b"\x00" * 64)
    r = asyncio.run(tools["pe_metadata"](str(f)))
    assert r["ok"] is False


# ---------------------------------------------------------------------------
# 注册与健康检查
# ---------------------------------------------------------------------------
def test_register_exposes_three_tools(tools):
    assert set(tools) == {"decompile_binary", "pe_metadata", "decompile_status"}


def test_decompile_status_reports_model_cache(tools):
    r = asyncio.run(tools["decompile_status"]())
    assert r["ok"] is True
    assert "model_cached" in r["dependencies"]


def test_healthcheck_true_when_model_cached(adapter):
    """模型已下载（验收前提）时 healthcheck 必须为 True，门禁不跳过。"""
    assert adapter.healthcheck() is True
