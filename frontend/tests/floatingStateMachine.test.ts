/**
 * 悬浮窗几何状态机单测（node:test 风格，参照 windowState.test.ts）。
 *
 * 覆盖：
 * - computeFloatingGeometry 四态几何与约束
 * - ★ 核心不变式 minWidth<=width / minHeight<=height（膨胀机制的直接回归）
 * - clampFullHeight 边界（非法输入 / 上限 / 下限）
 * - isSizeWithinTolerance（期望尺寸守卫的判定基础）
 * - FitHeightTrendGuard（递增环判定 / 归零 / 不永久锁死）
 */
import assert from 'node:assert/strict'
import test from 'node:test'

import {
  BALL_SIZE,
  checkGeometryInvariants,
  clampFullHeight,
  CLASSIC_MIN_HEIGHT,
  CLASSIC_MIN_WIDTH,
  COMPACT_HEIGHT,
  computeFloatingGeometry,
  EXPANDED_WIDTH,
  FitHeightTrendGuard,
  INITIAL_FULL_HEIGHT,
  isSizeWithinTolerance,
  MAX_FULL_HEIGHT,
  MIN_FIT_HEIGHT,
} from '../electron/modules/floatingStateMachine.ts'

// ─── 几何计算 ──────────────────────────────────────────────

test('球态：几何与约束均为 BALL_SIZE 正方形且不可缩放', () => {
  const g = computeFloatingGeometry('ball')
  assert.deepEqual(g, {
    width: BALL_SIZE,
    height: BALL_SIZE,
    minWidth: BALL_SIZE,
    minHeight: BALL_SIZE,
    resizable: false,
  })
})

test('紧凑态：宽度展开到 EXPANDED_WIDTH，高度与球态同高', () => {
  const g = computeFloatingGeometry('compact')
  assert.equal(g.width, EXPANDED_WIDTH)
  assert.equal(g.height, COMPACT_HEIGHT)
  assert.equal(g.resizable, false)
})

test('完整态：高度取 fitHeight 值，最小值恒为 MIN_FIT_HEIGHT', () => {
  const g = computeFloatingGeometry('full', 360)
  assert.equal(g.width, EXPANDED_WIDTH)
  assert.equal(g.height, 360)
  assert.equal(g.minWidth, EXPANDED_WIDTH)
  // ★ 关键断言：最小值不是 360，而是允许收缩到的最小值
  assert.equal(g.minHeight, MIN_FIT_HEIGHT)
})

test('★ 回归：完整态高度收缩到下限时，minimumSize 不得高于 bounds', () => {
  // 这是"按住拖拽窗口被撑大"的直接回归测试。
  // 旧实现把 minimumSize 设为动画目标高度（INITIAL_FULL_HEIGHT=200 或更大），
  // 而 fitHeight 会把高度收缩到 100 → minimumSize(200) > height(100)
  // → Windows 强制把窗口撑到 200，视觉上就是"窗口越来越大"。
  const g = computeFloatingGeometry('full', MIN_FIT_HEIGHT)
  assert.equal(g.height, MIN_FIT_HEIGHT)
  assert.ok(
    g.minHeight <= g.height,
    `minHeight(${g.minHeight}) 必须 <= height(${g.height})`,
  )
  assert.deepEqual(checkGeometryInvariants(g), [])
})

test('★ 回归：展开动画初始高度下，最小值仍不高于实际高度', () => {
  // expandFloatingWindow 的动画目标是 INITIAL_FULL_HEIGHT，
  // 若把 minimumSize 锁成该值，后续内容收缩即触发强制撑大。
  const g = computeFloatingGeometry('full', INITIAL_FULL_HEIGHT)
  assert.equal(g.height, INITIAL_FULL_HEIGHT)
  assert.equal(g.minHeight, MIN_FIT_HEIGHT)
  assert.ok(g.minHeight <= g.height)
})

test('经典态：自定义尺寸生效，约束为 800x600 且可缩放', () => {
  const g = computeFloatingGeometry('classic', MIN_FIT_HEIGHT, { width: 1600, height: 900 })
  assert.equal(g.width, 1600)
  assert.equal(g.height, 900)
  assert.equal(g.minWidth, CLASSIC_MIN_WIDTH)
  assert.equal(g.minHeight, CLASSIC_MIN_HEIGHT)
  assert.equal(g.resizable, true)
})

test('经典态：未传尺寸时回落默认 1280x800', () => {
  const g = computeFloatingGeometry('classic')
  assert.equal(g.width, 1280)
  assert.equal(g.height, 800)
})

// ─── 核心不变式：全状态 × 全高度遍历 ────────────────────────

