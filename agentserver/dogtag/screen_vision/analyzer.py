"""
屏幕感知分析器
负责调用screen_vision并分析结果
"""

import asyncio
import base64
import hashlib
import io
import json
import logging
import time
from typing import Any, Dict, List, Optional

import httpx

from .config import ProactiveVisionConfig, TriggerRule

logger = logging.getLogger(__name__)

# 尝试导入imagehash（用于差异检测）
try:
    import imagehash
    from PIL import Image
    IMAGEHASH_AVAILABLE = True
except ImportError:
    IMAGEHASH_AVAILABLE = False
    logger.warning(
        "[ScreenVision] imagehash库未安装，差异检测将降级到简单模式。"
        "安装命令: pip install imagehash pillow"
    )


class ProactiveVisionAnalyzer:
    """主动视觉分析器"""

    def __init__(self, config: ProactiveVisionConfig):
        self.config = config
        self._screenshot_cache: dict[str, Any] | None = None
        self._cache_time = 0.0
        self._last_screenshot_hash: str | None = None  # 上次截图的hash（pHash或简单hash）
        self._last_screen_description: str | None = None  # 上次屏幕描述（用于规则匹配缓存）
        self._screen_unchanged_count = 0  # 屏幕未变化计数
        self._total_checks = 0  # 总检查次数
        self._skipped_checks = 0  # 跳过的检查次数（差异检测节省的AI调用）
        self._http_client: httpx.AsyncClient | None = None

    def _get_http_client(self) -> httpx.AsyncClient:
        """获取或创建共享 httpx 客户端"""
        if self._http_client is None or self._http_client.is_closed:
            self._http_client = httpx.AsyncClient(timeout=30.0)
        return self._http_client

    async def close(self):
        """关闭共享 httpx 客户端"""
        if self._http_client and not self._http_client.is_closed:
            await self._http_client.aclose()
            self._http_client = None

    async def analyze_screen(self):
        """分析当前屏幕并决定是否触发"""
        from .metrics import get_metrics

        metrics = get_metrics()
        check_start = time.time()

        self._total_checks += 1
        logger.debug(f"[ScreenVision] 开始屏幕分析 (总检查: {self._total_checks})")

        # 1. 仅截图（不调用AI分析）
        screenshot_start = time.time()
        screenshot_data_url = await self._capture_screenshot()
        screenshot_duration = time.time() - screenshot_start

        if not screenshot_data_url:
            logger.warning("[ScreenVision] 截图失败")
            metrics.record_screenshot(screenshot_duration, error=True)
            metrics.record_check(time.time() - check_start, skipped=False)
            return

        metrics.record_screenshot(screenshot_duration, error=False)

        # 2. 计算截图hash并进行差异检测
        if self.config.diff_detection_enabled:
            hash_start = time.time()
            current_hash = self._calculate_screenshot_hash(screenshot_data_url)
            hash_duration = time.time() - hash_start
            logger.debug(f"[ScreenVision] Hash计算耗时: {hash_duration*1000:.1f}ms")

            if current_hash and self._last_screenshot_hash:
                # 比较hash
                is_similar = self._compare_hashes(current_hash, self._last_screenshot_hash)

                if is_similar:
                    # 屏幕内容未显著变化，跳过AI分析
                    self._screen_unchanged_count += 1
                    self._skipped_checks += 1

                    # 记录跳过的检查
                    metrics.record_check(time.time() - check_start, skipped=True)

                    # 每10次重复才记录一次日志，避免日志刷屏
                    if self._screen_unchanged_count % 10 == 0:
                        skip_rate = (self._skipped_checks / self._total_checks) * 100
                        logger.info(
                            f"[ScreenVision] 屏幕未显著变化 (连续{self._screen_unchanged_count}次)，跳过分析 "
                            f"(节省AI调用: {skip_rate:.1f}%)"
                        )
                    return

            # 屏幕发生显著变化，更新hash
            if self._screen_unchanged_count > 0:
                logger.info("[ScreenVision] 检测到屏幕显著变化，调用AI分析")
            self._screen_unchanged_count = 0
            self._last_screenshot_hash = current_hash

        # 3. 调用AI分析屏幕内容
        ai_start = time.time()
        screen_description = await self._analyze_screenshot_with_ai(screenshot_data_url)
        ai_duration = time.time() - ai_start

        if not screen_description:
            logger.warning("[ScreenVision] AI分析失败")
            metrics.record_check(time.time() - check_start, skipped=False)
            return

        logger.debug(f"[ScreenVision] AI分析耗时: {ai_duration:.2f}s, 结果: {screen_description[:100]}...")
        self._last_screen_description = screen_description

        # 4. 根据模式执行规则匹配
        matched_rules = []
        if self.config.analysis_mode == "rule_only":
            matched_rules = self._match_rules(screen_description)
        elif self.config.analysis_mode == "always":
            llm_start = time.time()
            matched_rules = await self._ai_match_rules(screen_description)
            metrics.record_llm_analysis(time.time() - llm_start)
        else:  # smart
            matched_rules = self._match_rules(screen_description)
            if not matched_rules:
                llm_start = time.time()
                matched_rules = await self._ai_match_rules(screen_description)
                metrics.record_llm_analysis(time.time() - llm_start)

        # 5. 触发匹配的规则
        if matched_rules:
            logger.info(f"[ScreenVision] 匹配到 {len(matched_rules)} 条规则")
            await self._trigger_rules(matched_rules, screen_description)
        else:
            logger.debug("[ScreenVision] 未匹配到任何规则")

        # 记录完整检查耗时
        metrics.record_check(time.time() - check_start, skipped=False)

    def _calculate_screenshot_hash(self, data_url: str) -> str | None:
        """计算截图的hash值（支持pHash/dHash/aHash）

        Args:
            data_url: base64格式的截图数据

        Returns:
            hash字符串，失败返回None
        """
        algorithm = self.config.diff_detection_algorithm

        # 如果选择none或imagehash不可用，降级到简单模式
        if algorithm == "none" or not IMAGEHASH_AVAILABLE:
            if algorithm != "none":
                logger.warning("[ScreenVision] imagehash不可用，降级到MD5 hash")
            # 简单MD5 hash（对base64数据直接hash）
            return hashlib.md5(data_url.encode('utf-8')).hexdigest()

        try:
            # 解析data_url
            header, b64data = data_url.split(",", 1)
            img_bytes = base64.b64decode(b64data)

            # 加载图像
            img = Image.open(io.BytesIO(img_bytes))

            # 根据算法计算hash
            if algorithm == "phash":
                img_hash = imagehash.phash(img, hash_size=8)
            elif algorithm == "dhash":
                img_hash = imagehash.dhash(img, hash_size=8)
            elif algorithm == "ahash":
                img_hash = imagehash.average_hash(img, hash_size=8)
            else:
                logger.warning(f"[ScreenVision] 未知hash算法: {algorithm}，降级到pHash")
                img_hash = imagehash.phash(img, hash_size=8)

            return str(img_hash)

        except Exception as e:
            logger.error(f"[ScreenVision] Hash计算失败: {e}，降级到MD5")
            # 降级到简单hash
            return hashlib.md5(data_url.encode('utf-8')).hexdigest()

    def _compare_hashes(self, hash1: str, hash2: str) -> bool:
        """比较两个hash是否相似

        Args:
            hash1: 第一个hash
            hash2: 第二个hash

        Returns:
            True表示相似，False表示不同
        """
        algorithm = self.config.diff_detection_algorithm

        # MD5 hash - 精确比较
        if algorithm == "none" or not IMAGEHASH_AVAILABLE:
            return hash1 == hash2

        try:
            # pHash/dHash/aHash - 汉明距离比较
            h1 = imagehash.hex_to_hash(hash1)
            h2 = imagehash.hex_to_hash(hash2)
            distance = h1 - h2

            # 距离小于等于阈值认为相似
            is_similar = distance <= self.config.diff_threshold
            if not is_similar:
                logger.debug(f"[ScreenVision] Hash距离: {distance} > 阈值{self.config.diff_threshold}，判定为变化")
            return is_similar

        except Exception as e:
            logger.error(f"[ScreenVision] Hash比较失败: {e}，降级到字符串比较")
            return hash1 == hash2

    def get_performance_stats(self) -> dict[str, Any]:
        """获取性能统计"""
        skip_rate = (self._skipped_checks / self._total_checks * 100) if self._total_checks > 0 else 0
        return {
            "total_checks": self._total_checks,
            "skipped_checks": self._skipped_checks,
            "effective_checks": self._total_checks - self._skipped_checks,
            "skip_rate_percent": round(skip_rate, 2),
            "current_unchanged_count": self._screen_unchanged_count,
        }

    async def _capture_screenshot(self) -> str | None:
        """仅截图，不进行AI分析

        Returns:
            base64格式的截图data_url，失败返回None
        """
        try:
            from guide_engine.screenshot_provider import get_screenshot_provider

            screenshot_provider = get_screenshot_provider()
            screenshot_result = screenshot_provider.capture_data_url()
            return screenshot_result.data_url

        except Exception as e:
            logger.error(f"[ScreenVision] 截图失败: {e}")
            return None

    async def _analyze_screenshot_with_ai(self, data_url: str) -> str | None:
        """使用AI分析截图内容

        Args:
            data_url: base64格式的截图

        Returns:
            AI分析的屏幕描述，失败返回None
        """
        from system.config import get_server_port

        mcp_port = get_server_port("mcp_server")
        url = f"http://127.0.0.1:{mcp_port}/call"

        payload = {
            "service_name": "screen_vision",
            "tool_name": "look_screen",
            "message": "简要描述当前屏幕上的主要内容和用户可能正在做什么。重点关注窗口标题、应用名称、明显的文字内容。",
            "params": {}
        }

        try:
            client = self._get_http_client()
            resp = await client.post(url, json=payload)
            if resp.status_code == 200:
                result = resp.json()
                if result.get("status") == "ok":
                    # 解析嵌套的JSON结果
                    inner_result_str = result.get("result", "{}")
                    inner_result = json.loads(inner_result_str)
                    if inner_result.get("status") == "success":
                        return inner_result.get("message", "")
            else:
                logger.warning(f"[ScreenVision] MCP服务返回错误: {resp.status_code}")
        except json.JSONDecodeError as e:
            logger.error(f"[ScreenVision] 解析screen_vision响应失败: {e}")
        except Exception as e:
            err_name = type(e).__name__
            if err_name == "ConnectError":
                logger.warning("[ScreenVision] 无法连接到MCP服务器，请检查服务是否启动")
            elif "Timeout" in err_name:
                logger.warning("[ScreenVision] 调用screen_vision超时")
            else:
                logger.error(f"[ScreenVision] 调用screen_vision失败: {e}")

        return None

    def _match_rules(self, screen_description: str) -> list[TriggerRule]:
        """基于关键词的规则匹配"""
        matched = []
        for rule in self.config.trigger_rules:
            if not rule.enabled:
                continue

            # 检查必须包含的关键词
            if rule.keywords:
                if not all(kw.lower() in screen_description.lower() for kw in rule.keywords):
                    continue

            # 检查不应包含的关键词
            if rule.absence_keywords:
                if any(kw.lower() in screen_description.lower() for kw in rule.absence_keywords):
                    continue

            matched.append(rule)
            logger.debug(f"[ScreenVision] 规则匹配成功: {rule.name}")

        return matched

    async def _ai_match_rules(self, screen_description: str) -> list[TriggerRule]:
        """使用AI进行智能规则匹配"""
        # 构建规则描述和启用的规则列表
        rules_desc = []
        enabled_rules = []
        for rule in self.config.trigger_rules:
            if rule.enabled:
                # 使用enabled_rules的索引作为编号
                rule_index = len(enabled_rules)
                rules_desc.append(f"{rule_index}. {rule.name}: {rule.scene_description}")
                enabled_rules.append(rule)

        if not rules_desc:
            return []

        prompt = f"""你是一个场景匹配助手。根据屏幕描述，判断哪些规则应该被触发。

当前屏幕描述：
{screen_description}

可用规则：
{chr(10).join(rules_desc)}

请返回应该触发的规则编号列表（JSON数组格式），如果没有匹配的规则，返回空数组。
只返回JSON，不要其他内容。

示例输出：[0, 2]
"""

        try:
            from apiserver.llm_service import get_llm_service
            llm_service = get_llm_service()

            response = await llm_service.chat_with_context_and_reasoning(
                messages=[{"role": "user", "content": prompt}],
            )

            # 解析AI返回的规则编号
            import re
            match = re.search(r'\[[\d,\s]*\]', response.content)
            if match:
                indices = json.loads(match.group())
                matched_rules = []
                for idx in indices:
                    if 0 <= idx < len(enabled_rules):
                        matched_rules.append(enabled_rules[idx])
                        logger.debug(f"[ScreenVision] AI匹配规则: {enabled_rules[idx].name}")
                return matched_rules
        except Exception as e:
            logger.error(f"[ScreenVision] AI规则匹配失败: {e}")

        return []

    async def _trigger_rules(self, rules: list[TriggerRule], context: str):
        """触发规则，向用户发送主动消息"""
        from .metrics import get_metrics
        from .trigger import get_proactive_trigger

        trigger = get_proactive_trigger()
        metrics = get_metrics()

        for rule in rules:
            try:
                success = await trigger.send_proactive_message(rule, context)
                if success:
                    metrics.record_rule_triggered(rule.rule_id)
            except Exception as e:
                logger.error(f"[ScreenVision] 触发规则 {rule.name} 失败: {e}")


# 全局单例
_analyzer: ProactiveVisionAnalyzer | None = None


def get_proactive_analyzer() -> ProactiveVisionAnalyzer | None:
    """获取分析器单例"""
    return _analyzer


def create_proactive_analyzer(config: ProactiveVisionConfig) -> ProactiveVisionAnalyzer:
    """创建并注册分析器单例（允许同步调用）

    注意：分析器是无状态的（除了缓存），替换旧实例是安全的。
    """
    global _analyzer
    if _analyzer is not None:
        logger.debug("[ScreenVision] 分析器已存在，将被替换")

    _analyzer = ProactiveVisionAnalyzer(config)
    return _analyzer
