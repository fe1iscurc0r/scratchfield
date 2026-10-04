/**
 * 悬浮窗几何状态机（纯函数，无 Electron 依赖，可 node:test 单测）。
 *
 * ── 卷149 背景：为什么需要这个模块 ──────────────────────────────
 *
 * 症状：悬浮窗按住不放 → 窗口越来越大 → 增大区域被黑块填充。
 *
 * 根因（代码实测）：**尺寸约束没有单一权威来源**，具体三条：
 *
 * 1. `minimumSize` 被设为"动画目标高度"而非该态的**最小值**。
 *    `expandFloatingWindow` 动画回调里 `setMinimumSize(EXPANDED_WIDTH, targetHeight)`，
 *    而 targetHeight 是动画的初始目标（`INITIAL_FULL_HEIGHT=200`）；
 *    动画结束后渲染层 fitHeight 会把高度收缩到内容实际高度（可低至 `MIN_FIT_HEIGHT=100`）。
 *    ⇒ minimumHeight(200) > bounds.height(100)，
 *      **Windows 会强制把窗口撑到 minimumSize** —— 这就是"被撑大"的直接机制。
 *
 * 2. 动画被拖拽打断时 `onDone` 不执行，`minimumSize` 停在中间态，状态撕裂。
 *    （`setWindowPosition` 在悬浮态会 `cancelCurrentAnimation()`，而 animateBounds
 *      的取消路径不调用 onDone。）
 *
 * 3. 缺少"实际尺寸偏离期望就纠正"的收敛机制。
 *    任何外部尺寸变更（原生 resize / Electron 平台缺陷）都会被**保留并累积**。
 *
 * ── 本模块的职责 ────────────────────────────────────────────
 *
 * 把"某状态下的窗口几何 + 尺寸约束"收敛成**唯一计算入口**，
 * 并提供不变式校验，供 window.ts 在每次状态转换后断言。
 *
 * ★ 核心不变式：`minWidth <= width` 且 `minHeight <= height`。
 *   一旦违反，Windows 就会强制放大窗口到 minimumSize。
 */

export type FloatingState = 'classic' | 'ball' | 'compact' | 'full'

// ── 尺寸常量（唯一真源，window.ts / 渲染层均从此处引用）──────────
export const BALL_SIZE = 100
export const EXPANDED_WIDTH = 420
export const MAX_FULL_HEIGHT = 640
/** full 态允许收缩到的最小高度（无消息时仅头部） */
export const MIN_FIT_HEIGHT = BALL_SIZE
/** 紧凑态与球态同高，展开时仅宽度变化 */
export const COMPACT_HEIGHT = BALL_SIZE
/** 展开到 full 时的动画初始高度，随后由 fitHeight 动态调整 */
export const INITIAL_FULL_HEIGHT = 200
export const CLASSIC_MIN_WIDTH = 800
export const CLASSIC_MIN_HEIGHT = 600
export const CLASSIC_DEFAULT_WIDTH = 1280
export const CLASSIC_DEFAULT_HEIGHT = 800

export interface WindowRectangle {
  x: number
  y: number
  width: number
  height: number
}

export interface FloatingGeometry {
  width: number
  height: number
  minWidth: number
  minHeight: number
  resizable: boolean
}

/** full 态高度钳制到 [MIN_FIT_HEIGHT, MAX_FULL_HEIGHT]；非法输入退化为最小高度 */
export function clampFullHeight(height: number): number {
  if (!Number.isFinite(height))
    return MIN_FIT_HEIGHT
  return Math.max(MIN_FIT_HEIGHT, Math.min(Math.round(height), MAX_FULL_HEIGHT))
}

/**
 * 计算某状态下的窗口几何与尺寸约束。
 *
 * 所有状态转换（enter / expand / expandToFull / collapse / collapseToCompact /
 * fitHeight）都必须经此函数取几何，**不得再散落 setMinimumSize 调用**。
 */
