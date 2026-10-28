#!/usr/bin/env python3
"""anthropic 1.x 兼容层连通性探针（工单 228 任务三 · 验收里"实测"的那一半）。

## 干什么

用兼容层真实发一条 1.x 形态的请求，断言返回的 content 非空 —— 证明「旧式入参 →
1.x 形态」的翻译逻辑在**真实 SDK** 上跑得通，而不只是 mock 里对（离线单测见
``tests/test_anthropic_compat.py``）。

## 没有 key / 没装 SDK 时

**优雅退出（exit 0 + 明确说明原因）**，不阻塞 CI。CI 干净环境既无
``ANTHROPIC_API_KEY``、也未必装 SDK —— 那不是失败，是"当前无法实测"。

退出码：``0`` = 通过或明确跳过；``1`` = 有 key 但真实调用失败。
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from mcpserver.llm_gateway import anthropic_compat as ac  # noqa: E402 - 必须先注入仓根到 sys.path


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="anthropic 1.x 兼容层探针（工单 228 任务三）")
    ap.add_argument("--model", default=None, help=f"模型名（默认 {ac.DEFAULT_MODEL}）")
    ap.add_argument("--prompt", default="ping", help="测试用 prompt")
    ap.add_argument("--max-tokens", type=int, default=64, help="max_tokens（1.x 必填）")
    ap.add_argument("--config", default=None, help="仓内 config.json 路径（注入用）")
    args = ap.parse_args(argv)

    api_key = os.environ.get(ac.ENV_API_KEY) or ac.api_key_from_repo_config(args.config)
    if not api_key:
        print(f"[skip] 未找到 {ac.ENV_API_KEY}（环境变量与仓内 config 均为空）→ 无法实测，exit 0")
        return 0

    try:
        client = ac.get_client(api_key=api_key, async_client=False, config_path=args.config)
    except ac.AnthropicCompatError as exc:
        print(f"[skip] {exc} → 无法实测，exit 0")
        return 0

    try:
        response = ac.messages_create(
            client,
            messages=[{"role": "user", "content": args.prompt}],
            model=args.model,
            max_tokens=args.max_tokens,
        )
    except Exception as exc:  # noqa: BLE001 - 探针要把任何失败都报成 exit 1
        print(f"[fail] 调用失败：{type(exc).__name__}: {exc}")
        return 1

    text = ac.extract_text(response)
    if not text:
        print(f"[fail] 返回成功但 content 为空：{response!r}"[:400])
        return 1

    print(f"[ok] model={args.model or ac.DEFAULT_MODEL} content={text[:160]!r}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
