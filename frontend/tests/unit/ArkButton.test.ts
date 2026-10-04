/**
 * ArkButton 挂载级单测（vitest + @vue/test-utils + jsdom）。
 */
import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'

import ArkButton from '@/components/ArkButton.vue'

describe('ArkButton', () => {
  it('默认标题从 title prop 渲染（v-html）', () => {
    const w = mount(ArkButton, { props: { title: '对话' } })
    expect(w.html()).toContain('对话')
  })

  it('subtitle 渲染', () => {
    const w = mount(ArkButton, { props: { title: '主', subtitle: '副' } })
    expect(w.text()).toContain('副')
  })

  it('slot 优先于 title', () => {
    const w = mount(ArkButton, { props: { title: '忽略我' }, slots: { default: '<span>自定义内容</span>' } })
    expect(w.text()).toContain('自定义内容')
    expect(w.text()).not.toContain('忽略我')
  })

  it('disabled 属性透传且样式降亮', () => {
    const w = mount(ArkButton, { props: { title: 'x', disabled: true } })
    expect(w.find('button').attributes('disabled')).toBeDefined()
    expect(w.find('button').classes()).toContain('brightness-60')
  })

  it('size=md 走紧凑类', () => {
    const w = mount(ArkButton, { props: { title: 'x', size: 'md' } })
    expect(w.find('div.flex').classes()).toContain('text-2xl')
  })

  it('icon 渲染为 img', () => {
    const w = mount(ArkButton, { props: { title: 'x', icon: 'data:image/png;base64,xx' } })
    expect(w.find('img').exists()).toBe(true)
  })
})