export function computeFloatingGeometry(
  state: FloatingState,
  fullHeight: number = MIN_FIT_HEIGHT,
  classic?: { width: number, height: number },
): FloatingGeometry {
  switch (state) {
    case 'ball':
      return {
        width: BALL_SIZE,
        height: BALL_SIZE,
        minWidth: BALL_SIZE,
        minHeight: BALL_SIZE,
        resizable: false,
      }

    case 'compact':
      return {
        width: EXPANDED_WIDTH,
        height: COMPACT_HEIGHT,
        minWidth: EXPANDED_WIDTH,
        minHeight: COMPACT_HEIGHT,
        resizable: false,
      }

    case 'full': {
      const height = clampFullHeight(fullHeight)
      return {
        width: EXPANDED_WIDTH,
        height,
        minWidth: EXPANDED_WIDTH,
        // ★ 关键：最小值恒为 MIN_FIT_HEIGHT，**不是**当前目标高度。
        //   若写成 height，内容收缩时 minimumSize 会高于 bounds → 被强制撑大。
        minHeight: MIN_FIT_HEIGHT,
        resizable: false,
      }
    }

    case 'classic':
    default:
      return {
        width: classic?.width ?? CLASSIC_DEFAULT_WIDTH,
        height: classic?.height ?? CLASSIC_DEFAULT_HEIGHT,
        minWidth: CLASSIC_MIN_WIDTH,
        minHeight: CLASSIC_MIN_HEIGHT,
        resizable: true,
      }
  }
}

/** 返回不变式违规清单；空数组 = 通过。供 window.ts 每次转换后断言。 */
export function checkGeometryInvariants(geometry: FloatingGeometry): string[] {
  const violations: string[] = []

  if (!Number.isFinite(geometry.width) || geometry.width <= 0)
    violations.push(`width 非法: ${geometry.width}`)
  if (!Number.isFinite(geometry.height) || geometry.height <= 0)
    violations.push(`height 非法: ${geometry.height}`)

  if (geometry.minWidth > geometry.width)
    violations.push(`minWidth(${geometry.minWidth}) > width(${geometry.width})`)
  if (geometry.minHeight > geometry.height)
    violations.push(`minHeight(${geometry.minHeight}) > height(${geometry.height})`)

  return violations
}

/** 尺寸是否在容差内 —— 供"期望尺寸守卫"判定实际尺寸是否偏离。 */
export function isSizeWithinTolerance(
  actual: { width: number, height: number },
  expected: { width: number, height: number },
  tolerancePx: number = 0,
): boolean {
  return Math.abs(actual.width - expected.width) <= tolerancePx
    && Math.abs(actual.height - expected.height) <= tolerancePx
}

/**
 * fitHeight 反馈环趋势守卫。
 *
 * 渲染层原有的 `_lastFitHeight` 相同值守卫**挡不住递增环**：
 * 窗口变大 → 内容 scrollHeight 变大 → desired 变大 → 窗口再变大 → …
 *
 * 本守卫按"连续递增次数"判定环：达到 limit 次即拒绝该次 fit 并告警。
 * 判环后**立即归零 streak**，避免误判（用户真的连续输入多行）导致永久锁死。
 */
export class FitHeightTrendGuard {
  private last = 0
  private risingStreak = 0
  private readonly limit: number

  constructor(limit = 5) {
    this.limit = Math.max(2, Math.floor(limit))
  }

  record(desired: number): { accept: boolean, reason?: string, streak: number } {
    if (desired > this.last)
      this.risingStreak++
    else if (desired < this.last)
      this.risingStreak = 0

    this.last = desired

    if (this.risingStreak >= this.limit) {
      const streak = this.risingStreak
      this.risingStreak = 0 // 判环即归零：下一次仍可正常 fit，不永久锁死
      return { accept: false, reason: `fitHeight 连续递增 ${streak} 次，判定反馈环`, streak }
    }

    return { accept: true, streak: this.risingStreak }
  }

  reset(): void {
    this.last = 0
    this.risingStreak = 0
  }
}
