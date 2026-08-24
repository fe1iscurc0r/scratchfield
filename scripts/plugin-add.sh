#!/usr/bin/env bash
# 授粉插件商城 — 添加器
# 用法: ./scripts/plugin-add.sh <id> <name> <upstream> <license> <type> <path> [doc] [note]
# 例:   ./scripts/plugin-add.sh my-plugin "我的插件" owner/repo MIT mcp mcpserver/adapters/my_plugin docs/my-授粉报告.md
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
INDEX="$ROOT/plugins/index.json"

if [ $# -lt 6 ]; then
  echo "用法: $0 <id> <name> <upstream> <license> <type> <path> [doc] [note]" >&2
  exit 1
fi

ID="$1"; NAME="$2"; UPSTREAM="$3"; LIC="$4"; TYPE="$5"; PATH_REL="$6"; DOC="${7:-}"; NOTE="${8:-}"

python3 - "$INDEX" "$ID" "$NAME" "$UPSTREAM" "$LIC" "$TYPE" "$PATH_REL" "$DOC" "$NOTE" <<'PY'
import json, sys, datetime
idx_path, args = sys.argv[1], sys.argv[2:]
idx = json.load(open(idx_path))
if any(p["id"] == args[0] for p in idx.get("plugins", [])):
    print(f"!! 插件 id [{args[0]}] 已存在，先删旧条目或换 id", file=sys.stderr); sys.exit(1)
entry = {
    "id": args[0], "name": args[1], "upstream": args[2],
    "license": args[3], "type": args[4], "path": args[5],
}
if args[6]: entry["doc"] = args[6]
if args[7]: entry["note"] = args[7]
idx.setdefault("plugins", []).append(entry)
idx["updated"] = datetime.date.today().isoformat()
json.dump(idx, open(idx_path, "w"), ensure_ascii=False, indent=2)
print(f"OK  已添加 [{args[0]}] 到 plugins/index.json")
PY

echo "提示: 顺手更新 plugins/README.md 的说明（如需），然后提交。"
