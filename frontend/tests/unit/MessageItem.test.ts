/**
 * MessageItem 挂载级单测（vitest + @vue/test-utils + jsdom）。
 */
import { describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'

import MessageItem from '@/components/MessageItem.vue'

// session.ts 依赖 useStorage（vueuse），挂载前 mock 掉持久层，只留内存响应式
vi.mock('@/utils/session', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/utils/session')>()
  return {
    ...actual,
    MESSAGES: [],
    CURRENT_SESSION_ID: null,
  }
})

describe('MessageItem', () => {
  it('渲染普通用户消息内容', () => {
    const w = mount(MessageItem, {
      props: { role: 'user', content: '你好', id: 'm1' },
    })
    expect(w.text()).toContain('你好')
  })

  it('无内容生成中显示短语', () => {
    const w = mount(MessageItem, {
      props: { role: 'assistant', content: '', reasoning: '', generating: true, id: 'm2' },
    })
    // 生成短语集之一（Generating/Thinking/Composing/Crafting/… 均以 ... 结尾）
    expect(w.text()).toMatch(/\.\.\.$/)
  })

  it('info 角色渲染分隔线样式', () => {
    const w = mount(MessageItem, {
      props: { role: 'info', content: '会话已切换', id: 'm3' },
    })
    expect(w.find('.info-divider').exists()).toBe(true)
    expect(w.text()).toContain('会话已切换')
  })

  it('无 reasoning 时不渲染思考区', () => {
    const w = mount(MessageItem, {
      props: { role: 'assistant', content: '回答', reasoning: '', id: 'm4' },
    })
    expect(w.find('[class*="reasoning"]').exists()).toBe(false)
  })
})
