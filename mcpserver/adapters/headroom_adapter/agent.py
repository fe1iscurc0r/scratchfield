"""headroom manifest 桥接：handle_handoff 分发（同 pdf2md_adapter 约定）。

两级压缩（按收益择优）：
1. 结构保真 pass：vendor UniversalCompressor（json/code/log 自动识别，去重 + 结构保真，
   无损）。实测 JSON 结构无冗余时压不动（ratio≈1.0）。
2. 词元级 pass：vendor KompressCompressor（ModernBERT token 分类，**有损**）。仅在
   第 1 级压不动且模型就绪时启用。实测 JSON 5941→3778（ratio 0.636）。

模型就绪条件（本机实测结论，改动前请读）：
- 权重 `onnx/kompress-fp32.onnx`（572MB）+ `answerdotai/ModernBERT-base` tokenizer 必须
  已在本地 HF 缓存。仓库里其实有 `onnx/kompress-int8-wo.onnx`（261MB），但本地
  onnxruntime 1.20.1 加载它直接报 `MatMulNBits nbits_ == 4 was false`（只支持 4bit
  量化），所以用 `HEADROOM_KOMPRESS_ONNX_FILENAME` 钉死 fp32。
- huggingface.co 在本机不可达，huggingface_hub 会退避重试 5 次（单次调用卡数分钟）：
  所以先探缓存，模型不在就关掉 Kompress 走纯结构/截断，绝不让工具卡死；
  冷缓存预取走镜像 `HF_ENDPOINT=https://hf-mirror.com`（实测可达，572MB/167s）。
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import threading
from typing import Any, Callable

logger = logging.getLogger(__name__)

# 短文本不做截断的阈值（与平铺模块 mcpserver/adapters/headroom.py 保持一致）
MIN_KEEP = 300

# 单次压缩硬超时：Kompress 首次加载 5s 上下、长文本推理更久，
# 留足余量但绝不允许网络退避把工具调用拖到分钟级
COMPRESS_TIMEOUT_S = 40.0

# 结构 pass 压到该比例以内就不再上词元级（有损）pass
STRUCTURAL_GOOD_ENOUGH = 0.9

_KOMPRESS_REPO = "chopratejas/kompress-v2-base"
_KOMPRESS_REVISION = "b1563631b35bfdcee37587ad530147497d820d4c"
# 优先级：fp32（ORT 1.20.1 可加载）> int8 > int8-wo（本机 ORT 不兼容，仅作兜底探测）
_KOMPRESS_ONNX_CANDIDATES = (
    "onnx/kompress-fp32.onnx",
    "onnx/kompress-int8.onnx",
    "onnx/kompress-int8-wo.onnx",
)
_TOKENIZER_REPO = "answerdotai/ModernBERT-base"

# mode → vendor ContentType 成员名（None = 交给管道自动识别）
_MODE_TO_CONTENT_TYPE = {
    "code": "CODE",
    "json": "JSON",
    "log": "LOG",
    "diff": "DIFF",
    "markdown": "MARKDOWN",
    "text": "TEXT",
}

_COMPRESSOR: Any = None
_KOMPRESS: Any = None
_COMPRESSOR_LOCK = threading.Lock()


def _inject_vendor_path() -> None:
    from mcpserver.adapters._common import inject_vendor_path

    inject_vendor_path("headroom")


def _cached_path(repo_id: str, filename: str, revision: str | None) -> str | None:
    """本地 HF 缓存里的文件路径；未缓存返回 None（不发网络请求）。"""
    try:
        from huggingface_hub import try_to_load_from_cache
    except Exception:  # noqa: BLE001
        return None
    try:
        path = try_to_load_from_cache(repo_id, filename, revision=revision)
    except Exception:  # noqa: BLE001
        return None
    if isinstance(path, str) and os.path.exists(path):
        return path
    return None


def _kompress_onnx_cached() -> str | None:
    for filename in _KOMPRESS_ONNX_CANDIDATES:
        if _cached_path(_KOMPRESS_REPO, filename, _KOMPRESS_REVISION):
            return filename
    return None


def _kompress_ready() -> bool:
    """权重 + tokenizer 都在本地缓存才认可用（避免运行时网络退避卡死）。"""
    if not _kompress_onnx_cached():
        return False
    return _cached_path(_TOKENIZER_REPO, "tokenizer.json", None) is not None


def rust_core_available() -> bool:
    """检测 Rust 扩展是否已构建（Windows wheel 未验证，默认 False）。"""
    _inject_vendor_path()
    try:
        from headroom import _core  # type: ignore  # noqa: F401

        return True
    except Exception:  # noqa: BLE001
        return False


def _build_compressor():
    """结构保真压缩器（**恒定 use_kompress=False**）。

    别把这里改成 use_kompress=True：开启后 vendor 会把非结构分支路由到 Kompress，
    实测同一段重复日志的结构压缩比反而从 0.308 掉到 0.775（有损且更差）。
    词元级压缩由独立的 _get_kompress() 单例负责，两级结果按 ratio 择优。
    """
    from headroom.compression.universal import (  # type: ignore
        UniversalCompressor,
        UniversalCompressorConfig,
    )

    config = UniversalCompressorConfig(
        use_kompress=False,
        use_entropy_preservation=True,
        compression_ratio_target=0.3,
    )
    return UniversalCompressor(config)


def _get_compressor():
    """进程级单例（构造含检测器初始化，别每次调用重建）。不可用返回 None。"""
    global _COMPRESSOR
    if _COMPRESSOR is not None:
        return _COMPRESSOR
    _inject_vendor_path()
    with _COMPRESSOR_LOCK:
        if _COMPRESSOR is None:
            try:
                _COMPRESSOR = _build_compressor()
            except Exception as e:  # noqa: BLE001 - 任何导入/构造失败都退化为 truncate
                logger.warning("[headroom_adapter] 压缩管道不可用，退化到 truncate: %s", e)
                return None
    return _COMPRESSOR


def _get_kompress():
    """词元级压缩器单例（vendor 内部按模块级缓存复用 ORT session）。未就绪返回 None。"""
    global _KOMPRESS
    if _KOMPRESS is not None:
        return _KOMPRESS
    if not _kompress_ready():
        return None
    _inject_vendor_path()
    with _COMPRESSOR_LOCK:
        if _KOMPRESS is None:
            try:
                # 钉死 ONNX 产物名：默认候选顺序先试 int8-wo，而本机 onnxruntime
                # 1.20.1 加载它会直接报 MatMulNBits 只支持 4bit（实测不可用）
                onnx_file = _kompress_onnx_cached()
                if onnx_file:
                    os.environ.setdefault("HEADROOM_KOMPRESS_ONNX_FILENAME", onnx_file)
                os.environ.setdefault("HEADROOM_KOMPRESS_BACKEND", "onnx")
                from headroom.transforms.kompress_compressor import (  # type: ignore
                    KompressCompressor,
                )

                _KOMPRESS = KompressCompressor()
            except Exception as e:  # noqa: BLE001
                logger.warning("[headroom_adapter] Kompress 不可用: %s", e)
                return None
    return _KOMPRESS


def _truncate_fallback(text: str, max_ratio: float, reason: str = "") -> dict:
    """保头尾、中间省略占位。短文本原样返回，不制造无意义压缩。"""
    if len(text) <= MIN_KEEP:
        return {"ok": True, "compressed": text, "ratio": 1.0, "mode": "no-truncation"}
    keep = max(MIN_KEEP, int(len(text) * max(max_ratio, 0.05)))
    if keep >= len(text):
        return {"ok": True, "compressed": text, "ratio": 1.0, "mode": "no-truncation"}
    head_len = min(keep // 2, len(text))
    tail_len = min(keep - head_len, len(text) - head_len)
    head = text[:head_len]
    tail = text[len(text) - tail_len:] if tail_len > 0 else ""
    omitted = len(text) - head_len - tail_len
    text_out = head + (f"\n\n[⋯中间{omitted}字已省略⋯]\n\n" + tail if omitted > 0 else "")
    out = {
        "ok": True,
        "compressed": text_out,
        "ratio": len(text_out) / max(1, len(text)),
        "mode": "truncate-fallback",
    }
    if reason:
        out["fallback_reason"] = reason
    return out


def _content_type_for(mode: str | None):
    name = _MODE_TO_CONTENT_TYPE.get((mode or "").strip().lower())
    if not name:
        return None
    try:
        from headroom.compression.detector import ContentType  # type: ignore

        return getattr(ContentType, name, None)
    except Exception:  # noqa: BLE001
        return None


def _structural_pass(text: str, mode: str) -> dict | None:
    compressor = _get_compressor()
    if compressor is None:
        return None
    content_type = _content_type_for(mode)
    result = (
        compressor.compress(text) if content_type is None
        else compressor.compress(text, content_type=content_type)
    )
    compressed = getattr(result, "compressed", None)
    if not isinstance(compressed, str):
        return None
    return {
        "ok": True,
        "compressed": compressed,
        "ratio": len(compressed) / max(1, len(text)),
        "mode": f"structural:{getattr(result, 'handler_used', 'unknown')}",
        "content_type": str(getattr(result, "content_type", "") or ""),
    }


def _kompress_pass(text: str) -> dict | None:
    """词元级（有损）压缩。不可用返回 None。"""
    compressor = _get_kompress()
    if compressor is None:
        return None
    result = compressor.compress(text)
    compressed = getattr(result, "compressed", None)
    if not isinstance(compressed, str) or not compressed:
        return None
    return {
        "ok": True,
        "compressed": compressed,
        "ratio": len(compressed) / max(1, len(text)),
        "mode": "kompress-token-lossy",
        "lossy": True,
    }


def compress_text(text: str, max_ratio: float = 0.7, mode: str = "general") -> dict:
    """压缩长文本：结构保真 pass → 压不动则词元级 pass → 都不行截断兜底。"""
    if not isinstance(text, str) or not text:
        return {"ok": False, "error": "text 为空或非字符串"}
    if len(text) <= MIN_KEEP:
        return {"ok": True, "compressed": text, "ratio": 1.0, "mode": "no-truncation"}

    best: dict | None = None
    for stage, runner in (("structural", lambda: _structural_pass(text, mode)), ("kompress", lambda: _kompress_pass(text))):
        try:
            candidate = runner()
        except Exception as e:  # noqa: BLE001 - 单级失败不影响另一级
            logger.warning("[headroom_adapter] %s pass 失败: %s", stage, e)
            continue
        if candidate is None:
            continue
        if best is None or candidate["ratio"] < best["ratio"]:
            best = candidate
        # 结构 pass 已经压得动就没必要上词元级（有损）
        if stage == "structural" and best["ratio"] <= STRUCTURAL_GOOD_ENOUGH:
            break

    if best is None:
        return _truncate_fallback(text, max_ratio, reason="pipeline-unavailable")
    return best


def stats() -> dict:
    """headroom 运行状态：Rust 扩展 / 结构管道 / 词元级模型可用性。"""
    version = "unknown"
    _inject_vendor_path()
    try:
        from headroom._version import __version__  # type: ignore

        version = __version__
    except Exception:  # noqa: BLE001
        try:
            from headroom import __version__ as _v  # type: ignore

            version = _v
        except Exception:  # noqa: BLE001
            pass
    rust_available = rust_core_available()
    pipeline_available = _get_compressor() is not None
    kompress_file = _kompress_onnx_cached()
    kompress_ready = _kompress_ready()
    return {
        "ok": True,
        "version": version,
        "rust_core_available": rust_available,
        "python_pipeline_available": pipeline_available,
        "kompress_model_cached": kompress_file,
        "kompress_ready": kompress_ready,
        "mode": (
            "full"
            if rust_available
            else ("structural+kompress" if kompress_ready else "structural_only")
        ),
    }


class HeadroomBridge:
    """mcpserver 扫描入口：entryPoint {module, class} → 本类。"""

    name = "headroom"

    _TOOLS: dict[str, Callable[..., dict]] = {
        "headroom_compress_text": compress_text,
        "headroom_stats": stats,
    }

    async def handle_handoff(self, task: dict) -> str:
        tool_name = str(task.get("tool_name") or "").strip()
        if not tool_name:
            return json.dumps(
                {"status": "error", "message": "缺少 tool_name", "data": {}},
                ensure_ascii=False,
            )
        fn = self._TOOLS.get(tool_name)
        if fn is None:
            return json.dumps(
                {
                    "status": "error",
                    "message": f"未知工具 {tool_name}，可用: {', '.join(sorted(self._TOOLS))}",
                    "data": {},
                },
                ensure_ascii=False,
            )

        # 参数平铺在 task 里（registry 约定）；兼容嵌套 params/arguments（stdio 直连）。
        # 用键存在判断而非真值：空 dict 也是合法参数集（无参工具）
        if isinstance(task.get("params"), dict):
            arguments: dict[str, Any] = task["params"]
        elif isinstance(task.get("arguments"), dict):
            arguments = task["arguments"]
        else:
            arguments = {
                k: v
                for k, v in task.items()
                if k not in ("tool_name", "agentType", "service_name", "_tool_call_id")
            }

        try:
            # 压缩是 CPU 密集同步调用 → 线程池；再套硬超时，避免模型加载/网络退避
            # 把 agent 的工具回路拖死。
            data = await asyncio.wait_for(
                asyncio.to_thread(lambda: fn(**arguments)),
                timeout=COMPRESS_TIMEOUT_S,
            )
            if isinstance(data, dict) and data.get("ok") is False:
                return json.dumps(
                    {"status": "error", "message": data.get("error", "未知错误"), "data": data},
                    ensure_ascii=False,
                )
            return json.dumps(
                {"status": "success", "message": "ok", "data": data},
                ensure_ascii=False,
                default=str,
            )
        except asyncio.TimeoutError:
            text = str(arguments.get("text") or "")
            max_ratio = float(arguments.get("max_ratio") or 0.7)
            data = _truncate_fallback(text, max_ratio, reason=f"timeout>{COMPRESS_TIMEOUT_S}s")
            return json.dumps(
                {"status": "success", "message": "压缩超时，已退化为截断", "data": data},
                ensure_ascii=False,
                default=str,
            )
        except TypeError as e:
            return json.dumps(
                {"status": "error", "message": f"参数错误: {e}", "data": {}},
                ensure_ascii=False,
            )
        except Exception as e:  # noqa: BLE001
            return json.dumps(
                {"status": "error", "message": f"{type(e).__name__}: {e}", "data": {}},
                ensure_ascii=False,
            )
