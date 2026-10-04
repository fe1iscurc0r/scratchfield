/**
 * 工具事件载荷格式化单测（toolPayload.ts，W100-03 · MessageItem.vue 纯部分）。
 */
import assert from 'node:assert/strict'
import test from 'node:test'

import { formatToolPayload, toolBody, toolSummary } from '../src/utils/toolPayload.ts'

test('formatToolPayload：null/undefined → 空串', () => {
  assert.equal(formatToolPayload(null), '')
  assert.equal(formatToolPayload(undefined), '')
})

test('formatToolPayload：字符串直通、对象转 JSON', () => {
  assert.equal(formatToolPayload('raw'), 'raw')
  assert.equal(formatToolPayload({ a: 1 }), '{\n  "a": 1\n}')
})

test('formatToolPayload：不可序列化对象降级 String', () => {
  const evil: Record<string, unknown> = {}
  evil.self = evil
  assert.ok(formatToolPayload(evil).startsWith('[object'))
})

test('toolSummary：调用/成功/失败三种形态', () => {
  assert.equal(toolSummary({ name: 'read_freq', type: 'tool_call' }), '🔧 read_freq')
  assert.equal(toolSummary({ name: 'read_freq', isError: false }), '✅ read_freq')
  assert.equal(toolSummary({ name: 'read_freq', isError: true }), '❌ read_freq')
})

test('toolBody：调用取 args，结果取 result', () => {
  assert.equal(toolBody({ type: 'tool_call', args: { freq: 7 } }), '{\n  "freq": 7\n}')
  assert.equal(toolBody({ result: 'done' }), 'done')
})
