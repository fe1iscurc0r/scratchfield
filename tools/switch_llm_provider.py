#!/usr/bin/env python3
"""LLM provider 切换器（工单210 任务二）。

⚠️ 与工单预设的偏差（实测 2026-10-08）：工单假设配置在 `~/.hermes/config.yaml`，**本机无该路径**。
   实际生效配置 = `system.config.get_config_path()` → `D:\\my git\\scratchpad\\config.json`，
   相关字段在 `api.{base_url, model, provider, api_key}`。

只改 `api.base_url` / `api.model` / `api.provider`（**默认不动 api_key**，除非显式 `--set-key-from-env`），
改前备份 `<config>.bak.<UTC 时间戳>`，写盘复用 `system.config.atomic_write_json`（原子 + 失败显式抛出）。

用法：
  # 看一眼有哪些预设 / 当前是什么
  .venv/Scripts/python.exe tools/switch_llm_provider.py --list
  .venv/Scripts/python.exe tools/switch_llm_provider.py --show

  # 切换（会备份 + 原子写）
  .venv/Scripts/python.exe tools/switch_llm_provider.py deepseek
  .venv/Scripts/python.exe tools/switch_llm_provider.py zhipu --model glm-4.7-flash
  .venv/Scripts/python.exe tools/switch_llm_provider.py deepseek --dry-run      # 只看会改什么

  # 连通性探测（GET {base_url}/models；超时/4xx → 打印 FAIL 并 exit 1）
  .venv/Scripts/python.exe tools/switch_llm_provider.py deepseek --probe

  # 回滚
  .venv/Scripts/python.exe tools/switch_llm_provider.py --list-backups
  .venv/Scripts/python.exe tools/switch_llm_provider.py --restore <备份文件名>

退出码：0 成功；1 探测失败/无备份；2 参数错误；3 配置不可读/写失败。
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import shutil
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

PRESETS: dict[str, dict[str, str]] = {
    "zhipu": {
        "base_url": "https://open.bigmodel.cn/api/paas/v4",
        "model": "glm-4.7-flash",
        "provider": "openai",
        "key_env": "ZHIPU_API_KEY",
        "note": "GLM（订阅到期即失效；默认模型名取自 NEKO 上游 api_profiles）",
    },
    "deepseek": {
        "base_url": "https://api.deepseek.com/v1",
        "model": "deepseek-chat",
        "provider": "openai",
        "key_env": "DEEPSEEK_API_KEY",
        "note": "官方直连；若走网关见 tokenrhythm 预设",
    },
    "minimax": {
        "base_url": "https://api.minimax.chat/v1",
        "model": "MiniMax-M2.7",
        "provider": "openai",
        "key_env": "MINIMAX_API_KEY",
        "note": "第三顺位兜底",
    },
    "tokenrhythm": {
        "base_url": "https://tokenrhythm.studio/v1",
        "model": "deepseek-v4-pro-0813",
        "provider": "openai",
        "key_env": "TOKENRHYTHM_API_KEY",
        "note": "本机现行（网关；use_gateway=True）—— 2026-10-08 实测生效值",
    },
}

FIELDS = ("base_url", "model", "provider")


def default_config_path() -> Path:
    try:
        from system.config import get_config_path

        return Path(get_config_path())
    except Exception:  # noqa: BLE001 - 独立可用（不依赖重依赖链）
        return Path("config.json").resolve()


def load_api(cfg: Path) -> dict:
    data = json.loads(cfg.read_text(encoding="utf-8"))
    return data, data.get("api", {})


def write_api(cfg: Path, data: dict) -> None:
    """原子写（复用仓内唯一写入口）。"""
    try:
        from system.config import atomic_write_json

        atomic_write_json(cfg, data)
    except Exception as e:  # noqa: BLE001
        print(f"原子写失败，退回 os.replace：{e}")
        tmp = cfg.with_suffix(cfg.suffix + ".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, cfg)


def backup(cfg: Path) -> Path:
    """备份到 `<config>.bak.<UTC 秒>[-N]`。

    ⚠️ 秒级时间戳在同一秒内多次切换会**重名**（会把"原始"那份备份覆盖掉，回滚点丢失）——
    实测踩到过 → 这里显式加冲突后缀 -1 / -2 …
    """
    stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    bak = cfg.with_name(f"{cfg.name}.bak.{stamp}")
    n = 1
    while bak.exists():
        bak = cfg.with_name(f"{cfg.name}.bak.{stamp}-{n}")
        n += 1
    shutil.copy2(cfg, bak)
    return bak


def probe(base_url: str, api_key: str, timeout: float = 8.0) -> tuple[bool, str]:
    url = base_url.rstrip("/") + "/models"
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {api_key}"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return (r.status == 200, f"HTTP {r.status}")
    except urllib.error.HTTPError as e:
        return (False, f"HTTP {e.code}")
    except Exception as e:  # noqa: BLE001 - 超时/DNS/连接拒绝都要报出来
        return (False, f"{type(e).__name__}: {str(e)[:80]}")


def main() -> int:
    ap = argparse.ArgumentParser(description="LLM provider 切换器（工单210）")
    ap.add_argument("provider", nargs="?", choices=sorted(PRESETS), help="目标 provider")
    ap.add_argument("--config", default=None, help="配置文件路径（默认取 get_config_path()）")
    ap.add_argument("--model", default=None, help="覆盖预设的 model 名")
    ap.add_argument("--set-key-from-env", action="store_true",
                    help="用预设的 key_env 环境变量覆盖 api_key（默认不动 api_key）")
    ap.add_argument("--dry-run", action="store_true", help="只打印将发生的改动，不落盘")
    ap.add_argument("--probe", action="store_true", help="切换后探测连通性（失败 exit 1）")
    ap.add_argument("--show", action="store_true", help="打印当前 api 配置")
    ap.add_argument("--list", action="store_true", help="列出预设")
    ap.add_argument("--list-backups", action="store_true", help="列出备份")
    ap.add_argument("--restore", default=None, help="从备份文件名恢复")
    args = ap.parse_args()

    cfg = Path(args.config) if args.config else default_config_path()

    if args.list:
        for name, p in PRESETS.items():
            print(f"{name:<12} model={p['model']:<26} base_url={p['base_url']}")
            print(f"{'':<12} {p['note']}  [key_env={p['key_env']}]")
        return 0

    if args.list_backups:
        for b in sorted(glob.glob(str(cfg) + ".bak.*")):
            print(" ", Path(b).name)
        return 0

    if args.restore:
        src = cfg.with_name(args.restore)
        if not src.exists():
            print(f"备份不存在: {src}")
            return 1
        shutil.copy2(src, cfg)
        print(f"已从 {src.name} 恢复 → {cfg}")
        return 0

    if not cfg.exists():
        print(f"配置不存在: {cfg}")
        return 3

    data, api = load_api(cfg)

    if args.show or args.provider is None:
        print(f"config = {cfg}")
        for k in ("base_url", "model", "provider", "use_gateway"):
            print(f"  api.{k} = {api.get(k)}")
        key = api.get("api_key") or ""
        print(f"  api.api_key = {key[:8]}...({len(key)} 字符)" if key else "  api.api_key = (空)")
        if args.provider is None and not args.show:
            print("\n用法见 --help；切换：switch_llm_provider.py <provider>")
        return 0

    preset = PRESETS[args.provider]
    new = {
        "base_url": preset["base_url"],
        "model": args.model or preset["model"],
        "provider": preset["provider"],
    }
    print(f"目标 provider: {args.provider} ({preset['note']})")
    changed = False
    for k in FIELDS:
        old = api.get(k)
        if old != new[k]:
            print(f"  api.{k}: {old} → {new[k]}")
            changed = True
        else:
            print(f"  api.{k}: {old}（不变）")

    if args.set_key_from_env:
        env_key = os.environ.get(preset["key_env"], "")
        if not env_key:
            print(f"  ⚠️ --set-key-from-env 给了但环境变量 {preset['key_env']} 为空 → 不动 api_key")
        else:
            print(f"  api.api_key: 用 {preset['key_env']} 覆盖（{len(env_key)} 字符）")
            api["api_key"] = env_key
            changed = True
    else:
        print("  api.api_key: 保持不变（如需换 key 用 --set-key-from-env 或手改）")

    if not changed:
        print("\n无改动（已是目标 provider）。")
    elif args.dry_run:
        print("\n[dry-run] 未落盘。")
    else:
        bak = backup(cfg)
        print(f"\n已备份 → {bak.name}")
        api.update(new)
        data["api"] = api
        write_api(cfg, data)
        print(f"已写入 → {cfg}")

    if args.probe:
        key = api.get("api_key") or ""
        ok, detail = probe(new["base_url"], key)
        print(f"探测 {new['base_url'].rstrip('/')}/models → {'OK' if ok else 'FAIL'} ({detail})")
        return 0 if ok else 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
