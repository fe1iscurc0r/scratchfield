"""admin 运维端点 —— 模型峰谷状态只读探针（工单 228 任务一）。

## 为什么有这个端点

云服已上线「峰谷双轨」（按工作日时段切换 provider / 模型）。但 gateway 重启后，
**当前实际生效的 provider / 模型 / 降级链对外不可见** —— 运维只能登录机器翻配置。
本路由补一个**纯只读**探针，把这件事变成一次 ``GET /admin/model_state``。

## ⚠️ 与工单预设的偏差（实测 2026-10-13）

工单假设配置在 ``~/.hermes/config.yaml``，字段为 ``model.default`` /
``model.provider`` / ``fallback_providers``。实测（承接工单 210
``tools/switch_llm_provider.py`` 头注的同一条纠正结论）：

- **本仓/本机无 ``~/.hermes/config.yaml``**；
- 权威配置 = ``system.config.get_config_path()`` → ``config.json`` 的
  ``api.{base_url, model, provider}``（另含 ``use_gateway`` / ``api_format``）；
- ``fallback_providers`` 在 ``config.json`` 里**不存在**（仓内只有 UI 的
  ``fallback_image``）。

所以读取优先级定为：**仓内 config 为主口径**，``~/.hermes/config.yaml`` **仅作可选回退**
（存在才读）。返回体用 ``sources`` 字段如实标注每个值的来源，避免"看着有值、
其实读的是另一处"这种误导 —— 同一假设在本仓已经连续出现过两次（工单 210 / 228），
标注来源是为了下次别再踩。

## 设计约束

- **纯只读**：不写任何状态、不 emit 事件、不动现有 health 路由；
- 任何一路读不到都**降级返回**而不是 500 —— 探针本身不该成为新的故障点。
"""
from __future__ import annotations

import importlib.util
import json
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter

router = APIRouter(tags=["admin"])

# ── 峰谷口径 ───────────────────────────────────────────────────────────────
# 与切换脚本同口径：**工作日** 09:00-12:00 与 14:00-18:00 为峰段（左闭右开）。
# ⚠️ `tools/peak_switch.sh` 只存在于服务器本地、**不在本仓**（2026-10-13 实测），
#    故此处把口径固化成常量 + 单测，作为可核对的事实来源。
PEAK_WINDOWS: tuple[tuple[int, int], ...] = ((9 * 60, 12 * 60), (14 * 60, 18 * 60))

# `~/.hermes/...` 是服务器侧路径；本仓无该目录，仅作可选回退。
DEFAULT_HERMES_CONFIG = Path("~/.hermes/config.yaml")
DEFAULT_PEAK_LOG = Path("~/.hermes/cron/output/peak_switch.log")

# capability 探测：这些 SDK 装没装，决定当前能走哪条 provider 链路。
CAPABILITY_MODULES: tuple[str, ...] = ("anthropic", "openai", "minimax", "deepseek", "zhipuai")

_PEAK_TOKENS = ("peak", "峰")
_VALLEY_TOKENS = ("valley", "off-peak", "offpeak", "谷")


def _default_config_path() -> Path | None:
    """仓内权威配置路径（``system.config.get_config_path()``）。

    单独包一层是为了可注入/可测：测试直接传 ``config_path``，不碰真实配置。
    """
    try:
        from system.config import get_config_path

        return Path(get_config_path())
    except Exception:  # noqa: BLE001 - 探针不因配置模块不可用而崩
        return None


def _load_json(path: Path) -> dict[str, Any] | None:
    """读 JSON；坏文件/缺文件一律归为"读不到"（返回 None）。"""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return None
    return data if isinstance(data, dict) else None


def _load_yaml(path: Path) -> dict[str, Any] | None:
    """读 YAML（PyYAML 可选：不可用就返回 None，不炸链）。"""
    try:
        import yaml
    except Exception:  # noqa: BLE001
        return None
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return None
    return data if isinstance(data, dict) else None