test('★ 不变式：所有状态在所有高度下都满足 minWidth<=width 且 minHeight<=height', () => {
  const states = ['ball', 'compact', 'full', 'classic'] as const
  // 覆盖边界与非法值
  const heights = [
    -100, 0, 1, 50, MIN_FIT_HEIGHT, 120, INITIAL_FULL_HEIGHT,
    300, 500, MAX_FULL_HEIGHT, MAX_FULL_HEIGHT + 1, 99999,
    Number.NaN, Number.POSITIVE_INFINITY,
  ]

  for (const state of states) {
    for (const h of heights) {
      const g = computeFloatingGeometry(state, h)
      const violations = checkGeometryInvariants(g)
      assert.deepEqual(
        violations,
        [],
        `state=${state} height=${h} 违反不变式: ${violations.join('; ')}`,
      )
    }
  }
})

test('checkGeometryInvariants 能识别被破坏的几何', () => {
  // 反向验证：守卫本身有效（否则上面的遍历是空转）
  assert.deepEqual(
    checkGeometryInvariants({ width: 420, height: 100, minWidth: 420, minHeight: 200, resizable: false }),
    ['minHeight(200) > height(100)'],
  )
  assert.deepEqual(
    checkGeometryInvariants({ width: 100, height: 100, minWidth: 420, minHeight: 100, resizable: false }),
    ['minWidth(420) > width(100)'],
  )
  assert.deepEqual(
    checkGeometryInvariants({ width: 420, height: 0, minWidth: 420, minHeight: 0, resizable: false }),
    ['height 非法: 0'],
  )
})

// ─── 高度钳制 ──────────────────────────────────────────────

test('clampFullHeight：上下限与非法输入', () => {
  assert.equal(clampFullHeight(300), 300)
  assert.equal(clampFullHeight(360.4), 360) // 四舍五入
  assert.equal(clampFullHeight(10), MIN_FIT_HEIGHT) // 低于下限
  assert.equal(clampFullHeight(99999), MAX_FULL_HEIGHT) // 高于上限
  assert.equal(clampFullHeight(Number.NaN), MIN_FIT_HEIGHT) // 非法
  assert.equal(clampFullHeight(Number.NEGATIVE_INFINITY), MIN_FIT_HEIGHT)
})

// ─── 期望尺寸守卫的判定基础 ────────────────────────────────

test('isSizeWithinTolerance：零容差要求完全一致', () => {
  const expected = { width: 420, height: 360 }
  assert.equal(isSizeWithinTolerance({ width: 420, height: 360 }, expected), true)
  assert.equal(isSizeWithinTolerance({ width: 421, height: 360 }, expected), false)
})

test('isSizeWithinTolerance：容差内放行，超差拦截', () => {
  const expected = { width: 420, height: 360 }
  assert.equal(isSizeWithinTolerance({ width: 421, height: 359 }, expected, 2), true)
  assert.equal(isSizeWithinTolerance({ width: 424, height: 360 }, expected, 2), false)
  assert.equal(isSizeWithinTolerance({ width: 420, height: 363 }, expected, 2), false)
})

// ─── fitHeight 反馈环守卫 ──────────────────────────────────

test('FitHeightTrendGuard：连续递增达到上限即判环并拒绝', () => {
  // limit=3 语义：连续递增到第 3 次时判环（不是第 4 次）
  const guard = new FitHeightTrendGuard(3)
  assert.equal(guard.record(100).accept, true) // streak=1
  assert.equal(guard.record(200).accept, true) // streak=2
  const rejected = guard.record(300) // streak=3 → 判环
  assert.equal(rejected.accept, false)
  assert.match(rejected.reason ?? '', /连续递增 3 次/)
})

test('FitHeightTrendGuard：递减会打断递增计数', () => {
  const guard = new FitHeightTrendGuard(3)
  guard.record(100)
  guard.record(200) // streak=1
  guard.record(150) // 递减 → 归零
  assert.equal(guard.record(160).accept, true) // streak=1
  assert.equal(guard.record(170).accept, true) // streak=2
})

test('FitHeightTrendGuard：相同值不累加递增计数', () => {
  const guard = new FitHeightTrendGuard(2)
  guard.record(100)
  assert.equal(guard.record(100).accept, true)
  assert.equal(guard.record(100).accept, true)
})

test('FitHeightTrendGuard：判环后归零，不会永久锁死后续 fit', () => {
  const guard = new FitHeightTrendGuard(2)
  guard.record(100)
  assert.equal(guard.record(200).accept, false) // streak 达 2 → 判环
  // 归零后，新的递增序列应当重新被接受（避免用户真实连续输入被永久拒绝）
  assert.equal(guard.record(250).accept, true)
  assert.equal(guard.record(300).accept, false)
})

test('FitHeightTrendGuard：reset 清空历史', () => {
  const guard = new FitHeightTrendGuard(2)
  guard.record(100)
  guard.record(200)
  guard.reset()
  assert.equal(guard.record(300).accept, true)
})
