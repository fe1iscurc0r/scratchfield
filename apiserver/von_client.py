"""Von 决策模型客户端 — 判决书自动打标推理后端（卷164）。

Von（github.com/wfzyx/von，Apache-2.0）是自托管的决策模型服务，协议
``/v1/systemone`` 与 TypeSafe Jev 云 API 兼容（战略备份位：云端切换零改码）。

设计要点
--------
- Von 是**外部服务**（与 Ollama 同等地位），apiserver **不负责拉起** ``von serve``；
- 启动/调用前**探活**，离线则打标功能降级禁用，**不炸服务**；
- **断路器**：连续失败达阈值后熔断，冷却期内直接快速失败；冷却后**半开**探测；
- 单问题超时（默认 10s）。

协议
----
``POST {endpoint}/v1/systemone``::

    {
      "state":     {"context": "....", ...},     # 决策上下文（喂料）
      "questions": {"案由分类": {"type": "choice", "options": [...]}, ...}
    }

响应::

    {
      "answers": {
        "案由分类": {"value": "合同纠纷", "confidence": 0.87,
                     "probs": {"合同纠纷": 0.87, ...}},
        "是否指导性案例": {"value": true, "confidence": 0.91}
      }
    }

问题类型：``boolean`` / ``choice`` / ``score``。
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Any

logger = logging.getLogger(__name__)

#: 问题类型白名单。
QUESTION_TYPES = ("boolean", "choice", "score")

#: 默认端点（与 config 默认一致，运行时以 config 为准）。
DEFAULT_ENDPOINT = "http://127.0.0.1:8001"


class VonError(RuntimeError):
    """Von 调用失败（网络/协议/超时）。"""


class VonCircuitOpen(VonError):
    """断路器处于熔断态，快速失败。"""


class VonUnavailable(VonError):
    """Von 未启用或探活失败（功能降级）。"""


class VonClient:
    """Von ``/v1/systemone`` 客户端（含断路器和探活）。

    线程安全：断路器状态用 ``threading.Lock`` 保护（打标可能在工作线程运行）。
    """

    def __init__(
        self,
        endpoint: str | None = None,
        *,
        timeout: float | None = None,
        breaker_threshold: int | None = None,
        breaker_cooldown: float | None = None,
        enabled: bool | None = None,
    ) -> None:
        self._override_endpoint = endpoint
        self._override_timeout = timeout
        self._override_threshold = breaker_threshold
        self._override_cooldown = breaker_cooldown
        self._override_enabled = enabled

        self._lock = threading.Lock()
        self._fail_count = 0
        self._open_until = 0.0
        self._last_probe_ok: bool | None = None
        self._last_probe_at = 0.0

    # ── 配置（每次读取，支持热更新） ──

    def _cfg(self) -> Any:
        from system.config import get_config

        return get_config().von

    @property
    def enabled(self) -> bool:
        if self._override_enabled is not None:
            return self._override_enabled
        try:
            return bool(self._cfg().enabled)
        except Exception:  # noqa: BLE001 - 配置不可用时保守禁用
            return False

    @property
    def endpoint(self) -> str:
        if self._override_endpoint:
            return self._override_endpoint.rstrip("/")
        try:
            return str(self._cfg().endpoint).rstrip("/")
        except Exception:  # noqa: BLE001
            return DEFAULT_ENDPOINT

    @property
    def timeout(self) -> float:
        if self._override_timeout is not None:
            return float(self._override_timeout)
        try:
            return float(self._cfg().timeout)
        except Exception:  # noqa: BLE001
            return 10.0

    @property
    def breaker_threshold(self) -> int:
        if self._override_threshold is not None:
            return int(self._override_threshold)
        try:
            return int(self._cfg().breaker_threshold)
        except Exception:  # noqa: BLE001
            return 5

    @property
    def breaker_cooldown(self) -> float:
        if self._override_cooldown is not None:
            return float(self._override_cooldown)
        try:
            return float(self._cfg().breaker_cooldown)
        except Exception:  # noqa: BLE001
            return 60.0

    # ── 断路器状态 ──

    def _circuit_open(self) -> bool:
        """熔断中返回 True（冷却期内）。"""
        with self._lock:
            if self._open_until and time.monotonic() < self._open_until:
                return True
            # 冷却结束 → 半开（清空 open_until，下次真实调用探测）
            if self._open_until and time.monotonic() >= self._open_until:
                self._open_until = 0.0
            return False

    def _record_success(self) -> None:
        with self._lock:
            self._fail_count = 0
            self._open_until = 0.0
            self._last_probe_ok = True
            self._last_probe_at = time.monotonic()

    def _record_failure(self) -> None:
        with self._lock:
            self._fail_count += 1
            self._last_probe_ok = False
            self._last_probe_at = time.monotonic()
            if self._fail_count >= self.breaker_threshold:
                self._open_until = time.monotonic() + self.breaker_cooldown
                logger.warning(
                    "[von] 连续失败 %d 次，熔断 %.0fs",
                    self._fail_count, self.breaker_cooldown,
                )

    @property
    def breaker_state(self) -> str:
        """``closed`` / ``open`` / ``half_open``。"""
        with self._lock:
            if self._open_until and time.monotonic() < self._open_until:
                return "open"
            if self._fail_count > 0:
                return "half_open"
            return "closed"

    def reset_breaker(self) -> None:
        """重置断路器（测试/运维用）。"""
        with self._lock:
            self._fail_count = 0
            self._open_until = 0.0

    # ── 探活 ──

    def is_alive(self, *, force: bool = False, cache_ttl: float = 10.0) -> bool:
        """探测 Von 是否在线（结果缓存 ``cache_ttl`` 秒，避免频繁探活）。

        离线**不抛异常**，返回 False（调用方据此降级）。
        """
        if not self.enabled:
            return False
        now = time.monotonic()
        with self._lock:
            if (
                not force
                and self._last_probe_at
                and (now - self._last_probe_at) < cache_ttl
            ):
                return bool(self._last_probe_ok)

        ok = self._probe()
        with self._lock:
            self._last_probe_ok = ok
            self._last_probe_at = time.monotonic()
        return ok

    def _probe(self) -> bool:
        """实际探活：``GET {endpoint}/v1/systemone/health``（失败退回根路径）。"""
        try:
            import httpx
        except ImportError:  # pragma: no cover - httpx 是核心依赖
            return False
        for path in ("/v1/systemone/health", "/health", "/"):
            try:
                with httpx.Client(timeout=min(self.timeout, 5.0)) as client:
                    resp = client.get(self.endpoint + path)
                if resp.status_code < 500:
                    return True
            except Exception:  # noqa: BLE001 - 探活失败即离线
                continue
        return False

    # ── 调用 ──

    def ask(
        self,
        state: dict[str, Any],
        questions: dict[str, Any],
        *,
        timeout: float | None = None,
    ) -> dict[str, Any]:
        """调用 ``/v1/systemone``，返回 ``{"answers": {...}}``。

        :raises VonUnavailable: 未启用或断路器熔断。
        :raises VonError: 网络/协议/超时错误。
        """
        if not self.enabled:
            raise VonUnavailable("Von 打标未启用（von.enabled=false）")
        if self._circuit_open():
            raise VonCircuitOpen(
                f"Von 断路器熔断中（{self.breaker_cooldown:.0f}s 后重试）"
            )
        self._validate_questions(questions)

        try:
            import httpx
        except ImportError as exc:  # pragma: no cover
            raise VonError("缺少 httpx 依赖") from exc

        url = self.endpoint + "/v1/systemone"
        payload = {"state": state or {}, "questions": questions}
        try:
            with httpx.Client(timeout=timeout or self.timeout) as client:
                resp = client.post(url, json=payload)
            if resp.status_code >= 400:
                raise VonError(f"HTTP {resp.status_code}: {resp.text[:200]}")
            data = resp.json()
        except VonError:
            self._record_failure()
            raise
        except Exception as exc:  # noqa: BLE001 - 网络/解析异常统一处理
            self._record_failure()
            raise VonError(f"Von 调用失败: {type(exc).__name__}: {exc}") from exc

        answers = data.get("answers")
        if not isinstance(answers, dict):
            self._record_failure()
            raise VonError(f"Von 响应缺少 answers 字段: {str(data)[:200]}")

        self._record_success()
        return {"answers": answers, "raw": data}

    @staticmethod
    def _validate_questions(questions: dict[str, Any]) -> None:
        if not isinstance(questions, dict) or not questions:
            raise VonError("questions 不能为空")
        for name, spec in questions.items():
            if not isinstance(spec, dict):
                raise VonError(f"问题 {name!r} 定义必须是对象")
            qtype = spec.get("type")
            if qtype not in QUESTION_TYPES:
                raise VonError(
                    f"问题 {name!r} 类型 {qtype!r} 不支持（允许 {QUESTION_TYPES}）"
                )
            if qtype == "choice":
                opts = spec.get("options")
                if not isinstance(opts, list) or not opts:
                    raise VonError(f"choice 问题 {name!r} 必须提供非空 options")

    def status(self) -> dict[str, Any]:
        """供前端状态徽章使用的精简状态。"""
        alive = self.is_alive() if self.enabled else False
        return {
            "enabled": self.enabled,
            "alive": alive,
            "endpoint": self.endpoint,
            "breaker": self.breaker_state,
            "message": (
                "Von 在线，可自动打标" if alive
                else ("Von 离线：请启动 von serve 后可用" if self.enabled
                      else "Von 打标已禁用")
            ),
        }


#: 模块级单例（复用断路器状态）。
_default_client: VonClient | None = None


_default_client_lock = threading.Lock()


def get_von_client() -> VonClient:
    """获取全局 VonClient 单例。"""
    global _default_client
    if _default_client is None:
        with _default_client_lock:
            if _default_client is None:
                _default_client = VonClient()
    return _default_client


def reset_von_client() -> None:
    """重置单例（测试用）。"""
    global _default_client
    _default_client = None
