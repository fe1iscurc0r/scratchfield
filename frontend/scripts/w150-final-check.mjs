/**
 * 卷150 UI 全量检查（最终验收自检）
 *
 * 检查项（对接《卷150 UI 接入指南》§8/§9）：
 *  1. 15 视图 <script> 语法检查（@vue/compiler-sfc 解析 + compileScript）
 *  2. 视图层 toast.add / useToast 清零（全部经 feedback 三级反馈）
 *  3. 逐视图组件接入统计：EmptyState / SkeletonCard / feedback / ConfirmDialog / quick-action
 *  4. 删除类操作必须走 ConfirmDialog（grep 自检，指南 §8 第二条）
 *  5. 基础设施文件存在性
 *
 * 用法：node scripts/w150-final-check.mjs [--log <输出路径>]
 * 退出码：全部通过 0；任一 FAIL 1。
 */
import { readFileSync, readdirSync, writeFileSync, existsSync } from 'node:fs'
import { resolve, dirname } from 'node:path'
import { fileURLToPath } from 'node:url'
import { parse, compileScript } from '@vue/compiler-sfc'

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const viewsDir = resolve(root, 'src/views')
const lines = []
let failCount = 0

function out(text = '') {
  lines.push(text)
  console.log(text)
}
function pass(item) { out(`  PASS  ${item}`) }
function fail(item) { failCount++; out(`  FAIL  ${item}`) }

// ── 1. 视图脚本语法检查 ──
out('== 1. 视图脚本语法检查（@vue/compiler-sfc） ==')
const viewFiles = readdirSync(viewsDir).filter(f => f.endsWith('.vue')).sort()
for (const file of viewFiles) {
  const source = readFileSync(resolve(viewsDir, file), 'utf-8')
  try {
    const { descriptor, errors } = parse(source, { filename: file })
    if (errors.length > 0)
      throw new Error(errors.map(e => e.message).join('; '))
    if (descriptor.scriptSetup || descriptor.script) {
      compileScript(descriptor, { id: `w150-${file}` })
    }
    pass(`${file} 语法 OK`)
  }
  catch (e) {
    fail(`${file} 语法错误：${e.message}`)
  }
}

// ── 2. 视图层 toast 清零 ──
out('')
out('== 2. 视图层 toast.add / useToast 清零（统一走 feedback） ==')
let toastClean = true
for (const file of viewFiles) {
  const source = readFileSync(resolve(viewsDir, file), 'utf-8')
  const addCount = (source.match(/toast\.add/g) || []).length
  const useCount = (source.match(/useToast/g) || []).length
  if (addCount > 0 || useCount > 0) {
    toastClean = false
    fail(`${file} 残留 toast.add=${addCount} useToast=${useCount}`)
  }
}
if (toastClean)
  pass('15 视图 toast.add / useToast 全部清零')

// ── 3. 逐视图组件接入统计 ──
out('')
out('== 3. 逐视图组件接入统计 ==')
out('  视图            EmptyState  SkeletonCard  feedback  ConfirmDialog  quickAction')
const stats = {}
for (const file of viewFiles) {
  const source = readFileSync(resolve(viewsDir, file), 'utf-8')
  const count = (re) => (source.match(re) || []).length
  const s = {
    empty: count(/EmptyState/g),
    skeleton: count(/SkeletonCard/g),
    feedback: count(/feedback\./g),
    confirm: count(/ConfirmDialog/g),
    quick: count(/lumo:quick-action|quick-action|quickAction/g),
  }
  stats[file] = s
  out(`  ${file.padEnd(16)}${String(s.empty).padStart(6)}${String(s.skeleton).padStart(13)}${String(s.feedback).padStart(10)}${String(s.confirm).padStart(14)}${String(s.quick).padStart(12)}`)
}

