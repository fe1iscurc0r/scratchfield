/**
 * 卷150 导航基建单测（node:test 风格，零外部依赖）。
 *
 * 覆盖：
 * - navigation.ts：分组完整性、路由与 main.ts 对齐、图标非空、Ctrl+n 分组序号
 * - commandScore.ts：前缀>词首>子串、拼音/关键词、"eln" 两键直达验收
 * - feedback.ts：shouldToast / toastSeverity 语义
 */
import assert from 'node:assert/strict'
import test from 'node:test'

import {
  allNavItems,
  commandCandidates,
  findNavByPath,
  groupIndexMap,
  NAV_ACTIONS,
  NAV_GROUPS,
} from '../src/utils/navigation.ts'
import { fuzzyMatch, isConfidentTopHit } from '../src/utils/commandScore.ts'
import { shouldToast, toastSeverity } from '../src/utils/feedback.ts'

// ─── navigation.ts ─────────────────────────────────────────

test('导航分组覆盖工单约定的 5 组', () => {
  assert.deepEqual(NAV_GROUPS.map(g => g.key), ['chat', 'research', 'knowledge', 'radio', 'system'])
  assert.deepEqual(NAV_GROUPS.map(g => g.label), ['对话', '科研四件套', '知识', '射频', '系统'])
})

test('全部路由项与 main.ts 已注册路由一一对应', () => {
  // main.ts 中注册的业务路由（排除 / 重定向、/forum 下线重定向、/float 悬浮球入口）
  const registered = [
    '/chat', '/model', '/memory', '/knowledge', '/papers', '/mind',
    '/skill', '/eln', '/data', '/config', '/market', '/radio', '/voice-eln',
  ]
  const navPaths = allNavItems().map(i => i.to)
  for (const p of registered) {
    assert.ok(navPaths.includes(p), `导航缺少 main.ts 已注册路由: ${p}`)
  }
  // 导航不收录 /forum（已下线）与 /float（悬浮球模式由主进程控制，非导航项）
  assert.ok(!navPaths.includes('/forum'))
  assert.ok(!navPaths.includes('/float'))
})

test('每个导航项都有 label、keywords、非空 icon', () => {
  for (const item of allNavItems()) {
    assert.ok(item.label.length > 0, `label 空: ${item.to}`)
    assert.ok(item.keywords.length > 0, `keywords 空: ${item.to}`)
    assert.ok(item.icon.includes('<svg'), `icon 非 SVG: ${item.to}`)
    assert.ok(item.icon.length > 40, `icon 过短(可疑): ${item.to}`)
  }
})

test('路由无重复、label 无重复', () => {
  const paths = allNavItems().map(i => i.to)
  assert.equal(new Set(paths).size, paths.length)
  const labels = allNavItems().map(i => i.label)
  assert.equal(new Set(labels).size, labels.length)
})

test('findNavByPath 精确命中', () => {
  assert.equal(findNavByPath('/eln')?.label, 'ELN')
  assert.equal(findNavByPath('/papers')?.label, '文献')
  assert.equal(findNavByPath('/nonexistent'), undefined)
})

test('Ctrl+<n> 分组序号：1=对话 2=科研 3=知识 4=射频 5=系统', () => {
  const m = groupIndexMap()
  assert.deepEqual(m, { chat: 1, research: 2, knowledge: 3, radio: 4, system: 5 })
})

test('命令候选 = 视图全集 + 动作集', () => {
  const cand = commandCandidates()
  assert.equal(cand.length, allNavItems().length + NAV_ACTIONS.length)
  // 动作条目都有 action 标记
  for (const a of NAV_ACTIONS) {
    assert.ok(a.action)
    assert.ok(a.to.startsWith('action:'))
  }
})

test('术语表遵守：文献(不是论文)、记忆(五元组全量)、思维(图谱)', () => {
  // 卷150 任务F 术语锚点：导航标签用词必须与术语表一致
  assert.equal(findNavByPath('/papers')?.label, '文献')
  assert.equal(findNavByPath('/memory')?.label, '记忆')
  assert.equal(findNavByPath('/mind')?.label, '思维')
})

// ─── commandScore.ts ───────────────────────────────────────

test('★ 验收项：输入 "eln" 两个键直达 ELN 视图', () => {
  const cand = commandCandidates()
  const r = fuzzyMatch('eln', cand)
  assert.ok(r.length > 0)
  assert.equal(r[0].item.label, 'ELN', `第一名应是 ELN，实得 ${r[0].item.label}`)
  assert.ok(isConfidentTopHit(r), '应为高置信命中（可直接回车）')
})

test('前缀命中 > 词首命中 > 普通子串', () => {
  const cand = [
    { label: 'eln', keywords: [] },
    { label: 'ELN 记录本', keywords: [] },
    { label: '个人实验记录（ELN 归档）', keywords: [] },
    { label: '记录本', keywords: [] },
  ]
  const r = fuzzyMatch('eln', cand)
  assert.equal(r[0].item.label, 'eln')
  assert.equal(r[1].item.label, 'ELN 记录本')
  // 「记录本」不含 e/l/n 序列，不出现
  assert.ok(!r.some(x => x.item.label === '记录本'))
})

test('拼音/关键词命中：wenxian → 文献', () => {
  const cand = commandCandidates()
  const r = fuzzyMatch('wenxian', cand)
  assert.equal(r[0].item.label, '文献')
})

test('中文查询命中：记忆 → 记忆视图', () => {
  const cand = commandCandidates()
  const r = fuzzyMatch('记忆', cand)
  assert.equal(r[0].item.label, '记忆')
})

test('空查询返回全部（原序，score=1）', () => {
  const cand = [{ label: 'A', keywords: [] }, { label: 'B', keywords: [] }]
  const r = fuzzyMatch('', cand)
  assert.equal(r.length, 2)
  assert.equal(r[0].score, 1)
})

test('无命中返回空数组', () => {
  const r = fuzzyMatch('zzzzqqqq', commandCandidates())
  assert.equal(r.length, 0)
  assert.equal(isConfidentTopHit(r), false)
})

test('isConfidentTopHit：同分双命中不算高置信', () => {
  const cand = [
    { label: 'data', keywords: [] },
    { label: 'data', keywords: ['x'] },
  ]
  const r = fuzzyMatch('data', cand)
  // 两个同分候选 → 不 confidently 直达（用户需要选择）
  assert.equal(isConfidentTopHit(r), false)
})

// ─── feedback.ts（纯逻辑部分）──────────────────────────────

test('feedback 语义：success 不弹 toast，warn/error 弹', () => {
  assert.equal(shouldToast('success'), false)
  assert.equal(shouldToast('warn'), true)
  assert.equal(shouldToast('error'), true)
})

test('toast severity 映射：warn→warn，error→error', () => {
  assert.equal(toastSeverity('warn'), 'warn')
  assert.equal(toastSeverity('error'), 'error')
})
