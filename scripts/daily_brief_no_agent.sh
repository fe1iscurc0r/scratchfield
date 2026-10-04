#!/usr/bin/env bash
# daily_brief_no_agent.sh — 无 Agent 每日早报（卷136 W136-03 落点）
#
# 说明：卷136 工单假设此脚本已存在，实际核查仓内无此文件（2026-09-19）。
# 故按工单要求的"OUTPUT 末尾追加论文情报段"直接在本脚本内实现——
# 新建而非修改（无既有逻辑可破坏）。
#
# 用法：bash scripts/daily_brief_no_agent.sh
set -uo pipefail
REPO="$(cd "$(dirname "$0")/.." && pwd)"
OUT="${DAILY_BRIEF_OUT:-$REPO/tmp/daily_brief_$(date +%Y-%m-%d).txt}"
mkdir -p "$(dirname "$OUT")"

{
  echo "===== 每日早报 $(date '+%Y-%m-%d %H:%M') ====="

  # ---- 论文情报（卷136 W136-03）----
  echo
  echo "📚 论文情报"
  PY="${PYTHON:-python}"
  if "$PY" "$REPO/scripts/daily_paper_brief.py" --all >/dev/null 2>&1; then
    SUM="$HOME/.hermes/cache/daily_paper_brief/summary.txt"
    if [ -s "$SUM" ]; then
      cat "$SUM"
    else
      echo "今日无相关新文献"
    fi
  else
    echo "（论文情报生成失败：daily_paper_brief.py 未就绪或无当日数据）"
  fi

  # ---- 后续早报段落可在此追加 ----
} | tee "$OUT"
echo
echo "[daily_brief] → $OUT"
