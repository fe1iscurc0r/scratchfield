#!/usr/bin/env bash
# 从工作仓(scratchpad)同步选料到公开展示仓(scratchfield)
# 用法: ./scripts/sync-to-scratchfield.sh [目标路径]
# 默认目标: ~/scratchfield
#
# 规则:
# - 增量同步(无 --delete): 只推送源变更, 不删除目标仓独有的策展文件
#   (README 门面 / LICENSE / plugins 商城 / 有意排除项)
# - 有意删除的目标文件需手动 rm
set -euo pipefail

SRC="$(cd "$(dirname "$0")/.." && pwd)"
DST="${1:-$HOME/scratchfield}"

[ -d "$DST/.git" ] || { echo "!! 目标不是 git 仓: $DST" >&2; exit 1; }

rsync -a \
  --exclude '.git/' \
  --exclude 'repos/' \
  --exclude 'vendor/' \
  --exclude 'papers/' \
  --exclude 'data/' \
  --exclude 'docs/SCI-Review-Plan-v1.md' \
  --exclude 'frontend/build/codesign.pfx' \
  --exclude 'BATCH-WORKORDERS-*.md' \
  --exclude 'TRAE_WORKORDER*.md' \
  --exclude 'LAW_WORKORDER*' \
  --exclude 'workorders/' \
  --exclude 'research/' \
  --exclude 'academic/' \
  --exclude 'wt-overwatch-v6/' \
  --exclude 'docs/archive/' \
  --exclude 'docs/SPEC-14*' \
  --exclude 'docs/law-*' \
  --exclude 'docs/法学*' \
  --exclude 'docs/*工单*' \
  --exclude 'docs/卷*' \
  --exclude 'docs/exec-reports/' \
  --exclude 'docs/授粉-轮*' \
  --exclude 'docs/issue-2881*' \
  --exclude 'docs/pollination/batches/' \
  --exclude 'docs/dependabot*' \
  --exclude 'docs/*判例*' \
  --exclude 'docs/*audit*' \
  --exclude 'docs/*审计*' \
  --exclude 'docs/2026-08-23-合并与Docker部署-操作日志.md' \
  --exclude 'docs/GOAL-TRANSITION.md' \
  --exclude 'docs/merge-report-*.md' \
  --exclude 'github_haul/' \
  --exclude 'tools/pcb-plays/' \
  --exclude '**/_queue/' \
  --exclude '.venv/' \
  --exclude 'README.md' \
  --exclude 'README_en.md' \
  --exclude 'README_ja.md' \
  --exclude 'QUICKSTART.md' \
  --exclude '**/__pycache__/' \
  --exclude '*.pyc' \
  --exclude '**/node_modules/' \
  --exclude '**/logs/' \
  --exclude '**/sessions/' \
  --exclude '**/uploaded_documents/' \
  --exclude '**/.auth_session' \
  "$SRC/" "$DST/"

echo "== 同步完成: $SRC -> $DST"
echo "== 提交推送: cd $DST && git add -A && git commit -m 'sync' && git push github main"
