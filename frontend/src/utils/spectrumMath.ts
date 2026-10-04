/**
 * 频谱绘制纯数学（从 SpectrumPanel.vue 抽出，无渲染依赖，可单测）。
 */
export const DB_FLOOR = -120

/** dB(-120..0) → 蓝(底噪)→青→绿→黄→红(强) 渐变 LUT（256 级） */
export function buildColormap(): Uint8ClampedArray {
  const lut = new Uint8ClampedArray(256 * 4)
  const stops: Array<[number, [number, number, number]]> = [
    [0.0, [8, 8, 32]],
    [0.35, [0, 90, 180]],
    [0.6, [0, 200, 120]],
    [0.8, [230, 230, 40]],
    [1.0, [255, 60, 40]],
  ]
  for (let i = 0; i < 256; i++) {
    const t = i / 255
    const last = stops.at(-1)!
    let [r, g, b] = last[1]
    for (let s = 0; s < stops.length - 1; s++) {
      const [t0, c0] = stops[s]!
      const [t1, c1] = stops[s + 1]!
      if (t >= t0 && t <= t1) {
        const f = t1 === t0 ? 0 : (t - t0) / (t1 - t0)
        r = Math.round(c0[0] + (c1[0] - c0[0]) * f)
        g = Math.round(c0[1] + (c1[1] - c0[1]) * f)
        b = Math.round(c0[2] + (c1[2] - c0[2]) * f)
        break
      }
    }
    lut[i * 4 + 0] = r
    lut[i * 4 + 1] = g
    lut[i * 4 + 2] = b
    lut[i * 4 + 3] = 255
  }
  return lut
}

/** dB 值 → 色图索引（DB_FLOOR..0 线性映射到 0..255，越界钳位） */
export function dbIndex(db: number): number {
  const t = (db - DB_FLOOR) / (0 - DB_FLOOR)
  return Math.max(0, Math.min(255, Math.round(t * 255)))
}

/** 底噪估计：取下 20% 分位 - 3dB，钳在 [-120, -30] */
export function estimateNoiseFloor(db: number[]): number {
  const sorted = [...db].filter(v => Number.isFinite(v)).sort((a, b) => a - b)
  if (sorted.length === 0)
    return -120
  const p20 = sorted[Math.floor(sorted.length * 0.2)] ?? -120
  return Math.max(-120, Math.min(-30, Math.round(p20 - 3)))
}
