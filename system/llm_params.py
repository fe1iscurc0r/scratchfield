"""LLM 参数获取公共模块

统一管理 LLM 调用参数（API key、base URL、模型名称前缀）的构建逻辑。
所有需要发起 LLM 调用的模块（llm_service、intent_router、context_compressor）
应通过此模块获取参数，避免重复实现。
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from system.config import get_config


def should_use_gateway() -> bool:
    """判断是否使用 Naga 网关（本地 Token 模式下恒为 False）"""
    try:
        from apiserver.naga_auth import should_use_model_gateway
        return should_use_model_gateway()
    except Exception:
        return False


def get_access_token() -> str:
    """获取当前 access_token"""
    try:
        from apiserver.naga_auth import get_access_token as _get
        return _get()
    except Exception:
        return ""


def get_gateway_url() -> str:
    """获取网关 URL"""
    try:
        from apiserver.naga_auth import NAGA_MODEL_URL
        return NAGA_MODEL_URL
    except Exception:
        return ""


def get_llm_params(
    model_type: str = "chat",
    *,
    api_key_override: str | None = None,
    api_base_override: str | None = None,
) -> dict[str, Any]:
    """获取 LLM 调用参数

    Args:
        model_type: 用途标识，影响 base_url 处理方式
                    - "chat": 标准对话，base_url 尾部加 "/"
                    - "router": 路由模型，base_url 尾部加 "/"
                    - "compress": 压缩模型，base_url 尾部加 "/"
                    - "anthropic": Anthropic 格式，不加尾部 "/"
        api_key_override: 强制覆盖 API key
        api_base_override: 强制覆盖 base URL

    Returns:
        LiteLLM 兼容的参数字典
    """
    if should_use_gateway():
        token = get_access_token()
        gateway_url = get_gateway_url()
        return {
            "api_key": token,
            "api_base": gateway_url + "/" if gateway_url else None,
            "extra_body": {"user_token": token} if token else {},
        }

    cfg = get_config()
    api_key = api_key_override or cfg.api.api_key
    base_url = api_base_override or cfg.api.base_url or ""

    if cfg.api.api_format == "anthropic":
        params: dict[str, Any] = {"api_key": api_key}
        if base_url and "anthropic.com" not in base_url:
            params["api_base"] = base_url.rstrip("/")
        return params

    if not base_url:
        return {"api_key": api_key}

    base_url = base_url.rstrip("/")
    if model_type == "anthropic":
        return {"api_key": api_key, "api_base": base_url}
    return {"api_key": api_key, "api_base": base_url + "/"}


def build_model_name(
    model: str,
    *,
    model_type: str = "chat",
    base_url: str | None = None,
    provider: str | None = None,
) -> str:
    """构建 LiteLLM 格式的模型名称（带提供商前缀）

    Args:
        model: 模型名称
        model_type: 用途标识，影响 base_url 判断逻辑
                    - "chat": 完整提供商检测
                    - "router": 简化检测（openai.com 判断）
                    - "compress": 简化检测（openai.com 判断）
        base_url: API 地址，默认从 config 读取
        provider: 提供商名称，默认从 config 读取

    Returns:
        LiteLLM 格式的模型名，如 "openai/deepseek-chat"
    """
    if should_use_gateway():
        return f"openai/{model}"

    cfg = get_config()
    api_format = cfg.api.api_format
    provider_name = (provider or cfg.api.provider or "auto").lower()
    base = (base_url or cfg.api.base_url or "").lower()

    if api_format == "anthropic" or provider_name == "anthropic":
        if not model.startswith("anthropic/"):
            return f"anthropic/{model}"
        return model

    if model_type in ("router", "compress"):
        if "openai.com" in base:
            return model
        return f"openai/{model}"

    if provider_name == "gemini":
        if not model.startswith("gemini/"):
            return f"gemini/{model}"
        return model
    if provider_name == "openrouter":
        if not model.startswith("openrouter/"):
            return f"openrouter/{model}"
        return model
    if provider_name == "deepseek":
        if not model.startswith("deepseek/"):
            return f"deepseek/{model}"
        return model
    if provider_name == "openai":
        # OpenAI 兼容中转（非 openai.com）需显式 openai/ 前缀，
        # 否则 litellm 报 "LLM Provider NOT provided"
        if base and "openai.com" not in base and not model.startswith("openai/"):
            return f"openai/{model}"
        return model

    if "deepseek" in base:
        if not model.startswith("deepseek/"):
            return f"deepseek/{model}"
    elif "openrouter" in base:
        if not model.startswith("openrouter/"):
            return f"openrouter/{model}"
    elif "openai.com" in base:
        return model
    else:
        if not model.startswith("openai/"):
            return f"openai/{model}"
    return model
