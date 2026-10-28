#!/bin/sh
# 工单241 任务三 · 峰谷切换后「重签挂起任务」
#
# 背景：tools/peak_switch.sh 在工作日峰段切到 MiniMax-M3、其余时间切回
# deepseek-flash。切换前由 M3 签署的挂起任务，切换到 deepseek-flash 后
# **签名主体仍是 M3** —— 审计层无法回溯「这条输出到底是哪个 provider 产的」。
# 本脚本把挂起任务用**新 provider** 重新签署，并输出可被日志采集的计数指标。
#
# 用法：
#   tools/agent_rekey.sh <provider> [--pending FILE] [--audit-dir DIR] [--dry-run]
#   tools/agent_rekey.sh MiniMax-M3
#
# 由 tools/peak_switch.sh 调用（仅在 `--rekey` 或 `AGENT_REKEY=1` 时）。
# 加密逻辑全在 `mcpserver.agent_governance`（纯 stdlib HMAC），本脚本只做路径与解释器解析。
#
# 环境变量：
#   PYTHON_BIN        python 解释器（默认 python3）
#   AGENT_AUDIT_DIR   审计目录（也用于定位默认的 pending_tasks.jsonl）
#   HERMES_AGENT_ID_KEY  签名密钥（未设置则 python 侧退出码 2）
#
# 退出码：0 = 成功（含 re-sign count: 0）；2 = 参数/密钥错误；其余透传 python 退出码
set -eu

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO="$(cd "$SCRIPT_DIR/.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-python3}"

if [ "$#" -lt 1 ] || [ "$1" = "--help" ] || [ "$1" = "-h" ]; then
	cat <<'EOF'
用法: agent_rekey.sh <provider> [--pending FILE] [--audit-dir DIR] [--dry-run]

  <provider>      新的 provider 名（如 MiniMax-M3 / deepseek-flash）
  --pending       挂起任务 JSONL（默认 <audit-dir>/pending_tasks.jsonl）
  --audit-dir     审计目录（默认 $AGENT_AUDIT_DIR 或 ~/.hermes/audit）
  --dry-run       只统计与写审计事件，不覆写挂起任务文件

输出: `re-sign count: N`（供 cron 日志采集「切换时重签了多少条」）。
EOF
	[ "$#" -ge 1 ] || exit 2
	exit 0
fi

cd "$REPO"
exec "$PYTHON_BIN" -m mcpserver.agent_governance resign --provider "$@"
