/**
 * HTML 实体解码单测（htmlEntities.ts，W100-03 · Markdown.vue 纯部分）。
 */
import assert from 'node:assert/strict'
import test from 'node:test'

import { decodeHtmlEntities } from '../src/utils/htmlEntities.ts'

test('decodeHtmlEntities：四种实体解码', () => {
  assert.equal(decodeHtmlEntities('a &amp; b'), 'a & b')
  assert.equal(decodeHtmlEntities('&lt;tag&gt;'), '<tag>')
  assert.equal(decodeHtmlEntities('&quot;x&quot;'), '"x"')
})

test('decodeHtmlEntities：无实体原样返回', () => {
  assert.equal(decodeHtmlEntities('plain text'), 'plain text')
})

test('decodeHtmlEntities：连续多实体', () => {
  assert.equal(decodeHtmlEntities('&lt;a&gt;&amp;&quot;b&quot;'), '<a>&"b"')
})
