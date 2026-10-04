#!/usr/bin/env python3
"""
LLM服务模块
提供统一的LLM调用接口，替代conversation_core.py中的get_response方法
使用 LiteLLM 统一处理多模型的 COT/reasoning_content
"""

import hashlib
import logging
import os
import sys
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# litellm 首次 import 约 8.9s，占启动时间 75% —— 改走懒加载代理（卷191-B2）
# 真实 import 推迟到首次 LLM 调用，见 apiserver/litellm_lazy.py
from fastapi import FastAPI, HTTPException

from system.config import get_config
from system.config_value_utils import is_placeholder_api_key
from system.llm_params import build_model_name as _build_common_model_name
from system.llm_params import get_access_token, get_gateway_url, should_use_gateway
from system.llm_params import get_llm_params as _get_common_llm_params

from . import naga_auth
from .litellm_lazy import acompletion, litellm

# 配置日志
logger = logging.getLogger("LLMService")


@dataclass
class LLMResponse:
    """LLM响应结构，包含内容和推理过程"""

    content: str
    reasoning_content: str | None = None

    def to_dict(self) -> dict[str, Any]:
        result = {"content": self.content}
        if self.reasoning_content:
            result["reasoning_content"] = self.reasoning_content
        return result


class LLMService:
    """LLM服务类 - 使用 LiteLLM 提供统一的LLM调用接口，支持 COT/reasoning_content"""

    def __init__(self):
        self._initialized = False
        self._initialize_client()

    def _initialize_client(self):
        """初始化 LiteLLM 配置"""
        try:
            cfg = get_config()
            litellm.api_key = cfg.api.api_key
            # Anthropic 格式下不设置全局 api_base，由每次调用的参数传递
            # 避免全局 base 污染导致请求被路由到错误的端点
            if cfg.api.api_format != "anthropic":
                if cfg.api.base_url and "openai.com" not in cfg.api.base_url:
                    litellm.api_base = cfg.api.base_url.rstrip("/") + "/"
            self._initialized = True
            logger.info("LLM服务 (LiteLLM) 初始化成功")
        except Exception as e:
            logger.error(f"LLM服务初始化失败: {e}")
            self._initialized = False

    def _get_model_name(
        self,
        model: str | None = None,
        base_url: str | None = None,
        provider: str | None = None,
    ) -> str:
        """获取 LiteLLM 格式的模型名称"""
        cfg = get_config()
        model = model or cfg.api.model
        return _build_common_model_name(
            model,
            model_type="chat",
            base_url=base_url,
            provider=provider,
        )

    def _get_llm_params(self) -> dict[str, Any]:
        """获取 LLM 调用参数"""
        return _get_common_llm_params(model_type="chat")

    def _get_overridden_llm_params(
        self, api_key: str | None = None, api_base: str | None = None
    ) -> dict[str, Any]:
        """获取带覆写的 LLM 调用参数"""
        return _get_common_llm_params(
            model_type="chat",
            api_key_override=api_key,
            api_base_override=api_base,
        )

    def _local_api_config_error(self, llm_params: dict[str, Any]) -> str | None:
        """Return a user-facing configuration error for invalid local model settings."""
        if should_use_gateway():
            return None
        if is_placeholder_api_key(llm_params.get("api_key")):
            return "未配置本地模型 API 密钥：请填写真实 API Key，或登录后启用陆墨模型网关。"
        return None

    def _supports_reasoning_replay(
        self,
        model_name: str,
        api_base: str | None = None,
        provider: str | None = None,
    ) -> bool:
        """DeepSeek Thinking Mode tool-call turns require replaying assistant reasoning_content."""
        combined = " ".join(
            str(part or "").lower()
            for part in (model_name, api_base, provider)
        )
        if "deepseek-reasoner" in combined:
            return False
        return "deepseek" in combined

    def _prepare_messages_for_model(
        self,
        messages: list[dict[str, Any]],
        model_name: str,
        api_base: str | None = None,
        provider: str | None = None,
    ) -> list[dict[str, Any]]:
        """Strip or retain reasoning_content according to the target model contract."""
        allow_reasoning_replay = self._supports_reasoning_replay(model_name, api_base, provider)
        prepared: list[dict[str, Any]] = []
        for message in messages:
            item = dict(message)
            if "reasoning_content" in item:
                can_replay = (
                    allow_reasoning_replay
                    and item.get("role") == "assistant"
                    and bool(item.get("tool_calls"))
                )
                if not can_replay:
                    item.pop("reasoning_content", None)
            prepared.append(item)
        return prepared

    # 不支持自定义 temperature 的模型约束表: {前缀: 强制值}
    _TEMPERATURE_CONSTRAINTS: dict[str, float] = {
        "gpt-5": 1,
    }

    def _normalize_temperature(self, model_name: str, temperature: float | None) -> float | None:
        """兼容不支持自定义 temperature 的模型参数约束。"""
        if temperature is None:
            return None

        normalized_model = (model_name or "").lower()
        for prefix, forced_value in self._TEMPERATURE_CONSTRAINTS.items():
            if normalized_model.startswith(prefix) and temperature != forced_value:
                logger.info(f"[LLM] 模型 {model_name} 仅支持 temperature={forced_value}，自动调整当前值 {temperature}")
                return forced_value

        return temperature

    async def get_response(self, prompt: str, temperature: float = 0.7) -> str:
        """为其他模块提供API调用接口（保持向后兼容，只返回 content）"""
        response = await self.get_response_with_reasoning(prompt, temperature)
        return response.content

    async def get_response_with_reasoning(self, prompt: str, temperature: float = 0.7) -> LLMResponse:
        """为其他模块提供API调用接口，返回包含 reasoning_content 的完整响应"""
        if not self._initialized:
            self._initialize_client()
            if not self._initialized:
                return LLMResponse(content="LLM服务不可用: 客户端初始化失败")

        try:
            model_name = self._get_model_name()
            llm_params = self._get_llm_params()
            config_error = self._local_api_config_error(llm_params)
            if config_error:
                return LLMResponse(content=config_error)
            response = await self._acompletion_thinking(
                model=model_name,
                messages=[{"role": "user", "content": prompt}],
                temperature=self._normalize_temperature(model_name, temperature),
                max_tokens=get_config().api.max_tokens,
                **llm_params
            )
            message = response.choices[0].message
            return LLMResponse(
                content=message.content or "", reasoning_content=getattr(message, "reasoning_content", None)
            )
        except Exception as e:
            logger.error(f"API调用失败: {e}")
            return LLMResponse(content=f"API调用出错: {str(e)}")

    def _apply_thinking_params(self, call_params: dict, *, enabled: bool | None = None) -> None:
        """思考开关透传（思考找回修复）。

        部分 OpenAI 兼容中转（如 tokenrhythm）默认不返回 reasoning_content，
        需要显式 enable_thinking=true 才吐思考链；官方 DeepSeek 等忽略该参数，
        无副作用。设 LUMO_ENABLE_THINKING=0 可整体关闭。

        ``enabled=False``：显式关闭（结构化短输出类辅助调用——Galgame 候选/
        摘要等不需要思考链，思考只会拖慢并撞超时）。
        """
        import os

        if enabled is False:
            return
        if enabled is None and os.environ.get("LUMO_ENABLE_THINKING", "1") == "0":
            return
        extra_body = dict(call_params.get("extra_body") or {})
        extra_body.setdefault("enable_thinking", True)
        call_params["extra_body"] = extra_body

    async def _acompletion_thinking(self, *, enable_thinking: bool | None = None, **call_params):
        """acompletion + 思考开关透传（见 _apply_thinking_params）。"""
        self._apply_thinking_params(call_params, enabled=enable_thinking)
        return await acompletion(**call_params)

    def is_available(self) -> bool:
        """检查LLM服务是否可用"""
        return self._initialized

    async def chat_with_context(self, messages: list[dict], temperature: float = 0.7) -> str:
        """带上下文的聊天调用（保持向后兼容，只返回 content）"""
        response = await self.chat_with_context_and_reasoning(messages, temperature)
        return response.content

    async def chat_with_context_and_reasoning_with_overrides(
        self,
        messages: list[dict[str, Any]],
        temperature: float = 0.7,
        model_override: str | None = None,
        api_key_override: str | None = None,
        api_base_override: str | None = None,
        provider_hint: str | None = None,
        enable_thinking: bool | None = None,
    ) -> LLMResponse:
        """带上下文聊天（支持模型/网关覆写）"""
        if not self._initialized:
            self._initialize_client()
            if not self._initialized:
                return LLMResponse(content="LLM服务不可用: 客户端初始化失败")

        final_model = model_override or get_config().api.model
        final_base = api_base_override or get_config().api.base_url
        final_api_key = api_key_override or get_config().api.api_key

        try:
            model_name = final_model
            _real_providers = ("openai", "deepseek", "gemini", "openrouter", "anthropic")
            if provider_hint and provider_hint.lower() in _real_providers and provider_hint.lower() != "openai":
                # gemini 等非 openai provider，加 LiteLLM 前缀
                if not model_name.startswith(f"{provider_hint}/"):
                    model_name = f"{provider_hint}/{model_name}"
            else:
                # openai/auto/custom/未指定: 走原有 base_url 推断逻辑
                model_name = self._get_model_name(model_name, final_base, provider_hint)

            llm_params = self._get_overridden_llm_params(final_api_key, final_base)
            config_error = self._local_api_config_error(llm_params)
            if config_error:
                return LLMResponse(content=config_error)
            prepared_messages = self._prepare_messages_for_model(
                messages,
                model_name,
                final_base,
                provider_hint,
            )
            response = await self._acompletion_thinking(
                model=model_name,
                messages=prepared_messages,
                temperature=self._normalize_temperature(model_name, temperature),
                max_tokens=get_config().api.max_tokens if hasattr(get_config().api, 'max_tokens') else None,
                enable_thinking=enable_thinking,
                **llm_params
            )
            message = response.choices[0].message
            return LLMResponse(
                content=message.content or "", reasoning_content=getattr(message, "reasoning_content", None)
            )
        except Exception as e:
            logger.error(f"上下文聊天调用失败: {e}")
            return LLMResponse(content=f"聊天调用出错: {str(e)}")

    async def chat_with_context_and_reasoning(self, messages: list[dict], temperature: float = 0.7,
                                              enable_thinking: bool | None = None) -> LLMResponse:
        """带上下文的聊天调用，返回包含 reasoning_content 的完整响应"""
        return await self.chat_with_context_and_reasoning_with_overrides(
            messages=messages,
            temperature=temperature,
            model_override=None,
            api_key_override=None,
            api_base_override=None,
            enable_thinking=enable_thinking,
        )

    async def stream_chat_with_context(self, messages: list[dict], temperature: float = 0.7,
                                       model_override: dict[str, str] | None = None,
                                       tools: list[dict] | None = None,
                                       enable_thinking: bool | None = None,
                                       router_meta: dict[str, str] | None = None):
        """带上下文的流式聊天调用，支持 reasoning_content 交织输出 + 原生 function calling

        Args:
            messages: 对话消息列表
            temperature: 生成温度
            model_override: 临时模型覆盖参数，用于切换到视觉模型等场景
                格式: {"model": "glm-4.5v", "api_base": "https://...", "api_key": "..."}
            tools: OpenAI function calling schemas（可选）
            router_meta: W125-01 路由输入（session_id/step_type/task_type/turn_id）；
                仅当调用方**未**指定 model_override 且 `router.enabled=true` 时生效（默认关，行为不变）

        Yields:
            格式为 "data: <json>\n\n" 的 SSE 事件
            JSON 结构: {"type": "content"|"reasoning"|"tool_calls_native", "text": "..."}
        """
        # W125-01/02/04：turn 级路由（默认关）+ 决策记录 + 路由 span
        _router_log_id = None
        _router_started = time.perf_counter()
        _router_finished = False

        def _finish_router(ok: bool, error: str = "") -> None:
            nonlocal _router_finished
            if _router_finished:
                return
            _router_finished = True
            latency = time.perf_counter() - _router_started
            try:
                if _router_log_id:
                    from apiserver import llm_router

                    llm_router.record_outcome(_router_log_id, success=ok, latency=latency, error=error)
            except Exception:  # noqa: BLE001 - 记录失败不影响对话
                logger.debug("[LLM] 路由结果回填失败", exc_info=True)
            try:
                if _router_span_cm is not None:
                    if _router_span is not None:
                        _router_span.attributes["status"] = "success" if ok else "error"
                    _router_span_cm.__exit__(None, None, None)
            except Exception:  # noqa: BLE001
                logger.debug("[LLM] 路由 span 收尾失败", exc_info=True)

        _router_span = None
        _router_span_cm = None
        if model_override is None:
            try:
                from apiserver import llm_router

                meta = dict(router_meta or {})
                routed = llm_router.route_override(
                    messages, tools=tools, step_type=str(meta.get("step_type") or ""),
                    task_type=str(meta.get("task_type") or ""),
                    session_id=str(meta.get("session_id") or ""),
                )
                if routed:
                    decision = dict(routed.get("_router") or {})
                    model_override = {k: v for k, v in routed.items() if k != "_router"}
                    _router_log_id = llm_router.record_decision(
                        decision, session_id=str(meta.get("session_id") or ""),
                        turn_id=str(meta.get("turn_id") or ""),
                    )
                    try:
                        from apiserver.event_bus.trace import trace_span

                        _router_span_cm = trace_span(
                            "router:route", tier=decision.get("tier"),
                            model=decision.get("model"),
                            complexity=decision.get("complexity"),
                        )
                        _router_span = _router_span_cm.__enter__()  # 拿到 Span 本体
                    except Exception:  # noqa: BLE001 - span 失败不影响调用
                        _router_span = None
                        _router_span_cm = None
            except Exception as e:  # noqa: BLE001 - 路由失败绝不拦对话（回落现有行为）
                logger.warning(f"[LLM] 模型路由跳过（回落到现有配置）: {e}")
        if not self._initialized:
            self._initialize_client()
            if not self._initialized:
                yield self._format_sse_chunk("content", "LLM服务不可用: 客户端初始化失败")
                return

        # 重试策略：最多 3 次
        #   - 401 AuthenticationError → 刷新 token 后重试（最多 1 次）
        #   - 连接错误 / 流中断  → 直接重试（最多 2 次）
        max_attempts = 3
        auth_retried = False

        for attempt in range(max_attempts):
            try:
                # 如果提供了 model_override，使用覆盖参数替代默认配置
                if model_override:
                    # 网关模式：只取 model 名，api_base/api_key 走网关
                    if should_use_gateway():
                        token = get_access_token()
                        model_name = self._get_model_name(
                            model=model_override.get("model"),
                        )
                        gateway_url = get_gateway_url()
                        llm_params = {
                            "api_key": token,
                            "api_base": gateway_url + "/" if gateway_url else None,
                            "extra_body": {"user_token": token} if token else {},
                        }
                    else:
                        override_base = model_override.get("api_base", "")
                        override_key = model_override.get("api_key", "")
                        model_name = self._get_model_name(
                            model=model_override.get("model"),
                            base_url=override_base,
                            provider=model_override.get("provider"),
                        )
                        llm_params = {
                            "api_key": override_key,
                            "api_base": override_base.rstrip("/") + "/" if override_base else None,
                        }
                    logger.info(f"使用覆盖模型: {model_name}, api_base: {llm_params.get('api_base')}")
                else:
                    llm_params = self._get_llm_params()
                    model_name = self._get_model_name()

                # 诊断日志：打印认证状态和 token 前缀
                _tk = naga_auth.get_access_token()
                logger.debug(f"[LLM] attempt={attempt} is_auth={naga_auth.is_authenticated()} "
                             f"token_prefix={_tk[:20] + '...' if _tk else 'None'} "
                             f"api_key_prefix={str(llm_params.get('api_key', ''))[:20]}... "
                             f"api_base={llm_params.get('api_base')}")

                config_error = self._local_api_config_error(llm_params)
                if config_error:
                    yield self._format_sse_chunk("content", config_error)
                    return

                prepared_messages = self._prepare_messages_for_model(
                    messages,
                    model_name,
                    str(llm_params.get("api_base") or ""),
                    model_override.get("provider") if model_override else get_config().api.provider,
                )
                call_params = {
                    "model": model_name,
                    "messages": prepared_messages,
                    "temperature": self._normalize_temperature(model_name, temperature),
                    "max_tokens": get_config().api.max_tokens if hasattr(get_config().api, "max_tokens") else None,
                    "stream": True,
                    "timeout": 120,
                    "stream_timeout": 120,
                    "num_retries": 0,
                    "enable_thinking": enable_thinking,
                    **llm_params
                }
                if tools:
                    call_params["tools"] = tools
                    if get_config().api.api_format != "anthropic":
                        call_params["parallel_tool_calls"] = True

                response = await self._acompletion_thinking(**call_params)

                # 累积器：tool_calls 增量拼接
                pending_tool_calls: dict[int, dict[str, str]] = {}  # {index: {id, name, arguments}}
                saw_content = False
                saw_reasoning = False
                final_finish_reason: str | None = None

                async for chunk in response:
                    if not chunk.choices:
                        continue

                    choice = chunk.choices[0]
                    final_finish_reason = getattr(choice, "finish_reason", None) or final_finish_reason
                    delta = choice.delta

                    # 处理 reasoning_content（思考过程）
                    reasoning = getattr(delta, "reasoning_content", None)
                    if reasoning:
                        saw_reasoning = True
                        yield self._format_sse_chunk("reasoning", reasoning)

                    # 处理 content（正式回答）
                    content = getattr(delta, "content", None)
                    if content:
                        saw_content = True
                        yield self._format_sse_chunk("content", content)

                    # 处理 tool_calls delta（原生 function calling）
                    tc_deltas = getattr(delta, "tool_calls", None)
                    if tc_deltas:
                        for tc in tc_deltas:
                            idx = tc.index
                            if idx not in pending_tool_calls:
                                pending_tool_calls[idx] = {"id": "", "name": "", "arguments": ""}
                            if tc.id:
                                pending_tool_calls[idx]["id"] = tc.id
                            if tc.function:
                                if tc.function.name:
                                    pending_tool_calls[idx]["name"] = tc.function.name
                                if tc.function.arguments:
                                    pending_tool_calls[idx]["arguments"] += tc.function.arguments

                # 流结束后，如果有 tool_calls，yield 一个完整事件
                if pending_tool_calls:
                    import json
                    calls = [pending_tool_calls[i] for i in sorted(pending_tool_calls)]
                    yield self._format_sse_chunk("tool_calls_native", json.dumps(calls, ensure_ascii=False))

                if not saw_content and not saw_reasoning and not pending_tool_calls:
                    logger.warning(
                        "[LLM] 流式调用返回空响应: model=%s attempt=%s/%s finish_reason=%s",
                        model_name,
                        attempt + 1,
                        max_attempts,
                        final_finish_reason,
                    )
                    if attempt < max_attempts - 1:
                        continue
                    yield self._format_sse_chunk(
                        "content",
                        "模型服务返回空响应（无正文、无思考、无工具调用）。请稍后重试，或检查当前模型、API Key 与网关状态。",
                    )

                # 流式响应正常完成，跳出重试循环
                _finish_router(True)
                return

            except litellm.AuthenticationError as e:
                _tk = naga_auth.get_access_token()
                # 只记录 token 长度与哈希前缀，避免明文访问令牌写入日志
                _tk_sha = hashlib.sha256(_tk.encode()).hexdigest()[:12] if _tk else None
                logger.error(f"LLM 401 诊断: attempt={attempt} is_auth={naga_auth.is_authenticated()} "
                             f"token={'set(len=' + str(len(_tk)) + ', sha256=' + _tk_sha + ')' if _tk else 'None'} "
                             f"has_refresh={naga_auth.has_refresh_token()}")
                if not auth_retried and naga_auth.is_authenticated():
                    auth_retried = True
                    logger.warning(f"LLM 调用 401，尝试刷新 token 后重试: {e}")
                    try:
                        result = await naga_auth.refresh()
                        new_token = result.get("access_token")
                        # 通过 SSE 推送新 token 给前端，避免前端旧 token 轮询覆盖后端新 token
                        if new_token:
                            yield self._format_sse_chunk("token_refreshed", new_token)
                        logger.info("Token 刷新成功，重试 LLM 调用")
                        continue  # 重试
                    except Exception as refresh_err:
                        logger.error(f"Token 刷新失败: {refresh_err}")
                # 刷新失败或已刷新过 → 通知前端触发重新登录
                logger.error(f"流式聊天认证失败: {e}")
                _finish_router(False, error="auth_expired")
                yield self._format_sse_chunk("auth_expired", "登录已过期，请重新登录")
                return

            except (litellm.APIConnectionError, litellm.ServiceUnavailableError, litellm.Timeout) as e:
                # 连接错误 / 流中断 / 超时 → 重试
                if attempt < max_attempts - 1:
                    logger.warning(f"[LLM] 流式调用连接异常 (attempt {attempt + 1}/{max_attempts})，重试中: {e}")
                    import asyncio
                    await asyncio.sleep(1)  # 短暂等待后重试
                    continue
                logger.error(f"[LLM] 流式调用连接异常，已耗尽重试次数: {e}")
                _finish_router(False, error="connection")
                yield self._format_sse_chunk("content", f"流式调用出错（连接异常，已重试 {max_attempts} 次）: {str(e)}")
                return

            except Exception as e:
                logger.error(f"流式聊天调用失败: {e}")
                _finish_router(False, error=type(e).__name__)
                yield self._format_sse_chunk("content", f"流式调用出错: {str(e)}")
                return

    def _format_sse_chunk(self, chunk_type: str, text: str) -> str:
        """格式化 SSE 数据块

        Args:
            chunk_type: "content" 或 "reasoning"
            text: 文本内容

        Returns:
            SSE 格式的数据块
        """
        import json

        data = {"type": chunk_type, "text": text}
        return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"


# 全局LLM服务实例
_llm_service: LLMService | None = None


def get_llm_service() -> LLMService:
    """获取全局LLM服务实例"""
    global _llm_service
    if _llm_service is None:
        _llm_service = LLMService()
    return _llm_service


# 创建独立的LLM服务API
llm_app = FastAPI(title="LLM Service API", description="LLM服务API", version="1.0.0")


@llm_app.post("/llm/chat")
async def llm_chat(request: dict[str, Any]):
    """LLM聊天接口 - 为其他模块提供LLM调用服务"""
    try:
        prompt = request.get("prompt", "")
        temperature = request.get("temperature", 0.7)

        if not prompt:
            raise HTTPException(status_code=400, detail="prompt参数不能为空")

        llm_service = get_llm_service()
        response = await llm_service.get_response(prompt, temperature)

        return {"status": "success", "response": response, "temperature": temperature}

    except Exception as e:
        logger.error(f"LLM聊天接口异常: {e}")
        raise HTTPException(status_code=500, detail="LLM服务异常")
