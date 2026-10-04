/**
 * 悬浮球展开定位纯函数（从 window.ts 抽出，无 Electron 依赖，可单测）。
 *
 * 规则（与抽出前一致）：
 * - 水平：从球位置向右展开；面板右缘超出屏幕时整体左移；负值钳到 0。
 * - 垂直：面板顶部与球顶部对齐；底部超出工作区时上移；负值钳到 0。
 */

export const EXPANDED_WIDTH = 420

export interface ExpandPosition {
  x: number
  y: number
}

export function calcExpandPosition(
  ballX: number,
  ballY: number,
  targetHeight: number,
  screenW: number,
  screenH: number,
): ExpandPosition {
  // 水平方向：球在面板左边缘
  let expandX = ballX
  if (expandX + EXPANDED_WIDTH > screenW)
    expandX = screenW - EXPANDED_WIDTH
  if (expandX < 0)
    expandX = 0

  // 垂直方向：面板顶部与球顶部对齐，空间不足时上移
  let expandY = ballY
  if (expandY + targetHeight > screenH)
    expandY = screenH - targetHeight
  if (expandY < 0)
    expandY = 0

  return { x: expandX, y: expandY }
}
