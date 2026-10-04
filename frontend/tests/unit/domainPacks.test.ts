/**
 * 卷162 · 领域包前端消费逻辑测试。
 *
 * 重点验证「default 包零回归」：把后端 `/api/domains` 返回的 default 包
 * form_fields 与改造前 ElnView 手写表单的字段序列逐项比对，确保一致。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'

/** 与改造前 ElnView.vue 手写表单逐字段一致（顺序/label/控件类型）。 */
const LEGACY_FORM = [
  ['topic', 'text', '课题 *'],
  ['date', 'date', '日期'],
  ['status', 'text', '状态'],
  ['purpose', 'textarea', '目的'],
  ['reagents', 'textarea', '药品与用量'],
  ['conditions', 'textarea', '条件'],
  ['results', 'textarea', '结果'],
  ['conclusion', 'textarea', '结论'],
  ['references', 'textarea', '关联文献'],
] as const

type Field = { key: string, type: string, label: string, required: boolean, show_in_form?: boolean }
type Pack = {
  name: string
  label: string
  description?: string
  eln: { fields: Field[], form_fields?: Field[] }
  papers: { id_fields: string[] }
  source_presets: unknown[]
  tagging: { questions: unknown[] }
}

function field(key: string, type: string, label: string, show_in_form = true): Field {
  return { key, type, label, required: key === 'topic', show_in_form }
}

/** 模拟 default 包（与 domains/default/pack.yaml 一致）。 */
function defaultPack(): Pack {
  const fields = [
    field('topic', 'text', '课题 *'),
    field('date', 'date', '日期'),
    field('status', 'text', '状态'),
    field('purpose', 'textarea', '目的'),
    field('reagents', 'textarea', '药品与用量'),
    field('conditions', 'textarea', '条件'),
    field('results', 'textarea', '结果'),
    field('conclusion', 'textarea', '结论'),
    field('references', 'textarea', '关联文献'),
    field('attachments', 'list', '照片附件', false),
  ]
  return {
    name: 'default',
    label: '材料科研',
    eln: { fields, form_fields: fields.filter(f => f.show_in_form !== false) },
    papers: { id_fields: ['doi', 'arxiv_id'] },
    source_presets: [],
    tagging: { questions: [] },
  }
}

function lawPack(): Pack {
  const fields = [
    field('topic', 'text', '案件名称 *'),
    field('date', 'date', '日期'),
    field('parties', 'textarea', '当事人'),
    field('cause_of_action', 'text', '案由'),
    field('dispute_focus', 'textarea', '争议焦点'),
    field('holding', 'textarea', '裁判要旨'),
    field('legal_basis', 'list', '法条依据'),
    field('related_cases', 'list', '关联判例'),
    field('conclusion', 'textarea', '结论'),
    field('references', 'list', '参考文献'),
  ]
  return {
    name: 'law',
    label: '法学',
    eln: { fields, form_fields: fields },
    papers: { id_fields: ['flk_id', 'case_no'] },
    source_presets: [],
    tagging: { questions: [] },
  }
}

async function loadModule() {
  vi.resetModules()
  return import('@/utils/domainPacks')
}

describe('domainPacks · default 包零回归', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
  })

  it('default 包 form_fields 与改造前 ElnView 手写表单逐字段一致', async () => {
    const m = await loadModule()
    globalThis.fetch = vi.fn(async () => new Response(JSON.stringify({
      ok: true,
      default: 'default',
      domains: [defaultPack(), lawPack()],
    }), { status: 200, headers: { 'Content-Type': 'application/json' } })) as any

    await m.fetchDomainPacks()
    m.setActiveDomain('default')

    const got = m.currentElnFields.value.map(f => [f.key, f.type, f.label])
    expect(got).toEqual(LEGACY_FORM.map(([k, t, l]) => [k, t, l]))
  })

  it('attachments 不进表单（改造前表单不渲染它）', async () => {
    const m = await loadModule()
    globalThis.fetch = vi.fn(async () => new Response(JSON.stringify({
      ok: true, default: 'default', domains: [defaultPack()],
    }), { status: 200 })) as any

    await m.fetchDomainPacks()
    const formKeys = m.currentElnFields.value.map(f => f.key)
    const allKeys = m.currentAllElnFields.value.map(f => f.key)
    expect(formKeys).not.toContain('attachments')
    expect(allKeys).toContain('attachments')
  })

  it('切到 law 包后表单出现法学字段', async () => {
    const m = await loadModule()
    globalThis.fetch = vi.fn(async () => new Response(JSON.stringify({
      ok: true, default: 'default', domains: [defaultPack(), lawPack()],
    }), { status: 200 })) as any

    await m.fetchDomainPacks()
    m.setActiveDomain('law')

    const keys = m.currentElnFields.value.map(f => f.key)
    for (const k of ['parties', 'cause_of_action', 'dispute_focus', 'holding', 'legal_basis', 'related_cases'])
      expect(keys).toContain(k)
    expect(m.currentPack.value?.papers.id_fields).toEqual(['flk_id', 'case_no'])
  })

  it('后端不可用时降级为空，不抛异常', async () => {
    const m = await loadModule()
    globalThis.fetch = vi.fn(async () => { throw new Error('ECONNREFUSED') }) as any

    const packs = await m.fetchDomainPacks()
    expect(packs).toEqual([])
    expect(m.currentElnFields.value).toEqual([])
    expect(m.domainsError.value).toContain('ECONNREFUSED')
  })

  it('未声明 form_fields 时按 show_in_form 本地过滤', async () => {
    const m = await loadModule()
    const p = defaultPack()
    delete p.eln.form_fields
    globalThis.fetch = vi.fn(async () => new Response(JSON.stringify({
      ok: true, default: 'default', domains: [p],
    }), { status: 200 })) as any

    await m.fetchDomainPacks()
    m.setActiveDomain('default')
    expect(m.currentElnFields.value.map(f => f.key)).not.toContain('attachments')
    expect(m.currentElnFields.value.length).toBe(LEGACY_FORM.length)
  })

  it('切换到的未知包名被拒绝并保持原值', async () => {
    const m = await loadModule()
    globalThis.fetch = vi.fn(async () => new Response(JSON.stringify({
      ok: true, default: 'default', domains: [defaultPack()],
    }), { status: 200 })) as any

    await m.fetchDomainPacks()
    m.setActiveDomain('nope')
    expect(m.activeDomain.value).toBe('default')
  })
})

describe('domainPacks · 路由动态注册', () => {
  it('default 包不注册额外路由，law 包注册（视图存在时）', async () => {
    const m = await loadModule()
    globalThis.fetch = vi.fn(async () => new Response(JSON.stringify({
      ok: true, default: 'default', domains: [defaultPack(), lawPack()],
    }), { status: 200 })) as any

    const added: any[] = []
    const router = {
      hasRoute: () => false,
      addRoute: (r: any) => added.push(r),
    } as any

    await m.registerDomainRoutes(router)
    // default 跳过；law 视图存在 → 注册一条 /law
    const paths = added.map(r => r.path)
    expect(paths).not.toContain('/default')
    expect(paths).toContain('/law')
  })
})
