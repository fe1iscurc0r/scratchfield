/**
 * TagBadge 挂载级单测（卷164 · vitest + @vue/test-utils + jsdom）。
 *
 * 覆盖：置信度显示 / 低置信「待复核」样式 / 人工角标 / 点击复核事件。
 */
import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'

import TagBadge from '@/components/TagBadge.vue'

describe('TagBadge', () => {
  it('显示标签与置信度小数', () => {
    const w = mount(TagBadge, { props: { label: '合同纠纷', confidence: 0.87 } })
    expect(w.text()).toContain('合同纠纷')
    expect(w.text()).toContain('0.87')
  })

  it('高置信不显示「待复核」', () => {
    const w = mount(TagBadge, { props: { label: '合同纠纷', confidence: 0.87 } })
    expect(w.text()).not.toContain('待复核')
    expect(w.text()).not.toContain('人工')
  })

  it('低于阈值显示「待复核」且为黄色样式', () => {
    const w = mount(TagBadge, { props: { label: '事实认定', confidence: 0.42, threshold: 0.6 } })
    expect(w.text()).toContain('待复核')
    expect(w.find('span').classes().join(' ')).toContain('amber')
  })

  it('human=true 显示「人工」角标且不判低置信', () => {
    const w = mount(TagBadge, { props: { label: '法律适用', confidence: 1, human: true } })
    expect(w.text()).toContain('人工')
    expect(w.text()).not.toContain('待复核')
  })

  it('clickable + 低置信时点击 emit review', async () => {
    const w = mount(TagBadge, {
      props: { label: '事实认定', confidence: 0.3, clickable: true },
    })
    await w.trigger('click')
    expect(w.emitted('review')).toHaveLength(1)
  })

  it('clickable 但高置信时不触发 review', async () => {
    const w = mount(TagBadge, {
      props: { label: '合同纠纷', confidence: 0.9, clickable: true },
    })
    await w.trigger('click')
    expect(w.emitted('review')).toBeUndefined()
  })

  it('省略 confidence 时只显示标签', () => {
    const w = mount(TagBadge, { props: { label: '指导性案例' } })
    expect(w.text()).toContain('指导性案例')
    expect(w.text()).not.toContain('待复核')
  })

  it('布尔 true 值以「是」显示', () => {
    const w = mount(TagBadge, { props: { label: '是', confidence: 0.95 } })
    expect(w.text()).toContain('是')
  })
})