def _module_installed(name: str) -> bool:
    """探测模块是否可导入。

    注意 ``find_spec("a.b")`` 在**父包不可导入时抛异常**而不是返回 None
    （CPython 明文行为；本仓 ``tests/conftest.py`` 为同一坑打过补丁）—— 这里统一兜住。
    """
    try:
        return importlib.util.find_spec(name) is not None
    except (ImportError, ValueError):
        return False


def detect_capabilities() -> list[str]:
    """当前环境实际可用的 provider SDK 列表。"""
    return [name for name in CAPABILITY_MODULES if _module_installed(name)]


def is_weekday_peak(moment: datetime) -> bool:
    """工作日峰段判定（与切换脚本同口径：09-12 / 14-18，左闭右开）。"""
    if moment.weekday() >= 5:  # 5=周六 6=周日
        return False
    minutes = moment.hour * 60 + moment.minute
    return any(low <= minutes < high for low, high in PEAK_WINDOWS)


def _peak_from_log(path: Path) -> bool | None:
    """从 ``peak_switch.log`` 末条记录推断峰/谷；无法判定时返回 None。"""
    try:
        raw = path.read_text(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        return None
    lines = [ln.strip() for ln in raw.splitlines() if ln.strip()]
    if not lines:
        return None
    last = lines[-1].lower()
    if any(tok in last for tok in _VALLEY_TOKENS):
        return False
    if any(tok in last for tok in _PEAK_TOKENS):
        return True
    return None


def resolve_model_state(
    *,
    config_path: str | Path | None = None,
    hermes_path: str | Path | None = None,
    log_path: str | Path | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """组装 ``GET /admin/model_state`` 的返回体（纯函数：全部路径可注入、可测）。

    :param config_path: 仓内 config.json 路径；None → 取 ``system.config.get_config_path()``
    :param hermes_path: 服务器侧 ``~/.hermes/config.yaml``；None → 取默认（可不存在）
    :param log_path:    服务器侧 ``peak_switch.log``；None → 取默认（可不存在）
    :param now:         注入"当前时间"（测试用）；None → ``datetime.now()``
    """
    moment = now or datetime.now()
    sources: dict[str, str] = {}

    # ── 主口径：仓内 config.json ───────────────────────────────────────────
    cfg_file = Path(config_path) if config_path else _default_config_path()
    api: dict[str, Any] = {}
    if cfg_file is not None and cfg_file.exists():
        data = _load_json(cfg_file) or {}
        raw_api = data.get("api")
        api = raw_api if isinstance(raw_api, dict) else {}
        sources["config"] = str(cfg_file)
    else:
        sources["config"] = "missing"

    # ── 可选回退：服务器侧 ~/.hermes/config.yaml ───────────────────────────
    hermes_file = Path(hermes_path).expanduser() if hermes_path else DEFAULT_HERMES_CONFIG.expanduser()
    hermes: dict[str, Any] = {}
    if hermes_file.exists():
        hermes = _load_yaml(hermes_file) or {}
        if hermes:
            sources["hermes"] = str(hermes_file)
    raw_model = hermes.get("model")
    hermes_model = raw_model if isinstance(raw_model, dict) else {}

    current_model = api.get("model") or hermes_model.get("default")
    current_provider = api.get("provider") or hermes_model.get("provider")

    fallback: Any = api.get("fallback_providers") or hermes_model.get("fallback_providers") or []
    if not isinstance(fallback, (list, tuple)):
        fallback = []

    # ── 峰谷：log 优先（反映真实切换动作），否则按时间规则推断 ──────────────
    log_file = Path(log_path).expanduser() if log_path else DEFAULT_PEAK_LOG.expanduser()
    peak = _peak_from_log(log_file)
    if peak is None:
        peak = is_weekday_peak(moment)
        sources["peak"] = "clock"
    else:
        sources["peak"] = "log"

    return {
        "peak": bool(peak),
        "current_model": current_model,
        "current_provider": current_provider,
        "fallback_chain": list(fallback),
        "capabilities": detect_capabilities(),
        "ts": moment.isoformat(),
        "sources": sources,
    }


@router.get("/admin/model_state")
async def model_state() -> dict[str, Any]:
    """模型峰谷状态只读探针：当前 provider / 模型 / 降级链 / 可用 SDK / 峰谷段。"""
    return resolve_model_state()
