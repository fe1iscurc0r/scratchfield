#!/usr/bin/env bash
# 从工作仓(scratchpad)同步选料到公开展示仓(scratchfield)
# 用法: ./scripts/sync-to-scratchfield.sh [目标路径]
# 默认目标: ~/scratchfield
#
# 规则:
# - 增量同步(无 --delete): 只推送源变更, 不删除目标仓独有的策展文件
#   (README 门面 / LICENSE / plugins 商城 / 有意排除项)
# - 有意删除的目标文件需手动 rm
# - 工单271 T2 / P0-13: 目标仓是**公开**展示仓。同步后先跑敏感自检，命中即非零退出、
#   不给提交命令；提交建议从 `git add -A` 换成显式白名单（脚本生成清单，人只审不拼）。
set -euo pipefail

SRC="$(cd "$(dirname "$0")/.." && pwd)"
DST="${1:-$HOME/scratchfield}"

[ -d "$DST/.git" ] || { echo "!! 目标不是 git 仓: $DST" >&2; exit 1; }

# ── 敏感基名清单 ─────────────────────────────────────────────────────────────
# 同一份清单既喂 rsync 的 --exclude，又喂同步后的落盘自检；分头维护必然漂移。
# 自检不是重复劳动：排除表只管将来，目标仓里可能早就躺着历次同步带过去的文件。
# *.bak* 顺带盖住工单271 T3 那三个遗留生成器新产生的 <name>.bak-<时间戳> 备份。
SENSITIVE_GLOBS=(
  'config.json'
  '.env*'
  '*.bak*'
  'token_usage.json'
  '.workbuddy'
  '*.pem'
  'id_rsa*'
  '.auth_session'
)
SENSITIVE_EXCLUDES=()
for glob in "${SENSITIVE_GLOBS[@]}"; do
  SENSITIVE_EXCLUDES+=( --exclude "$glob" )
done

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
  "${SENSITIVE_EXCLUDES[@]}" \
  "$SRC/" "$DST/"

echo "== 同步完成: $SRC -> $DST"

# ── 敏感自检：$DST 落盘后仍命中 ⇒ 拒绝提交，非零退出 ─────────────────────────
# 白名单：基名看着像敏感、实际是**公开模板**的文件（值全是占位符）。
# 只作用于自检，**不改 rsync 的 --exclude** —— 同步时仍不主动带 .env* 过去，
# 免得将来有人把真实 .env 放进源仓后被顺手推上公仓。
# 加条目必须写清"为什么它不含真值"，否则这里就是后门。
SENSITIVE_ALLOW=(
  '*.example'
)
find_sensitive() {
  local -a expr=() allow=()
  local i
  for i in "${!SENSITIVE_GLOBS[@]}"; do
    if [ "$i" -gt 0 ]; then expr+=( -o ); fi
    expr+=( -name "${SENSITIVE_GLOBS[$i]}" )
  done
  for i in "${!SENSITIVE_ALLOW[@]}"; do
    allow+=( ! -name "${SENSITIVE_ALLOW[$i]}" )
  done
  # .git 里有 config、hooks 等同名文件，不剪掉会全是假阳性
  find "$1" -name .git -prune -o \( "${expr[@]}" \) "${allow[@]}" -print
}

HITS="$(mktemp)"
find_sensitive "$DST" > "$HITS" || true
if [ -s "$HITS" ]; then
  echo "!! 敏感文件自检命中 $(wc -l < "$HITS") 项 —— 这些东西不能进公开仓 $DST：" >&2
  while IFS= read -r hit; do
    echo "     ${hit#"$DST"/}" >&2
  done < "$HITS"
  echo "!! 未给出提交命令。私密就移出/删除；确实要公开的，改 SENSITIVE_GLOBS 并在 PR 里写理由。" >&2
  exit 1
fi
echo "== 敏感文件自检: 0 命中"

# ── 待提交白名单（取代 git add -A：公仓的每次提交都该是能逐条过目的）──────────
LIST="$(mktemp)"
{
  # 新仓还没有 HEAD 时 diff 无意义，全部内容都以 untracked 出现，下面那条覆盖它
  if git -C "$DST" rev-parse --verify -q HEAD >/dev/null 2>&1; then
    git -C "$DST" diff --name-only -z --no-renames HEAD
  fi
  git -C "$DST" ls-files --others --exclude-standard -z
} | sort -z -u > "$LIST"

mapfile -d '' PATHS < "$LIST"
if [ "${#PATHS[@]}" -eq 0 ]; then
  echo "== 目标仓无变更，无需提交。"
  exit 0
fi

echo "== 待提交 ${#PATHS[@]} 项（前 20）:"
for p in "${PATHS[@]:0:20}"; do echo "     $p"; done
if [ "${#PATHS[@]}" -gt 20 ]; then echo "     … 完整清单在 $LIST"; fi
cat <<EOF
== 提交（显式白名单，**不要用 git add -A**；清单文件重启会回收，尽快用）:
   git -C "$DST" add --pathspec-from-file="$LIST" --pathspec-file-nul
   git -C "$DST" commit -m 'sync $(date +%Y-%m-%d)' && git -C "$DST" push github main
EOF
