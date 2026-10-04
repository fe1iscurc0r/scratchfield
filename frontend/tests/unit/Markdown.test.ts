/**
 * Markdown 挂载级单测（vitest + @vue/test-utils + jsdom）。
 */
import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'

import Markdown from '@/components/Markdown.vue'

describe('Markdown', () => {
  it('渲染基础 markdown 为 HTML', () => {
    const w = mount(Markdown, { props: { source: '# 标题\n\n**粗体**' } })
    expect(w.html()).toContain('<h1')
    expect(w.html()).toContain('<strong>粗体</strong>')
  })

  it('XSS 脚本被 DOMPurify 清除', () => {
    const w = mount(Markdown, { props: { source: '<script>alert(1)</script>' } })
    expect(w.html()).not.toContain('<script')
    expect(w.html()).not.toContain('alert(1)')
  })

  it('链接渲染带 target', () => {
    const w = mount(Markdown, { props: { source: '[x](https://example.com)' } })
    expect(w.html()).toContain('href="https://example.com"')
  })

  it('代码块渲染为 pre/code', () => {
    const w = mount(Markdown, { props: { source: '```\nconst a = 1\n```' } })
    expect(w.html()).toContain('<pre')
    expect(w.html()).toContain('<code')
  })
})
