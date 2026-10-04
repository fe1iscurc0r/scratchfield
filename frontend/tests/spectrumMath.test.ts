/**
 * SpectrumPanel 纯数学单测（spectrumMath.ts，W100-03）。
 */
import assert from 'node:assert/strict'
import test from 'node:test'

import { buildColormap, dbIndex, DB_FLOOR, estimateNoiseFloor } from '../src/utils/spectrumMath.ts'

test('dbIndex 线性映射：底噪 → 0，0dB → 255', () => {
  assert.equal(dbIndex(DB_FLOOR), 0)
  assert.equal(dbIndex(0), 255)
  assert.equal(dbIndex(-60), 128) // -60 在 [-120,0] 中点
})

test('dbIndex 越界钳位', () => {
  assert.equal(dbIndex(-200), 0)
  assert.equal(dbIndex(100), 255)
})

test('buildColormap LUT 形状与透明度', () => {
  const lut = buildColormap()
  assert.equal(lut.length, 256 * 4)
  for (let i = 0; i < 256; i++)
    assert.equal(lut[i * 4 + 3], 255) // alpha 恒 255
  // 首尾渐变色符合预设（底噪暗蓝 / 强信号红）
  assert.deepEqual([lut[0], lut[1], lut[2]], [8, 8, 32])
  assert.deepEqual([lut[255 * 4], lut[255 * 4 + 1], lut[255 * 4 + 2]], [255, 60, 40])
})

test('estimateNoiseFloor 空输入 → -120', () => {
  assert.equal(estimateNoiseFloor([]), -120)
  assert.equal(estimateNoiseFloor([NaN, Infinity]), -120)
})

test('estimateNoiseFloor 下分位估计与钳位', () => {
  // 纯底噪 -100dB → 20% 分位 -100 → -103 钳到 [-120,-30] 内
  const noise = Array.from({ length: 100 }, () => -100)
  const est = estimateNoiseFloor(noise)
  assert.equal(est, -103)
  assert.ok(est >= -120 && est <= -30)
  // 强信号抬底（-50）→ 估计上移但不过 -30
  const loud = Array.from({ length: 100 }, () => -50)
  const est2 = estimateNoiseFloor(loud)
  assert.equal(est2, -53)
})
