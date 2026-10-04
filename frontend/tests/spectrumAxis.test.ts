import assert from 'node:assert/strict'
import test from 'node:test'
import {
  dbTicks,
  formatRbw,
  formatSpan,
  freqTickDecimals,
  freqTicks,
} from '../src/utils/spectrumAxis.ts'

/** 相邻刻度的最小像素间距（等比映射）。 */
function minPitch(ticks: number[], spanPx: number, lo: number, hi: number): number {
  if (ticks.length < 2)
    return Number.POSITIVE_INFINITY
  let min = Number.POSITIVE_INFINITY
  for (let i = 1; i < ticks.length; i++) {
    const p = ((ticks[i]! - ticks[i - 1]!) / (hi - lo)) * spanPx
    if (p < min)
      min = p
  }
  return min
}

test('纵轴：满量程 -120..0 在 140px 内刻度不再重叠（回归 D1）', () => {
  const ticks = dbTicks(-120, 0, 140)
  const dbs = ticks.map(t => t.db)
  // 旧实现固定 10dB 步进 → 13 个刻度、间距 11.7px < 字高必重叠
  assert.ok(ticks.length <= 8, `刻度过多: ${dbs.join(',')}`)
  assert.ok(minPitch(dbs, 140, -120, 0) >= 18, `最小间距不足: ${minPitch(dbs, 140, -120, 0)}`)
})

test('纵轴：上限为负时刻度全部落在可见区间，不再画进瀑布区（回归 D1）', () => {
  for (const [lo, hi] of [[-120, -60], [-90, -30], [-100, 0], [-30, -5], [-140, -10]]) {
    const ticks = dbTicks(lo, hi, 150)
    assert.ok(ticks.length > 0, `${lo}..${hi} 无刻度`)
    for (const t of ticks) {
      assert.ok(t.db >= lo - 1e-9 && t.db <= hi + 1e-9, `${t.db} 超出 [${lo},${hi}]`)
      assert.ok(t.ratio >= 0 && t.ratio <= 1, `ratio 越界: ${t.ratio}`)
    }
    assert.ok(minPitch(ticks.map(t => t.db), 150, lo, hi) >= 18, `${lo}..${hi} 间距不足`)
  }
})

test('纵轴：非法输入返回空数组', () => {
  assert.deepEqual(dbTicks(0, 0, 140), [])
  assert.deepEqual(dbTicks(-10, -120, 140), [])
  assert.deepEqual(dbTicks(-120, 0, 0), [])
  assert.deepEqual(dbTicks(Number.NaN, 0, 140), [])
})

test('横轴：kHz 级窄跨度不再整条空白（回归 D2）', () => {
  // 实测场景：48kHz 音频源 rfft 单边谱，跨度仅 24 kHz —— 旧阶梯最小 0.5MHz，0 个刻度
  const f0 = 7_101_000
  const f1 = 7_125_000
  const ticks = freqTicks(f0, f1, 783)
  assert.ok(ticks.length >= 2, 'kHz 级跨度必须产生刻度')
  for (const t of ticks) {
    assert.ok(t.hz >= f0 - 1e-6 && t.hz <= f1 + 1e-6, `${t.hz} 超出 [${f0},${f1}]`)
    assert.ok(t.ratio >= 0 && t.ratio <= 1)
  }
  // 步进应为 kHz 量级（1/2/5×10^k）
  const step = ticks[1]!.hz - ticks[0]!.hz
  assert.ok(step >= 1000 && step <= 5000, `步进异常: ${step}`)
  // 刻度标签需能区分（3 位小数）
  assert.equal(freqTickDecimals(step), 3)
})

test('横轴：MHz 级宽带与 Hz 级极窄跨度都自适应', () => {
  const wide = freqTicks(88_000_000, 108_000_000, 800)
  assert.ok(wide.length >= 4 && wide.length <= 20, `宽带刻度数异常: ${wide.length}`)
  const narrow = freqTicks(7_100_000, 7_100_500, 800)
  assert.ok(narrow.length >= 2, '500Hz 跨度应产生刻度')
  assert.equal(freqTickDecimals(narrow[1]!.hz - narrow[0]!.hz) >= 3, true)
})

test('横轴：非法输入返回空数组', () => {
  assert.deepEqual(freqTicks(100, 100, 800), [])
  assert.deepEqual(freqTicks(200, 100, 800), [])
  assert.deepEqual(freqTicks(0, 100, 0), [])
})

test('RBW 与跨度格式化不再出现 0.0 kHz 丢精度（回归 D5）', () => {
  // 实测：24000Hz / 512 bin ≈ 46.9 Hz，旧实现显示 "0.0 kHz"
  assert.equal(formatRbw(24000 / 512), '46.9 Hz')
  assert.equal(formatRbw(2400), '2.4 kHz')
  assert.equal(formatSpan(24_000), '24.0 kHz')
  assert.equal(formatSpan(20_000_000), '20.000 MHz')
  assert.equal(formatSpan(500), '500 Hz')
  assert.equal(formatRbw(0), '—')
})
