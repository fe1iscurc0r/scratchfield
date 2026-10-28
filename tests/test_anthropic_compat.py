"""工单 228 任务三 · anthropic 1.x 兼容层**离线**单测（mock SDK：不打网络、不装 SDK）。

用 importlib 按路径加载 ``mcpserver/llm_gateway/anthropic_compat.py`` —— 不触发
``mcpserver`` 包的导入副作用，也不要求本机装 anthropic SDK。
"""
from __future__ import annotations

import importlib.util
import json
import sys
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

_spec = importlib.util.spec_from_file_location(
    "w228_anthropic_compat", ROOT / "mcpserver" / "llm_gateway" / "anthropic_compat.py")
ac = importlib.util.module_from_spec(_spec)
sys.modules["w228_anthropic_compat"] = ac
_spec.loader.exec_module(ac)


def _fake_sdk(record: list) -> types.SimpleNamespace:
    """最小 anthropic 替身：记录每次 create 的 kwargs，返回 1.x 形态响应。"""
    class _Messages:
        def create(self, **kwargs):
            record.append(kwargs)
            return {"content": [{"type": "text", "text": "pong"}]}

    class _Client:
        def __init__(self, **kwargs):
            self.kw = kwargs
            self.messages = _Messages()

    class _AsyncClient(_Client):
        pass

    return types.SimpleNamespace(Anthropic=_Client, AsyncAnthropic=_AsyncClient)


# ── 纯翻译函数（不碰 SDK）────────────────────────────────────────────────────

def test_normalize_extracts_system_from_messages():
    msgs, system = ac.normalize_messages([
        {"role": "system", "content": "be terse"},
        {"role": "user", "content": "hi"},
    ])
    assert system == "be terse"
    assert msgs == [{"role": "user", "content": "hi"}]


def test_explicit_system_goes_first():
    _, system = ac.normalize_messages(
        [{"role": "system", "content": "inner"}, {"role": "user", "content": "hi"}],
        system="outer",
    )
    assert system == "outer\n\ninner"


def test_wrap_text_blocks():
    msgs, _ = ac.normalize_messages([{"role": "user", "content": "hi"}], wrap_text_blocks=True)
    assert msgs == [{"role": "user", "content": [{"type": "text", "text": "hi"}]}]


def test_wrap_text_blocks_leaves_non_str_alone():
    blocks = [{"type": "text", "text": "x"}]
    msgs, _ = ac.normalize_messages([{"role": "user", "content": blocks}], wrap_text_blocks=True)
    assert msgs[0]["content"] == blocks


# ── messages_create：三处强制翻译 ────────────────────────────────────────────

def test_messages_create_sets_required_fields(monkeypatch):
    record: list = []
    monkeypatch.setitem(sys.modules, "anthropic", _fake_sdk(record))
    client = ac.get_client(api_key="sk-test")
    ac.messages_create(
        client,
        messages=[{"role": "user", "content": "hi"}],
        model="claude-3-5-sonnet-latest",
        max_tokens=32,
        system="sys",
    )
    call = record[-1]
    assert call["model"] == "claude-3-5-sonnet-latest"
    assert call["max_tokens"] == 32
    assert call["system"] == "sys"
    assert call["messages"] == [{"role": "user", "content": "hi"}]


def test_max_tokens_defaults_when_omitted(monkeypatch):
    """1.x 里 max_tokens 必填 —— 不传也必须补上默认值，否则 400。"""
    record: list = []
    monkeypatch.setitem(sys.modules, "anthropic", _fake_sdk(record))
    client = ac.get_client(api_key="sk-test")
    ac.messages_create(client, messages=[{"role": "user", "content": "hi"}])
    assert record[-1]["max_tokens"] == ac.DEFAULT_MAX_TOKENS


def test_system_in_messages_is_hoisted_to_top_level(monkeypatch):
    record: list = []
    monkeypatch.setitem(sys.modules, "anthropic", _fake_sdk(record))
    client = ac.get_client(api_key="sk-test")
    ac.messages_create(client, messages=[
        {"role": "system", "content": "be terse"},
        {"role": "user", "content": "hi"},
    ])
    call = record[-1]
    assert call["system"] == "be terse"
    assert all(m.get("role") != "system" for m in call["messages"])


def test_extra_kwargs_pass_through(monkeypatch):
    record: list = []
    monkeypatch.setitem(sys.modules, "anthropic", _fake_sdk(record))
    client = ac.get_client(api_key="sk-test")
    ac.messages_create(
        client, messages=[{"role": "user", "content": "hi"}],
        max_tokens=8, temperature=0.2, top_p=0.9,
    )
    assert record[-1]["temperature"] == 0.2
    assert record[-1]["top_p"] == 0.9


# ── get_client：key 优先级与 async 分支 ─────────────────────────────────────

def test_get_client_key_priority(monkeypatch):
    record: list = []
    monkeypatch.setitem(sys.modules, "anthropic", _fake_sdk(record))
    monkeypatch.delenv(ac.ENV_API_KEY, raising=False)
    assert ac.get_client(api_key="explicit").kw["api_key"] == "explicit"
    monkeypatch.setenv(ac.ENV_API_KEY, "from-env")
    assert ac.get_client().kw["api_key"] == "from-env"


def test_get_client_selects_async_class(monkeypatch):
    monkeypatch.setitem(sys.modules, "anthropic", _fake_sdk([]))
    client = ac.get_client(api_key="k", async_client=True)
    assert type(client).__name__ == "_AsyncClient"


def test_load_sdk_raises_compat_error_when_absent(monkeypatch):
    """SDK 缺失必须是 AnthropicCompatError（可降级），不是裸 ImportError。"""
    monkeypatch.setitem(sys.modules, "anthropic", None)
    with pytest.raises(ac.AnthropicCompatError):
        ac.load_sdk()


# ── 配置兜底与响应抽取 ──────────────────────────────────────────────────────

def test_api_key_from_repo_config(tmp_path):
    cfg = tmp_path / "config.json"
    cfg.write_text(json.dumps({"api": {"api_key": "sk-from-config"}}), encoding="utf-8")
    assert ac.api_key_from_repo_config(cfg) == "sk-from-config"


def test_api_key_from_repo_config_missing_or_malformed(tmp_path):
    assert ac.api_key_from_repo_config(tmp_path / "nope.json") is None
    bad = tmp_path / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    assert ac.api_key_from_repo_config(bad) is None


def test_extract_text_handles_dict_and_object():
    assert ac.extract_text({"content": [{"type": "text", "text": "a"},
                                        {"type": "text", "text": "b"}]}) == "ab"
    assert ac.extract_text({"content": "plain"}) == "plain"

    class _Block:
        text = "obj"

    class _Resp:
        content = [_Block()]

    assert ac.extract_text(_Resp()) == "obj"
    assert ac.extract_text(object()) == ""
