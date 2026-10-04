/**
 * 前后端键名转换单测（keyCase.ts，W100-03）。
 */
import assert from 'node:assert/strict'
import test from 'node:test'

import { toCamel, toSnake } from '../src/utils/keyCase.ts'

test('toSnake：请求体 camelCase → snake_case（deep）', () => {
  const out = toSnake({ maxTokens: 1000, nested: { streamMode: true } })
  assert.deepEqual(out, { max_tokens: 1000, nested: { stream_mode: true } })
})

test('toCamel：响应体 snake_case → camelCase（deep）', () => {
  const out = toCamel('{"session_id":"abc","nested":{"has_more":true}}')
  assert.deepEqual(out, { sessionId: 'abc', nested: { hasMore: true } })
})

test('toSnake/toCamel 互逆', () => {
  const payload = { activeTabId: 'lumo', chatHistory: [{ role: 'user', contentText: 'hi' }] }
  const round = toCamel(JSON.stringify(toSnake(payload)))
  assert.deepEqual(round, payload)
})
