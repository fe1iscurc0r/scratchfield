#!/usr/bin/env bash
# 授粉插件商城 — 安装器
# 用法: ./scripts/plugin-install.sh <plugin-id>
# 从 plugins/index.json 读取条目，按 type 处理：
#   mcp      → 校验路径存在 + 有 agent-manifest.json（mcpserver unified_call 自动发现）
#   skill    → 拷贝到 ~/.hermes/skills/
#   coupled  → 已是本仓目录，仅校验
#   report   → 纯文档，打印路径
set -euo pipefail

INDEX="$(cd "$(dirname "$0")/.." && pwd)/plugins/index.json"

if [ $# -lt 1 ]; then
  echo "用法: $0 <plugin-id>" >&2
  exit 1
fi
ID="$1"

if ! command -v python3 >/dev/null 2>&1; then
  echo "需要 python3" >&2
  exit 1
fi

# 用 python 安全解析 index.json（避免 jq 依赖）；分隔符用 | 防字段内空格
IFS='|' read -r NAME TYPE PATH_REL DOC LIC <<<"$(python3 - "$INDEX" "$ID" <<'PY'
import json, sys
idx = json.load(open(sys.argv[1]))
for p in idx.get("plugins", []):
    if p["id"] == sys.argv[2]:
        print(f"{p.get('name','')}|{p.get('type','')}|{p.get('path','')}|{p.get('doc','')}|{p.get('license','')}")
        sys.exit(0)
sys.exit(1)
PY
)" || { echo "插件 [$ID] 不在注册表 plugins/index.json 中" >&2; exit 1; }

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
echo "== 安装 [$ID] $NAME (${LIC:-许可未标}) =="

case "$TYPE" in
  mcp)
    FULL="$ROOT/$PATH_REL"
    if [ ! -e "$FULL" ]; then
      echo "!! 路径不存在: $FULL" >&2; exit 1
    fi
    if [ -d "$FULL" ] && [ -f "$FULL/agent-manifest.json" ]; then
      echo "OK  MCP 适配器就位: $PATH_REL (mcpserver 启动时自动注册)"
    elif [ -f "$FULL" ]; then
      echo "OK  单文件适配器就位: $PATH_REL"
    else
      echo "OK  路径存在: $PATH_REL (无 manifest，需人工确认注册方式)"
    fi
    ;;
  skill)
    FULL="$ROOT/$PATH_REL"
    [ -e "$FULL" ] || { echo "!! 路径不存在: $FULL" >&2; exit 1; }
    mkdir -p ~/.hermes/skills
    cp -r "$FULL" ~/.hermes/skills/
    echo "OK  已拷贝到 ~/.hermes/skills/$(basename "$FULL")"
    ;;
  coupled)
    FULL="$ROOT/$PATH_REL"
    [ -e "$FULL" ] || { echo "!! 路径不存在: $FULL" >&2; exit 1; }
    echo "OK  耦合层已在仓内: $PATH_REL"
    ;;
  report)
    echo "OK  授粉报告: $PATH_REL"
    ;;
  *)
    echo "!! 未知 type: $TYPE" >&2; exit 1
    ;;
esac

if [ -n "$DOC" ]; then
  echo "   报告: $DOC"
fi
