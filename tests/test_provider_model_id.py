"""工单229 任务三 · 模型 ID 兼容矩阵（真调外部 API 的用例默认不跑）。

## 为什么要有这个

LLM 平台的 **alias 漂移没有任何 CI 报警**。2026-10-10 那次就是：平台把老别名静默 alias 到
规范名，请求返回 **HTTP 200 但 ``content`` 为空**，用户侧表现为 400，靠人工 curl 才定位到。
本文件对每个 provider 的 default 模型发一次最小请求并断言三件事：

1. HTTP 200；
2. 正文非空（≥ 2 字符）—— 专治「200 + 空 content」这种静默降级；
3. **返回体里的 ``model`` 字段 == 请求的 model ID** —— 这条才是防 alias 漂移的核心。
   不等时打印 ``alias_diff``（expected vs returned）便于人工定位。

## 配置来源（⚠️ 与工单预设的偏差，实测纠正）

工单预设「从 ``config.yaml`` 读各 provider 的 ``available_models_json`` + ``default``」。
**本仓没有 `config.yaml`**（只有 `config.json.example`；`config.json` 里也只有一条
生效的 `api.{base_url,model,provider}`，没有多 provider 台账）。
⇒ 本文件改用**仓内唯一权威 provider 表**：``tools/switch_llm_provider.py`` 的 ``PRESETS``
（含 base_url / model / key_env）。不复制、不另建台账——它变了这里跟着变。

本文件唯一手维的信息是 ``PROVIDER_STYLES``（endpoint 风格）：``PRESETS`` 没有这个字段。
根因是「MiniMax 走 Anthropic 兼容面、其余走 OpenAI 兼容面」这件事在仓内没有声明处。

## 跑法

    pytest -m live tests/test_provider_model_id.py -q    # 真调（默认被 addopts 的 `not live` 排除）
    tools/check_providers.sh                             # 同上，巡检入口
    SKIP_LIVE_API_TEST=1 pytest tests/ -q                # 显式跳过（与默认等价）

跳过条件：`SKIP_LIVE_API_TEST` 置真 / 该 provider 的 key 环境变量为空。
"""
from __future__ import annotations

import importlib.util
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# 与 tests/test_switch_llm_provider.py 相同的安全加载姿势：按文件路径 importlib 加载，
# 不往 sys.path 里塞 tools/（否则 tools/tests/ 会抢走顶层 "tests" 命名空间，工单225 病二）。
_spec = importlib.util.spec_from_file_location(
    "w229_switch_llm_provider", REPO_ROOT / "tools" / "switch_llm_provider.py")
assert _spec is not None and _spec.loader is not None
_switch = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_switch)
PRESETS: dict[str, dict[str, str]] = _switch.PRESETS

LIVE_TIMEOUT = 10.0
MIN_CONTENT_CHARS = 2
TRUTHY = {"1", "true", "yes", "on"}
PROBE_PROMPT = "ping"

# endpoint 风格：本文件唯一手维信息（PRESETS 无此字段）。
#   openai    → POST {base_url}/chat/completions      （Authorization: Bearer）
#   anthropic → POST {base_url}/messages              （x-api-key + anthropic-version）
PROVIDER_STYLES: dict[str, str] = {
    "deepseek": "openai",
    "minimax": "anthropic",
    "zhipu": "openai",
    "tokenrhythm": "openai",
}

ENDPOINT_PATH = {"openai": "/chat/completions", "anthropic": "/messages"}


def resolve_endpoint(base_url: str, style: str) -> str:
    """base_url + 端点路径；base_url 已含该后缀时不再重复拼接（工单 229 的 MiniMax 备注）。"""
    path = ENDPOINT_PATH[style]
    base = base_url.rstrip("/")
    return base if base.endswith(path) else base + path


def build_request(style: str, model: str, api_key: str) -> tuple[dict[str, str], dict]:
    """返回 (headers, payload)。"""
    if style == "anthropic":
        return (
            {"x-api-key": api_key, "anthropic-version": "2023-06-01"},
            {"model": model, "max_tokens": 8, "messages": [{"role": "user", "content": PROBE_PROMPT}]},
        )
    return (
        {"Authorization": f"Bearer {api_key}"},
        {"model": model, "max_tokens": 8, "messages": [{"role": "user", "content": PROBE_PROMPT}]},
    )


def extract_model_and_text(style: str, data: dict) -> tuple[str | None, str]:
    """从响应体取出 (返回的 model 字段, 正文文本)；取不到正文时返回空串。"""
    if style == "anthropic":
        blocks = data.get("content") or []
        text = "".join(b.get("text", "") for b in blocks if isinstance(b, dict))
        return data.get("model"), text
    choices = data.get("choices") or []
    if not choices:
        return data.get("model"), ""
    message = choices[0].get("message") or {}
    return data.get("model"), message.get("content") or ""


