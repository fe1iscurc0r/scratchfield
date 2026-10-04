"""B-03 · LLM 脱敏路由网关（卷132）。

   用户查询 → 敏感检测（本地正则，零外呼）
       ├─ 敏感   → Ollama 本地（数据不出机器）
       └─ 非敏感 → MiniMax 云端（能力更强）

**路由透明**：调用方只看到统一的 `{ok, text, route, model, ...}`，不感知底层。

三条设计纪律：

1. **检测先于外呼** —— 敏感判定完全在本地做（纯正则），不把原文先发给云端"问是否敏感"。
   否则脱敏本身就成了泄露通道。
2. **失败即降级到本地** —— 云端不可用时回落到 Ollama，而不是把敏感查询重发云端。
   宁可慢、不要在隐私上赌。
3. **判定可解释** —— 每次返回 `matched_rules`，便于审计为什么走了本地
   （B-04 的告警与审计依赖这一点）。

规则表在 `sensitivity_rules.yaml`，可热替换。注意这是**正则表不是 NER**，
姓名识别能力有限，不要当完备隐私检测用。
"""
from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any

__all__ = ["LLMGateway", "SensitivityClassifier", "load_rules", "ROUTE_OLLAMA", "ROUTE_MINIMAX"]

ROUTE_OLLAMA = "ollama"
ROUTE_MINIMAX = "minimax"

_DEFAULT_RULES_PATH = Path(__file__).with_name("sensitivity_rules.yaml")


# --------------------------------------------------------------------------- #
# 规则加载 + 分类
# --------------------------------------------------------------------------- #

