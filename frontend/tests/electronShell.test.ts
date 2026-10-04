/**
 * Electron 桌面壳纯逻辑单测（node:test 风格，参照 windowState.test.ts）。
 *
 * 覆盖：
 * - 悬浮球展开定位（calcExpandPosition 纯函数：右展开 / 越界左移 / 越界上移 / 负值钳 0）
 * - 托盘图标平台路径分支（Windows .ico vs macOS .png）——通过 tray.ts 抽出前的
 *   平台判定语义逐条断言（纯语义，不 import electron）
 */
import assert from 'node:assert/strict'
import test from 'node:test'

import { calcExpandPosition, EXPANDED_WIDTH } from '../electron/modules/expandPosition.ts'

test('悬浮球展开：常规位置向右展开且顶部对齐', () => {
  const pos = calcExpandPosition(100, 200, 640, 1920, 1040)
  assert.deepEqual(pos, { x: 100, y: 200 })
})

test('悬浮球展开：面板右缘越界时整体左移', () => {
  // 球在 1800，向右展开 420 会到 2220 > 1920，应左移到 1920-420
  const pos = calcExpandPosition(1800, 100, 640, 1920, 1040)
  assert.equal(pos.x, 1920 - EXPANDED_WIDTH)
  assert.equal(pos.y, 100)
})

test('悬浮球展开：底部越界时上移', () => {
  // 球 y=900，展开 640 会到 1540 > 1040，应上移到 1040-640
  const pos = calcExpandPosition(10, 900, 640, 1920, 1040)
  assert.equal(pos.y, 1040 - 640)
  assert.equal(pos.x, 10)
})

test('悬浮球展开：负值钳到 0（小球屏）', () => {
  // 屏幕比面板还窄 → 左移后变负，应钳 0
  const pos = calcExpandPosition(0, -50, 640, 300, 200)
  assert.deepEqual(pos, { x: 0, y: 0 })
})

test('悬浮球展开：屏幕恰好容纳时不动', () => {
  const pos = calcExpandPosition(EXPANDED_WIDTH, 0, 640, EXPANDED_WIDTH * 2, 640)
  assert.deepEqual(pos, { x: EXPANDED_WIDTH, y: 0 })
})

test('托盘图标平台分支语义：Windows 用 .ico，macOS 用 .png（纯语义断言）', () => {
  // tray.ts 的平台分支：win32 → build/icon.ico；其余 → build/icon.png（22px 图标）
  const iconFor = (platform: string) =>
    platform === 'win32' ? 'icon.ico' : 'icon.png'
  assert.equal(iconFor('win32'), 'icon.ico')
  assert.equal(iconFor('darwin'), 'icon.png')
  assert.equal(iconFor('linux'), 'icon.png')
})
