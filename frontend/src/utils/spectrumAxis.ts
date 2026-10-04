/**
 * 频谱面板坐标轴刻度计算（纯函数，无 DOM 依赖，可离线单测）
 *
 * 修复的两个历史缺陷：
 *  - 纵轴步进写死 10 dB 且循环不看上限，刻度间距可小于字高导致重叠，还会画进瀑布区；
 *  - 横轴阶梯最小只有 0.5 MHz，HF 常见的 kHz 级跨度下一次循环都不执行，横轴整条空白。
 *
 * 阶梯取值序列（1/2/5 × 10^k）与 GQRX/SDR++ 等频谱仪的刻度语义一致，
 * 为通用数学习惯，非任何上游代码移植。
 */

const DB_LADDER = [1, 2, 5, 10, 20, 25, 50] as const
const HZ_LADDER = [1, 2, 5] as const

/** 在阶梯 1/2/5×10^k 中取不小于 raw 的最小步进。 */
function niceStep(raw: number, ladder: readonly number[]): number {
  const mag = 10 ** Math.floor(Math.log10(raw))
  for (const m of ladder) {
    if (mag * m >= raw - 1e-12)
      return mag * m
  }
  return mag * 10
}

export interface DbTick {
  db: number
  /** (db - lo) / (hi - lo)，0=轴底 1=轴顶 */
  ratio: number
}

/**
 * 纵轴 dB 刻度：只落在可见区间 [lo, hi] 内，且相邻刻度的像素间距不小于 minPitchPx。
 * lo/hi 来自用户可调的底噪/上限，因此刻度随量程自适应（老实现间距 11.7px < 字高必重叠）。
 */
export function dbTicks(
  lo: number,
  hi: number,
  plotHeightPx: number,
  minPitchPx = 18,
): DbTick[] {
  if (!Number.isFinite(lo) || !Number.isFinite(hi) || !(hi > lo) || !(plotHeightPx > 0))
    return []
  const maxTicks = Math.max(2, Math.floor(plotHeightPx / Math.max(8, minPitchPx)))
  const step = niceStep((hi - lo) / maxTicks, DB_LADDER)
  const out: DbTick[] = []
  // 从区间内第一个步进整数倍开始，避免画出 [lo, hi] 之外的刻度
  const first = Math.ceil(lo / step) * step
  for (let i = 0; ; i++) {
    const db = Math.round((first + i * step) * 1e6) / 1e6
    if (db > hi + 1e-9)
      break
    out.push({ db, ratio: (db - lo) / (hi - lo) })
    if (out.length > 200)
      break
  }
  return out
}

export interface HzTick {
  hz: number
  /** 相对 [f0, f1] 的 0..1 位置 */
  ratio: number
}

/**
 * 横轴频率刻度：阶梯覆盖 Hz→GHz 全量级（1/2/5×10^k），
 * kHz 级窄跨度（HF 声卡频谱常态）也能取到合理步进。
 */
export function freqTicks(
  f0: number,
  f1: number,
  plotWidthPx: number,
  minPitchPx = 64,
): HzTick[] {
  if (!Number.isFinite(f0) || !Number.isFinite(f1) || !(f1 > f0) || !(plotWidthPx > 0))
    return []
  const maxTicks = Math.max(2, Math.floor(plotWidthPx / Math.max(16, minPitchPx)))
  const step = niceStep((f1 - f0) / maxTicks, HZ_LADDER)
  const out: HzTick[] = []
  const first = Math.ceil(f0 / step) * step
  for (let i = 0; ; i++) {
    const hz = first + i * step
    if (hz > f1 + 1e-6)
      break
    out.push({ hz, ratio: (hz - f0) / (f1 - f0) })
    if (out.length > 400)
      break
  }
  return out
}

/** 刻度标签的小数位：由步进量级反推（步进 5 kHz → 0.005 MHz → 3 位）。 */
export function freqTickDecimals(stepHz: number): number {
  if (!(stepHz > 0))
    return 3
  const stepMhz = stepHz / 1e6
  const dec = Math.ceil(-Math.log10(stepMhz) - 1e-9)
  return Math.min(6, Math.max(stepMhz >= 1 ? 1 : 0, dec))
}

export function formatFreqTick(hz: number, stepHz: number): string {
  return (hz / 1e6).toFixed(freqTickDecimals(stepHz))
}

/** RBW 显示：小于 1 kHz 用 Hz，避免出现 "0.0 kHz" 这种丢精度的读数。 */
export function formatRbw(rbwHz: number): string {
  if (!Number.isFinite(rbwHz) || rbwHz <= 0)
    return '—'
  return rbwHz < 1000 ? `${rbwHz.toFixed(1)} Hz` : `${(rbwHz / 1000).toFixed(1)} kHz`
}

/** 跨度显示：自适应 Hz / kHz / MHz。 */
export function formatSpan(spanHz: number): string {
  if (!Number.isFinite(spanHz) || spanHz <= 0)
    return '—'
  if (spanHz < 1000)
    return `${spanHz.toFixed(0)} Hz`
  if (spanHz < 1e6)
    return `${(spanHz / 1e3).toFixed(1)} kHz`
  return `${(spanHz / 1e6).toFixed(3)} MHz`
}
