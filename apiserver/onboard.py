"""Lumo onboard —— 新用户初始化向导（对标 OpenClaw `openclaw onboard`，自研）。

从零到能跑的四步：
  1. 环境：跑 doctor 的静态层（依赖/Python 版本）
  2. 配置：从模板生成 config.json，交互式填 LLM key/base_url/model 三项必填
  3. 验证：doctor --probe（key 真的能用）
  4. 下一步指引：启动命令 + 端口

用法：
  python -m apiserver.onboard           # 交互式
  python -m apiserver.onboard --api-key sk-xxx --base-url https://... --model xxx
                                        # 非交互（CI/脚本）
"""
from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = REPO_ROOT / "config.json"
EXAMPLE_PATH = REPO_ROOT / "config.example.json"

# 模板兜底：无 example 文件时生成的最小骨架（与 config.json 实际键对齐）
MINIMAL_TEMPLATE = {
    "system": {"version": "5.1.5", "ai_name": "陆墨", "active_character": "陆墨",
               "voice_enabled": True, "stream_mode": True},
    "api": {"api_key": "YOUR_API_KEY", "base_url": "YOUR_BASE_URL",
            "model": "YOUR_MODEL", "provider": "openai", "api_format": "openai",
            "temperature": 0.7, "max_history_rounds": 10},
    "api_server": {"enabled": True, "host": "127.0.0.1", "port": 8000,
                   "auto_start": True, "docs_enabled": True},
    "agent_server": {"enabled": True, "host": "127.0.0.1", "port": 8001,
                     "auto_start": True},
    "mcp_server": {"enabled": True, "host": "127.0.0.1", "port": 8003,
                   "auto_start": True},
    "channels": {"webhook": {"enabled": True}},
}

STEPS_HEADER = """
╭──────────────────────────────────────╮
│   Lumo onboard —— 初始化向导          │
╰──────────────────────────────────────╯
"""


def _ensure_config_file() -> tuple[bool, str]:
    """config.json 存在或从模板生成。返回 (已就绪, 说明)。"""
    if CONFIG_PATH.exists():
        return True, "config.json 已存在"
    src = EXAMPLE_PATH if EXAMPLE_PATH.exists() else None
    if src:
        shutil.copy(src, CONFIG_PATH)
        return True, f"已从 {src.name} 复制生成 config.json"
    CONFIG_PATH.write_text(
        json.dumps(MINIMAL_TEMPLATE, ensure_ascii=False, indent=2),
        encoding="utf-8")
    return True, "已生成最小 config.json 骨架"


def _ask(prompt: str, default: str = "") -> str:
    """交互式提问（EOF 安全——非交互环境返回默认值）。"""
    suffix = f" [{default}]" if default else ""
    try:
        val = input(f"{prompt}{suffix}: ").strip()
        return val or default
    except (EOFError, OSError):
        print("  （非交互环境，使用默认/占位值）")
        return default


def _fill_api_config(non_interactive: dict | None = None) -> list[str]:
    """填 api 三项必填。返回仍缺失的项。"""
    cfg = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    api = cfg.setdefault("api", {})
    missing = []
    for key, label, placeholder in (
        ("api_key", "LLM API Key", "YOUR_API_KEY"),
        ("base_url", "LLM 网关地址（如 https://api.example.com/v1）", "YOUR_BASE_URL"),
        ("model", "模型名（如 deepseek-v4-pro）", "YOUR_MODEL"),
    ):
        cur = api.get(key, "")
        if non_interactive and non_interactive.get(key):
            api[key] = non_interactive[key]
        elif cur in ("", placeholder) or "YOUR_" in str(cur):
            if non_interactive is not None:  # 非交互且没提供 → 留占位
                api[key] = cur or placeholder
                missing.append(key)
                continue
            val = _ask(label)
            api[key] = val or cur or placeholder
            if not val:
                missing.append(key)
    CONFIG_PATH.write_text(
        json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
    return missing


def run_onboard(args: list[str] | None = None) -> int:
    args = args if args is not None else sys.argv[1:]
    non_interactive = None
    if any(a.startswith("--") for a in args):
        # 非交互模式：--api-key/--base-url/--model
        non_interactive = {}
        for a in args:
            if a.startswith("--api-key="):
                non_interactive["api_key"] = a.split("=", 1)[1]
            elif a.startswith("--base-url="):
                non_interactive["base_url"] = a.split("=", 1)[1]
            elif a.startswith("--model="):
                non_interactive["model"] = a.split("=", 1)[1]

    print(STEPS_HEADER)

    # 步 1：环境静态检查
    print("【1/4】环境检查（doctor 静态层）")
    from apiserver.doctor import run_doctor
    report = run_doctor(probe=False, live_ports=False)
    for c in report.checks:
        mark = "✓" if c.ok else "✗"
        print(f"  [{mark}] {c.name}: {c.detail}")
        if not c.ok and c.hint:
            print(f"        ↳ {c.hint}")
    env_fail = [c for c in report.checks if not c.ok and c.name.startswith(("python", "dep:"))]
    if env_fail:
        print("\n环境层有未过项——先修复再继续（提示见上）。")
        return 1

    # 步 2：配置文件
    print("\n【2/4】配置文件")
    ok, msg = _ensure_config_file()
    print(f"  {msg}")
    missing = _fill_api_config(non_interactive)
    if missing:
        print(f"  ⚠ 未填写：{', '.join(missing)}（之后可手动编辑 config.json）")
    else:
        print("  ✓ api 配置三项已填")

    # 步 3：验证（含 LLM 探测）
    print("\n【3/4】验证（doctor --probe，发 1 个最小请求）")
    report2 = run_doctor(probe=not missing, live_ports=False)
    for c in report2.checks:
        if c.name.startswith(("config:", "llm:")):
            mark = "✓" if c.ok else "✗"
            print(f"  [{mark}] {c.name}: {c.detail}")

    # 步 4：下一步指引
    print("\n【4/4】下一步")
    print("  启动：      python -m apiserver.start_server")
    print("  API 地址：  http://127.0.0.1:8000（docs: /docs）")
    print("  健康自检：  python -m apiserver.doctor --probe")
    print("  渠道接入：  POST /api/channels/webhook（详见 docs）")
    if missing:
        print("\n完成度：配置缺 API 三项——填好后重跑 onboard 验证。")
        return 1
    print("\nonboard 完成 ✓")
    return 0


if __name__ == "__main__":
    sys.exit(run_onboard())
