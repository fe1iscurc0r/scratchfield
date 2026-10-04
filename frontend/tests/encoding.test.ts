/**
 * SSE 流解码单测（encoding.ts，W100-03）。
 */
import assert from 'node:assert/strict'
import test from 'node:test'

import { decodeStreamChunk } from '../src/utils/encoding.ts'

test('decodeStreamChunk：JSON 事件解析为结构化 chunk', () => {
  const chunk = decodeStreamChunk('{"type":"round_start","round":2}')
  assert.equal(chunk.type, 'round_start')
  assert.equal(chunk.round, 2)
})

test('decodeStreamChunk：纯文本降级为 content', () => {
  const chunk = decodeStreamChunk('你好，世界')
  assert.equal(chunk.type, 'content')
  assert.equal(chunk.text, '你好，世界')
})

test('decodeStreamChunk：非法 JSON 降级不抛', () => {
  const chunk = decodeStreamChunk('{not json')
  assert.equal(chunk.type, 'content')
})

test('decodeStreamChunk：缺 type 字段的对象降级', () => {
  const chunk = decodeStreamChunk('{"foo":1}')
  assert.equal(chunk.type, 'content')
  assert.equal(chunk.text, '{"foo":1}')
})
