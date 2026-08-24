from __future__ import annotations

import json
import logging
import time as _time
from typing import Any

try:
    from guide_engine.models import get_guide_engine_settings
    from guide_engine.screenshot_provider import compress_screenshot_data_url, get_screenshot_provider
    _GUIDE_ENGINE_AVAILABLE = True
except Exception:
    _GUIDE_ENGINE_AVAILABLE = False
    get_guide_engine_settings = None
    compress_screenshot_data_url = None
    get_screenshot_provider = None

logger = logging.getLogger("ScreenVisionAgent")


class ScreenVisionAgent:
    """屏幕视觉代理 - 实时获取并分析用户屏幕内容

    适用场景：
    1. 用户询问屏幕上的元素（如"右边是什么"、"这个界面怎么操作"）
    2. 需要基于可见内容提供建议（如"这关怎么过"）
    3. 用户请求查看/分析/识别屏幕
    4. 需要确认界面状态（如"我现在在哪个页面"）
    5. 疑难排查（如"为什么点不了"）
    """
    name = "ScreenVision Agent"

    async def handle_handoff(self, task: dict[str, Any]) -> str:
        tool_name = str(task.get("tool_name") or "").strip()
        if tool_name != "look_screen":
            return json.dumps(
                {"status": "error", "message": f"未知工具: {tool_name}。可用工具: look_screen", "data": {}},
                ensure_ascii=False,
            )

        if not _GUIDE_ENGINE_AVAILABLE:
            return json.dumps(
                {"status": "error", "message": "屏幕视觉模块未启用（guide_engine 已禁用）", "data": {}},
                ensure_ascii=False,
            )

        query = str(task.get("query") or task.get("content") or task.get("message") or "描述屏幕上的内容").strip()

        t_start = _time.monotonic()

        try:
            t0 = _time.monotonic()
            screenshot = get_screenshot_provider().capture_data_url()
            t_screenshot = _time.monotonic() - t0
            logger.info(f"[ScreenVision] 截图完成: {t_screenshot:.2f}s, source={screenshot.source}, "
                        f"size={screenshot.width}x{screenshot.height}")
        except Exception as exc:
            logger.error(f"[ScreenVision] 截图失败: {exc}")
            return json.dumps(
                {"status": "error", "message": f"截图失败: {exc}", "data": {}},
                ensure_ascii=False,
            )

        # 压缩截图：缩放到 1280px 宽 + JPEG q80，体积缩小 30-40 倍
        try:
            t0 = _time.monotonic()
            raw_len = len(screenshot.data_url)
            compressed_url = compress_screenshot_data_url(screenshot.data_url, max_width=1280, quality=80)
            compressed_len = len(compressed_url)
            t_compress = _time.monotonic() - t0
            logger.info(f"[ScreenVision] 图片压缩: {t_compress:.2f}s, "
                        f"{raw_len // 1024}KB → {compressed_len // 1024}KB "
                        f"(缩小 {raw_len / max(compressed_len, 1):.1f}x)")
        except Exception as exc:
            logger.warning(f"[ScreenVision] 图片压缩失败，使用原图: {exc}")
            compressed_url = screenshot.data_url

        try:
            t0 = _time.monotonic()
            description = await self._analyze_screenshot(query, compressed_url)
            t_llm = _time.monotonic() - t0
            logger.info(f"[ScreenVision] 视觉LLM分析完成: {t_llm:.2f}s, 结果长度={len(description)}")
        except Exception as exc:
            logger.error(f"[ScreenVision] 视觉分析失败: {exc}")
            return json.dumps(
                {"status": "error", "message": f"视觉分析失败: {exc}", "data": {}},
                ensure_ascii=False,
            )

        t_total = _time.monotonic() - t_start
        logger.info(f"[ScreenVision] 总耗时: {t_total:.2f}s (截图={t_screenshot:.2f}s + LLM={t_llm:.2f}s)")

        return json.dumps(
            {"status": "success", "message": description, "data": {"source": screenshot.source}},
            ensure_ascii=False,
        )

    async def _analyze_screenshot(self, query: str, image_data_url: str) -> str:
        from apiserver.llm_service import get_llm_service

        settings = get_guide_engine_settings() if _GUIDE_ENGINE_AVAILABLE else None
        llm_service = get_llm_service()

        system_prompt = (
            "你是一个屏幕视觉助手。用户会给你一张屏幕截图，请根据用户的问题分析截图内容。"
            "描述要准确、简洁，重点关注用户问题相关的内容。"
        )

        user_content: list[dict[str, Any]] = [
            {"type": "text", "text": query},
            {"type": "image_url", "image_url": {"url": image_data_url}},
        ]

        messages: list[dict[str, Any]] = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ]

        overrides = {}
        if settings:
            overrides = {
                "model_override": settings.game_guide_llm_api_model,
                "api_key_override": settings.game_guide_llm_api_key,
                "api_base_override": settings.game_guide_llm_api_base_url,
                "provider_hint": settings.game_guide_llm_api_type,
            }

        response = await llm_service.chat_with_context_and_reasoning_with_overrides(
            messages=messages,
            **overrides,
        )
        return response.content