// 接入硬指标（指南验收 🔲 项 → 应达成）
const hard = [
  ['PapersView.vue', 'confirm', 1, '删除文献确认弹窗（任务D.1）'],
  ['PapersView.vue', 'skeleton', 1, '文献列表加载骨架'],
  ['PapersView.vue', 'empty', 1, '文献空态/错误态'],
  ['PapersView.vue', 'quick', 1, 'DOI 导入 quick-action'],
  ['DataView.vue', 'skeleton', 1, '数据解析骨架（消白屏冻结）'],
  ['RadioView.vue', 'skeleton', 1, '电台连接中骨架'],
  ['RadioView.vue', 'empty', 1, '电台离线空态'],
  ['MemoryView.vue', 'skeleton', 1, '记忆分页骨架'],
  ['MemoryView.vue', 'empty', 1, '记忆错误/空数据空态'],
  ['ElnView.vue', 'quick', 1, '新建 ELN quick-action（Ctrl+N）'],
  ['ElnView.vue', 'skeleton', 1, 'ELN 加载骨架'],
  ['MessageView.vue', 'quick', 1, '新会话 quick-action（Ctrl+N）'],
  ['SkillView.vue', 'empty', 1, '技能/MCP 空态'],
  ['ConfigView.vue', 'feedback', 1, '配置反馈行内化'],
  ['MarketView.vue', 'feedback', 1, '安装反馈行内化'],
  ['KnowledgeView.vue', 'skeleton', 1, '知识库加载骨架'],
]
for (const [file, key, min, label] of hard) {
  if ((stats[file]?.[key] ?? 0) >= min)
    pass(`${label}（${file} ${key}=${stats[file][key]}）`)
  else
    fail(`${label}未达成（${file} ${key}=${stats[file]?.[key] ?? 0}，要求 ≥${min}）`)
}

// ── 4. 删除类操作 ConfirmDialog 自检（指南 §8） ──
out('')
out('== 4. 删除类操作 ConfirmDialog 覆盖检查 ==')
for (const file of viewFiles) {
  const source = readFileSync(resolve(viewsDir, file), 'utf-8')
  // 含「删除」按钮/动作但不引用 ConfirmDialog、也不走二次确认函数的视图列出
  const hasDeleteUi = /severity="danger"|删除<\/(?:button|Button)|askDelete|askRemove|doRemove|doDelete/.test(source)
  const hasConfirm = /ConfirmDialog|askDelete|askRemove|confirmDelete/.test(source)
  if (hasDeleteUi && !hasConfirm)
    fail(`${file} 存在删除类 UI 但未接 ConfirmDialog/确认函数`)
  else if (hasDeleteUi)
    pass(`${file} 删除操作已接确认`)
}

// ── 5. 基础设施存在性 ──
out('')
out('== 5. 基础设施文件 ==')
const infra = [
  'src/utils/navigation.ts',
  'src/utils/commandScore.ts',
  'src/utils/feedback.ts',
  'src/composables/useGlobalHotkeys.ts',
  'src/components/AppSidebar.vue',
  'src/components/CommandPalette.vue',
  'src/components/EmptyState.vue',
  'src/components/SkeletonCard.vue',
  'tests/w150Navigation.test.ts',
  'docs/ui-terms.md',
]
for (const rel of infra) {
  if (existsSync(resolve(root, rel)))
    pass(rel)
  else
    fail(`${rel} 缺失`)
}

// ── 汇总 ──
out('')
out(failCount === 0 ? 'ALL PASS ✓' : `FAILED: ${failCount} 项未通过`)

// ── 写日志 ──
const logIdx = process.argv.indexOf('--log')
if (logIdx > 0 && process.argv[logIdx + 1]) {
  const header = `# w150_final_check.log\n# 生成：${new Date().toISOString()}\n# 命令：node scripts/w150-final-check.mjs --log ${process.argv[logIdx + 1]}\n\n`
  writeFileSync(resolve(process.argv[logIdx + 1]), header + lines.join('\n') + '\n', 'utf-8')
  console.log(`\n日志已写入 ${process.argv[logIdx + 1]}`)
}
process.exit(failCount === 0 ? 0 : 1)
