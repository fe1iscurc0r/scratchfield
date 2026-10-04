"""Ollama 辅助「实验建议」（W-01 · 可选开关）。

把预测结果交给本地 Ollama 生成一段实验建议文本（数据解读/下一组参数建议）。
定位：辅助解读，不参与预测计算——Ollama 不可用/未装时优雅降级（返回提示，
不抛错），预测本身照常可用。

模型名可用 OLLAMA_MODEL 环境变量覆盖，默认 qwen2.5:7b。
"""
from __future__ import annotations

import json
import os
import urllib.request
from typing import Any

DEFAULT_BASE_URL = os.environ.get("OLLAMA_BASE_URL", "http://127.0.0.1:11434")
DEFAULT_MODEL = os.environ.get("OLLAMA_MODEL", "qwen2.5:7b")


def _generate(model: str, prompt: str, timeout: float = 60.0) -> str:
    """调用 Ollama /api/generate（非流式），失败抛 RuntimeError。"""
    url = DEFAULT_BASE_URL.rstrip("/") + "/api/generate"
    payload = {"model": model, "prompt": prompt, "stream": False}
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode("utf-8"), headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = json.loads(resp.read().decode("utf-8", errors="replace"))
    if data.get("error"):
        raise RuntimeError(f"Ollama 返回错误: {data['error']}")
    return data.get("response", "")


def suggest_experiment(
    prediction_result: dict[str, Any], *, model: str | None = None, timeout: float = 60.0
) -> dict[str, Any]:
    """基于预测结果生成实验建议文本（Ollama 不可用时降级）。"""
    model = model or DEFAULT_MODEL
    inputs = prediction_result.get("input", {})
    predictions = prediction_result.get("predictions", [])
    honest = prediction_result.get("honest_label", "")

    prompt = (
        "你是材料科学实验助手。以下是一次生物质碳化实验的模型预测结果，"
        "请用中文给出 2~3 句实验建议（数据解读 + 下一组值得尝试的参数方向）。"
        "务必说明这些是预测值、需实验验证。\n"
        f"输入条件: {json.dumps(inputs, ensure_ascii=False)}\n"
        f"预测结果: {json.dumps(predictions, ensure_ascii=False)}\n"
        f"数据性质: {honest}\n"
    )
    try:
        text = _generate(model, prompt, timeout=timeout)
    except Exception as e:  # noqa: BLE001 - Ollama 可选，任何失败都应降级而非崩溃
        return {
            "ok": False,
            "available": False,
            "model": model,
            "note": "Ollama 不可用，已跳过实验建议（预测结果仍有效）",
            "error": f"{type(e).__name__}: {e}",
        }
    return {
        "ok": True,
        "available": True,
        "model": model,
        "suggestion": text.strip(),
    }


def main(argv: list[str] | None = None) -> int:
    """CLI：`python -m scripts.materials_model.suggest '{"input": {...}, "predictions": [...]}'`。"""
    import argparse

    parser = argparse.ArgumentParser(description="用 Ollama 对预测结果生成实验建议（可选）")
    parser.add_argument("result", help="预测结果 JSON 文本或文件路径")
    parser.add_argument("--model", default=None, help="Ollama 模型名（默认 OLLAMA_MODEL 或 qwen2.5:7b）")
    args = parser.parse_args(argv)

    text = args.result
    from pathlib import Path

    if Path(text).exists():
        text = Path(text).read_text(encoding="utf-8")
    result = json.loads(text)
    out = suggest_experiment(result, model=args.model)
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0 if out["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
