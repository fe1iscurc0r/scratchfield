/**
 * 对象工具纯函数单测（object.ts，W100-03）。
 */
import assert from 'node:assert/strict'
import test from 'node:test'

import { deepClone, deepMerge } from '../src/utils/object.ts'

test('deepClone：深拷贝与源互不影响', () => {
  const src = { a: 1, b: { c: [1, 2, 3] } }
  const clone = deepClone(src)
  assert.deepEqual(clone, src)
  clone.b.c.push(4)
  assert.deepEqual(src.b.c, [1, 2, 3])
})

test('deepClone：循环引用不炸', () => {
  const src: Record<string, unknown> = { a: 1 }
  src.self = src
  const clone = deepClone(src)
  assert.equal(clone.self, clone)
})

test('deepMerge：浅层覆盖 + 深层递归合并', () => {
  const base = { a: 1, b: { x: 1, y: 2 } }
  const extra = { b: { y: 3, z: 4 }, c: 5 }
  const merged = deepMerge(base, extra)
  assert.deepEqual(merged, { a: 1, b: { x: 1, y: 3, z: 4 }, c: 5 })
  // 原对象不被污染
  assert.deepEqual(base, { a: 1, b: { x: 1, y: 2 } })
})