def load_rules(path: str | Path | None = None) -> dict[str, Any]:
    """加载规则表。PyYAML 缺失或文件损坏时退回内置最小规则（不静默失效）。"""
    p = Path(path) if path is not None else _DEFAULT_RULES_PATH
    try:
        import yaml
        if p.exists():
            with p.open("r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
            if isinstance(data, dict):
                data.setdefault("strong", [])
                data.setdefault("specific", [])
                data.setdefault("allowlist", [])
                data.setdefault("routes", {})
                return data
    except Exception:                                       # noqa: BLE001
        pass
    return {"strong": [], "specific": [], "allowlist": [], "routes": {},
            "_warning": "规则表加载失败，敏感检测退化为「仅精确坐标」"}


class SensitivityClassifier:
    """敏感文本判定。命中断言顺序：strong > specific（allowlist 只抑制 specific）。"""

    def __init__(self, rules: dict[str, Any] | None = None,
                 rules_path: str | Path | None = None) -> None:
        self.rules = rules if rules is not None else load_rules(rules_path)
        self._strong = self._compile(self.rules.get("strong") or [])
        self._specific = self._compile(self.rules.get("specific") or [])
        self._allow = [str(x) for x in (self.rules.get("allowlist") or [])]

    @staticmethod
    def _compile(items: list[Any]) -> list[tuple[str, re.Pattern[str], str]]:
        out: list[tuple[str, re.Pattern[str], str]] = []
        for item in items:
            if isinstance(item, dict) and item.get("pattern"):
                try:
                    out.append((str(item.get("name") or "rule"),
                                re.compile(str(item["pattern"])),
                                str(item.get("hint") or "")))
                except re.error:
                    continue                                # 坏正则跳过，不让整表失效
        return out

    def classify(self, text: str) -> tuple[bool, list[dict[str, str]]]:
        """→ (是否敏感, 命中规则列表)。"""
        s = str(text or "")
        matched: list[dict[str, str]] = []
        for name, rx, hint in self._strong:
            if rx.search(s):
                matched.append({"rule": name, "hint": hint, "level": "strong"})
        if matched:
            return True, matched                          # 强信号：allowlist 不放行
        allowed = any(a and a in s for a in self._allow)
        if not allowed:
            for name, rx, hint in self._specific:
                if rx.search(s):
                    matched.append({"rule": name, "hint": hint, "level": "specific"})
        return bool(matched), matched

    def is_sensitive(self, text: str) -> bool:
        return self.classify(text)[0]

    def describe(self) -> dict[str, Any]:
        return {
            "strong_rules": [n for n, _, _ in self._strong],
            "specific_rules": [n for n, _, _ in self._specific],
            "allowlist": list(self._allow),
            "version": self.rules.get("version"),
            "warning": self.rules.get("_warning"),
        }


# --------------------------------------------------------------------------- #
# 网关
# --------------------------------------------------------------------------- #

class LLMGateway:
    """脱敏路由网关。`client` 可注入（httpx.Client 或其替身）。

    `minimax_key` 省略时读环境变量 `MINIMAX_API_KEY`；为空则**禁用云端路由**
    （全部走本地），不会因缺 key 把请求发出去。
    """

    def __init__(self, client: Any = None,
                 classifier: SensitivityClassifier | None = None,
                 rules_path: str | Path | None = None,
                 ollama_base_url: str = "http://localhost:11434",
                 ollama_model: str = "qwen2.5:7b",
                 minimax_base_url: str = "https://api.minimaxi.com/anthropic",
                 minimax_model: str = "MiniMax-Text-01",
                 minimax_key: str | None = None,
                 timeout: float = 60.0,
                 allow_network: bool = True) -> None:
        self._client = client
        self._owns_client = client is None
        self.classifier = classifier or SensitivityClassifier(rules_path=rules_path)
        self.ollama_base_url = ollama_base_url.rstrip("/")
        self.ollama_model = ollama_model
        self.minimax_base_url = minimax_base_url.rstrip("/")
        self.minimax_model = minimax_model
        self.minimax_key = minimax_key if minimax_key is not None else _env_key()
        self.timeout = timeout
        self.allow_network = bool(allow_network)
        self.calls: list[dict[str, Any]] = []              # 路由审计流水

    # ---- 基础设施 ----

    def _get_client(self) -> Any:
        if self._client is None:
            import httpx
            self._client = httpx.Client(timeout=self.timeout)
        return self._client

    def close(self) -> None:
        if self._client is not None and self._owns_client:
            try:
                self._client.close()
            except Exception:                               # noqa: BLE001
                pass
        self._client = None

    # ---- 敏感判定 ----

    def classify_sensitivity(self, text: str) -> bool:
        """工单要求的接口名。含具体地址/坐标 → True。"""
        return self.classifier.is_sensitive(text)

    # ---- 路由决策 ----

    def choose_route(self, text: str) -> tuple[str, list[dict[str, str]]]:
        """→ (route, matched_rules)。缺云端 key 时强制本地。"""
        sensitive, matched = self.classifier.classify(text)
        if sensitive:
            return ROUTE_OLLAMA, matched
        if not self.minimax_key:
            matched = matched + [{"rule": "no_cloud_key", "hint": "未配置云端 key，回落本地",
                                  "level": "route"}]
            return ROUTE_OLLAMA, matched
        return ROUTE_MINIMAX, matched

    # ---- 两种后端调用 ----

    def _call_ollama(self, messages: list[dict[str, str]],
                     system_prompt: str | None, model: str | None) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": model or self.ollama_model,
            "messages": ([{"role": "system", "content": system_prompt}] if system_prompt else [])
                        + messages,
            "stream": False,
        }
        resp = self._get_client().post(f"{self.ollama_base_url}/api/chat",
                                       json=payload, timeout=self.timeout)
        if getattr(resp, "status_code", 200) != 200:
            return {"ok": False, "error": f"http_{getattr(resp, 'status_code', '?')}"}
        data = resp.json() or {}
        text = ((data.get("message") or {}).get("content")
                or data.get("response") or "")
        return {"ok": True, "text": text, "model": payload["model"]}

    def _call_minimax(self, messages: list[dict[str, str]],
                      system_prompt: str | None, model: str | None) -> dict[str, Any]:
        if not self.minimax_key:
            return {"ok": False, "error": "missing_api_key"}
        payload: dict[str, Any] = {
            "model": model or self.minimax_model,
            "max_tokens": 1024,
            "messages": messages,
        }
        if system_prompt:
            payload["system"] = system_prompt
        headers = {
            "x-api-key": self.minimax_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }
        resp = self._get_client().post(f"{self.minimax_base_url}/v1/messages",
                                       json=payload, headers=headers, timeout=self.timeout)
        if getattr(resp, "status_code", 200) != 200:
            return {"ok": False, "error": f"http_{getattr(resp, 'status_code', '?')}"}
        data = resp.json() or {}
        parts = data.get("content") or []
        text = "".join(p.get("text", "") for p in parts if isinstance(p, dict))
        return {"ok": True, "text": text, "model": payload["model"]}

    # ---- 对外统一接口 ----

    def chat(self, messages: list[dict[str, Any]],
             system_prompt: str | None = None,
             force_route: str | None = None,
             model: str | None = None) -> dict[str, Any]:
        """统一聊天入口。返回 `{ok, text, route, model, sensitive, matched_rules, latency_ms}`。

        `force_route` 用于运维排查（`ollama` / `minimax`），会跳过敏感判定；
        正常业务不要用它，否则脱敏形同虚设。
        """
        msgs = [{"role": str(m.get("role", "user")), "content": str(m.get("content", ""))}
                for m in (messages or [])]
        probe = "\n".join(m["content"] for m in msgs)

        if force_route:
            route = ROUTE_OLLAMA if force_route == ROUTE_OLLAMA else ROUTE_MINIMAX
            sensitive, matched = self.classifier.classify(probe)
            matched = matched + [{"rule": "forced", "hint": f"强制路由 {route}", "level": "route"}]
        else:
            route, matched = self.choose_route(probe)
            sensitive = any(m.get("level") in ("strong", "specific") for m in matched)

        if not self.allow_network:
            result = {"ok": False, "error": "network_disabled"}
            route_used = route
        else:
            started = time.time()
            result = (self._call_ollama(msgs, system_prompt, model)
                      if route == ROUTE_OLLAMA
                      else self._call_minimax(msgs, system_prompt, model))
            route_used = route
            # 云端失败 → 回落本地（不把敏感内容再发云端的方向反过来）
            if not result.get("ok") and route == ROUTE_MINIMAX:
                fallback = self._call_ollama(msgs, system_prompt, model)
                if fallback.get("ok"):
                    fallback["fallback_from"] = ROUTE_MINIMAX
                    result = fallback
                    route_used = ROUTE_OLLAMA
            result["latency_ms"] = round((time.time() - started) * 1000, 1)

        record = {
            "route": route_used,
            "sensitive": sensitive,
            "matched_rules": matched,
            "ok": bool(result.get("ok")),
            "chars": len(probe),
            "ts": time.time(),
        }
        self.calls.append(record)

        out: dict[str, Any] = {
            "ok": bool(result.get("ok")),
            "text": result.get("text", ""),
            "route": route_used,
            "model": result.get("model", ""),
            "sensitive": sensitive,
            "matched_rules": matched,
        }
        for key in ("error", "latency_ms", "fallback_from"):
            if key in result:
                out[key] = result[key]
        return out

    # ---- 状态 ----

    def available_models(self) -> list[str]:
        """探测 Ollama 已拉取的模型；不可达返回空列表。"""
        if not self.allow_network:
            return []
        try:
            resp = self._get_client().get(f"{self.ollama_base_url}/api/tags", timeout=3.0)
            if getattr(resp, "status_code", 200) != 200:
                return []
            data = resp.json() or {}
            return [m.get("name", "") for m in (data.get("models") or []) if m.get("name")]
        except Exception:                                   # noqa: BLE001
            return []

    def route_status(self) -> dict[str, Any]:
        """`GET /api/llm/route-status` 的载荷。"""
        models = self.available_models()
        return {
            "ok": True,
            "routes": {
                "sensitive": {
                    "provider": ROUTE_OLLAMA,
                    "base_url": self.ollama_base_url,
                    "model": self.ollama_model,
                    "reachable": bool(models),
                    "available_models": models,
                },
                "nonsensitive": {
                    "provider": ROUTE_MINIMAX,
                    "base_url": self.minimax_base_url,
                    "model": self.minimax_model,
                    "configured": bool(self.minimax_key),
                },
            },
            "classifier": self.classifier.describe(),
            "recent_calls": self.calls[-20:],
            "call_count": len(self.calls),
        }


def _env_key() -> str | None:
    import os
    for name in ("MINIMAX_API_KEY", "SITAWARE_MINIMAX_KEY"):
        val = os.environ.get(name)
        if val:
            return val
    return None
