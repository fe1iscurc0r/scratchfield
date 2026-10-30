#!/bin/sh
# 工单229 任务二 · 峰谷模型切换器
#
# 峰谷表（与 apiserver/admin/router.py 的 PEAK_WINDOWS 同源，只此一份口径）：
#   峰段 = 工作日（周一~周五）09:00-12:00 与 14:00-18:00，**左闭右开**
#   谷段 = 其余全部时间（含周末全天）
#
# 切换动作 = 依次 `hermes config set <key> <model>`（默认 key = model.default）。
#
# 用法：
#   tools/peak_switch.sh                  # 按当前时间切换
#   tools/peak_switch.sh --dry-run        # 只打印将执行的命令，不落盘（CI / 巡检可调用）
#   tools/peak_switch.sh --now "1 09 30"  # 指定 <星期(1-7)> <时> <分>（排错 / 回归用）
#   tools/peak_switch.sh --rekey          # 切换后重签挂起任务（工单241 任务三）
#   tools/peak_switch.sh --help
#
# 可覆盖的环境变量：
#   PEAK_MODEL    峰段模型名（默认 MiniMax-M3）
#   VALLEY_MODEL  谷段模型名（默认 deepseek-flash）
#   CONFIG_KEYS   要写入的配置键，空格分隔（默认 "model.default"），按给定顺序逐个调用
#   HERMES_BIN    hermes 可执行文件（默认 hermes）
#   DATE_BIN      date 可执行文件（默认 date；回归测试注入假 date 用）
#   AGENT_REKEY   置 1/on/true/yes 等价于 --rekey（默认关；关闭时本脚本行为与 229 版一字不差）
#   AGENT_REKEY_BIN  重签脚本路径（默认 <脚本目录>/agent_rekey.sh；回归测试注入假脚本用）
#
# 退出码：0 = 切换成功 / 正常 dry-run；2 = 参数错误；其余 = hermes 的退出码透传
set -eu

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

PEAK_MODEL="${PEAK_MODEL:-MiniMax-M3}"
VALLEY_MODEL="${VALLEY_MODEL:-deepseek-flash}"
CONFIG_KEYS="${CONFIG_KEYS:-model.default}"
HERMES_BIN="${HERMES_BIN:-hermes}"
DATE_BIN="${DATE_BIN:-date}"

DRY_RUN=0
NOW=""
# 工单241 任务三：provider 变更后是否重签挂起任务（默认关，避免改变 229 既有行为）
REKEY_ENABLED=0
case "${AGENT_REKEY:-0}" in
	1 | on | true | yes) REKEY_ENABLED=1 ;;
esac

usage() {
	cat <<'EOF'
用法: peak_switch.sh [--dry-run] [--now "<星期(1-7)> <时> <分>"] [--rekey] [--help]

  --dry-run   只打印将执行的 hermes 命令，不实际切换
  --now       指定时间快照（1=周一 … 7=周日），排错 / 回归用；缺省读当前时间
  --rekey     切换后调用 tools/agent_rekey.sh 重签挂起任务（等价 AGENT_REKEY=1）

峰段 = 工作日 09:00-12:00 与 14:00-18:00（左闭右开）；其余为谷段。
EOF
}

while [ $# -gt 0 ]; do
	case "$1" in
		--dry-run) DRY_RUN=1 ;;
		--rekey) REKEY_ENABLED=1 ;;
		--now)
			shift
			[ $# -ge 1 ] || { echo "错误: --now 缺少参数" >&2; exit 2; }
			NOW="$1"
			;;
		--help | -h)
			usage
			exit 0
			;;
		*)
			echo "错误: 未知参数 $1" >&2
			usage >&2
			exit 2
			;;
	esac
	shift
done

if [ -n "$NOW" ]; then
	# shellcheck disable=SC2086  # 有意按空白拆成 <星期> <时> <分>
	set -- $NOW
else
	# shellcheck disable=SC2086  # 有意按空白拆分 date 的输出
	set -- $("$DATE_BIN" "+%u %H %M")
fi
[ $# -eq 3 ] || { echo "错误: 时间快照需为 '<星期 1-7> <时> <分>'，收到: ${NOW:-<date 输出异常>}" >&2; exit 2; }
DOW="$1"
HOUR="$2"
MINUTE="$3"

# 命中峰段返回 0，否则返回 1。
# ⚠️ 这里**必须**是 POSIX sh：测试是用 `sh tools/peak_switch.sh` 调的（Ubuntu 上 sh=dash）。
# 所以不能用 bash 的 `$((10#$x))` 强制十进制 —— dash 会报 `arithmetic expression: expecting primary`
# （CI 上 19 条用例就是这么挂的）。POSIX 做法：先剥掉前导 0 再按十进制算，08/09 才不会被当八进制。
_dec() {
	_v=$(printf '%s' "$1" | sed 's/^0*//')
	printf '%s' "${_v:-0}"
}

is_peak() {
	case "$1" in "" | *[!0-9]*) return 1 ;; esac
	case "$2" in "" | *[!0-9]*) return 1 ;; esac
	case "$3" in "" | *[!0-9]*) return 1 ;; esac
	[ "$1" -ge 6 ] && return 1 # 周六(6) / 周日(7)：全天谷段
	_ph=$(_dec "$2")
	_pm=$(_dec "$3")
	minutes=$((_ph * 60 + _pm))
	if [ "$minutes" -ge 540 ] && [ "$minutes" -lt 720 ]; then return 0; fi  # 09:00-12:00
	if [ "$minutes" -ge 840 ] && [ "$minutes" -lt 1080 ]; then return 0; fi # 14:00-18:00
	return 1
}

if is_peak "$DOW" "$HOUR" "$MINUTE"; then
	SEGMENT=peak
	MODEL="$PEAK_MODEL"
else
	SEGMENT=valley
	MODEL="$VALLEY_MODEL"
fi

echo "时间快照: 星期${DOW} ${HOUR}:${MINUTE} → ${SEGMENT}段 → ${MODEL}"

for key in $CONFIG_KEYS; do
	if [ "$DRY_RUN" -eq 1 ]; then
		echo "[dry-run] ${HERMES_BIN} config set ${key} ${MODEL}"
	else
		"$HERMES_BIN" config set "$key" "$MODEL"
	fi
done

# 工单241 任务三：provider 变了 → 旧 provider 签的挂起任务要重签，否则审计无法回溯。
# 默认关（REKEY_ENABLED=0），因此本段在关闭时对 stdout / hermes 调用序列零影响。
if [ "$REKEY_ENABLED" -eq 1 ]; then
	REKEY_BIN="${AGENT_REKEY_BIN:-$SCRIPT_DIR/agent_rekey.sh}"
	if [ "$DRY_RUN" -eq 1 ]; then
		echo "[dry-run] ${REKEY_BIN} ${MODEL}"
	elif [ -x "$REKEY_BIN" ]; then
		"$REKEY_BIN" "$MODEL"
	else
		echo "警告: 未找到可执行的重签脚本 ${REKEY_BIN}，跳过 re-sign" >&2
	fi
fi