def skip_reason(api_key: str | None) -> str | None:
    if os.environ.get("SKIP_LIVE_API_TEST", "").strip().lower() in TRUTHY:
        return "SKIP_LIVE_API_TEST 已置位"
    if not api_key:
        return "缺少对应 API key 环境变量"
    return None


def post_json(url: str, headers: dict[str, str], payload: dict) -> tuple[int, dict]:
    body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(url, data=body, method="POST")
    request.add_header("Content-Type", "application/json")
    for key, value in headers.items():
        request.add_header(key, value)
    try:
        with urllib.request.urlopen(request, timeout=LIVE_TIMEOUT) as response:
            return response.status, json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", "replace")
        try:
            return exc.code, json.loads(raw)
        except json.JSONDecodeError:
            return exc.code, {"_raw": raw[:500]}


# --------------------------------------------------------------------------- #
# 静态用例（默认会跑）：矩阵自检 + 端点拼接 + 响应解析
# --------------------------------------------------------------------------- #

@pytest.mark.core
def test_matrix_covers_every_preset() -> None:
    """PRESETS 新增 provider 时必须同步补 style——否则矩阵会静默漏测。"""
    missing = sorted(set(PRESETS) - set(PROVIDER_STYLES))
    assert not missing, f"PROVIDER_STYLES 缺少这些 provider 的 endpoint 风格：{missing}"
    extra = sorted(set(PROVIDER_STYLES) - set(PRESETS))
    assert not extra, f"PROVIDER_STYLES 指向了 PRESETS 里不存在的 provider：{extra}"


@pytest.mark.core
@pytest.mark.parametrize(
    ("base_url", "style", "expected"),
    [
        ("https://api.deepseek.com/v1", "openai", "https://api.deepseek.com/v1/chat/completions"),
        ("https://api.deepseek.com/v1/", "openai", "https://api.deepseek.com/v1/chat/completions"),
        ("https://api.deepseek.com/v1/chat/completions", "openai",
         "https://api.deepseek.com/v1/chat/completions"),
        ("https://api.minimax.chat/v1", "anthropic", "https://api.minimax.chat/v1/messages"),
        ("https://api.minimax.chat/v1/messages", "anthropic", "https://api.minimax.chat/v1/messages"),
    ],
)
def test_resolve_endpoint(base_url: str, style: str, expected: str) -> None:
    assert resolve_endpoint(base_url, style) == expected


@pytest.mark.core
def test_extract_openai_style_response() -> None:
    data = {"model": "deepseek-flash", "choices": [{"message": {"content": "pong"}}]}
    assert extract_model_and_text("openai", data) == ("deepseek-flash", "pong")
    assert extract_model_and_text("openai", {"model": "x"}) == ("x", "")


@pytest.mark.core
def test_extract_anthropic_style_response() -> None:
    data = {"model": "MiniMax-M3", "content": [{"type": "text", "text": "po"}, {"type": "text", "text": "ng"}]}
    assert extract_model_and_text("anthropic", data) == ("MiniMax-M3", "pong")
    assert extract_model_and_text("anthropic", {"model": "x"}) == ("x", "")


@pytest.mark.core
def test_skip_reason_respects_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SKIP_LIVE_API_TEST", raising=False)
    assert skip_reason("sk-x") is None
    assert skip_reason("") is not None
    assert skip_reason(None) is not None
    monkeypatch.setenv("SKIP_LIVE_API_TEST", "1")
    assert skip_reason("sk-x") is not None


# --------------------------------------------------------------------------- #
# 真调用例（@pytest.mark.live，默认被 addopts 的 `not live` 排除）
# --------------------------------------------------------------------------- #

@pytest.mark.live
@pytest.mark.parametrize("provider", sorted(PROVIDER_STYLES))
def test_default_model_id_round_trips(provider: str) -> None:
    preset = PRESETS[provider]
    style = PROVIDER_STYLES[provider]
    api_key = os.environ.get(preset["key_env"], "").strip()
    reason = skip_reason(api_key)
    if reason:
        pytest.skip(f"{provider}: {reason}")

    url = resolve_endpoint(preset["base_url"], style)
    headers, payload = build_request(style, preset["model"], api_key)
    status, data = post_json(url, headers, payload)

    assert status == 200, f"{provider} HTTP {status} @ {url}: {json.dumps(data, ensure_ascii=False)[:300]}"

    returned_model, text = extract_model_and_text(style, data)
    assert len(text.strip()) >= MIN_CONTENT_CHARS, (
        f"{provider} 返回 200 但正文为空（疑似别名静默降级）@ {url}: "
        f"{json.dumps(data, ensure_ascii=False)[:300]}"
    )
    assert returned_model == preset["model"], (
        f"alias_diff: provider={provider} endpoint={url} "
        f"expected={preset['model']!r} returned={returned_model!r}"
    )
