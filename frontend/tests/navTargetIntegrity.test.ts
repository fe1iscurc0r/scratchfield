/**
 * 导航目标完整性单测（node:test 风格，零外部依赖）。
 *
 * 背景（一次真实事故的复盘）：
 * `/forum` 子树已下线 —— `main.ts` 里原来 7 条子路由（/forum、my-posts、my-replies、
 * messages、friends、quota、:id）被整块换成 `redirect: '/'`。但 `src` 里仍留有对
 * `/forum` 的引用，其中一处是**导航目标**：
 *
 *   components/AgentContacts.vue:「探索中」标签 → `router.push('/forum/quota')`
 *
 * 而 `docs/travel-exploration-system.md` §2 把「干员通讯录里的『探索中』标签可点击 →
 * 跳转到该干员当前探索上下文」写成产品承诺 ⇒ 点击后**静默跳回首页**，用户零反馈。
 * 这是「下线时漏掉的收尾」：不是死代码，是活代码里的真 bug。
 *
 * 本测试把这类事故钉死成一条不变量：
 *   **只要 `/forum` 在 `main.ts` 里仍是 redirect，`src` 中就不允许出现指向 `/forum` 的导航目标。**
 *
 * 不在扫描范围（故意的，避免把无关的账混进来）：
 * - `src/forum/**` —— 该子树被主动冻结（待复活存档，见 `main.ts` 注释），不参与扫描；
 * - `main.ts` —— 它持有路由表，`path: '/forum'` + `redirect` 是**合法**且必需的（兜住旧深链）；
 * - `/forum` 的**非导航类**用法（如恒假的路由前缀守卫）—— 它们不是导航目标，本文件末条
 *   测试改为断言其**前提**（不存在活的 `/forum*` 路由），而不是逐个点名消费方。
 *
 * **门控与自调整**：大部分断言以 `forumIsOffline` 为门控（下线态才检查），
 * 但本文件末条「下线态契约」是**无条件**的 —— 任何活的 `/forum*` 路由都会让它失败，
 * 从而把「复活论坛」逼成一次显式动作（必须同步处理被删掉的守卫/分支/管道），
 * **不会**因为门控为假而让整套断言静默空跑。
 *
 * 静态扫描的边界（诚实声明）：只能覆盖**字面量**目标。`router.push(someVar)` 形式的
 * 动态目标检测不到。
 */
import assert from 'node:assert/strict'
import { existsSync, readdirSync, readFileSync } from 'node:fs'
import path from 'node:path'
import test from 'node:test'

const SRC = path.resolve(import.meta.dirname, '../src')
const MAIN_TS = path.join(SRC, 'main.ts')

/** 递归收集 src 下的 .ts / .tsx / .vue 源文件（排除 src/forum/ 子树）。 */
function collectSources(dir: string): string[] {
  const out: string[] = []
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name)
    if (entry.isDirectory()) {
      if (entry.name === 'forum')
        continue
      out.push(...collectSources(full))
      continue
    }
    if (/\.(?:ts|tsx|vue)$/.test(entry.name))
      out.push(full)
  }
  return out
}

/** 导航目标的字面量写法：调用式 push/replace/navClick，对象式 to:，模板属性式 to="..."。 */
const NAV_TARGET_PATTERNS: RegExp[] = [
  /\.(?:push|replace)\s*\(\s*[`'"]([^`'"\s]+)[`'"]/g,
  /\bnavClick\s*\(\s*[`'"]([^`'"\s]+)[`'"]/g,
  /\bto:\s*[`'"]([^`'"\s]+)[`'"]/g,
  /\bto\s*=\s*"([^"]+)"/g,
]

/** 返回 [{ file, line, target }]，仅保留以 `/` 开头的站内目标。 */
function findNavTargets(files: string[]): Array<{ file: string, line: number, target: string }> {
  const hits: Array<{ file: string, line: number, target: string }> = []
  for (const file of files) {
    const text = readFileSync(file, 'utf8')
    for (const pattern of NAV_TARGET_PATTERNS) {
      pattern.lastIndex = 0
      for (;;) {
        const m = pattern.exec(text)
        if (m === null)
          break
        const target = m[1]
        if (!target.startsWith('/'))
          continue
        hits.push({ file: path.relative(SRC, file), line: text.slice(0, m.index).split('\n').length, target })
      }
    }
  }
  return hits
}

const mainSource = readFileSync(MAIN_TS, 'utf8')
const navTargets = findNavTargets(collectSources(SRC))

/**
 * main.ts 里所有 `/forum*` 路由声明（原始片段 + 捕获到的路径）。
 * 这些声明都是单行对象字面量，`[^}]*` 不会跨过大括号。
 */
const forumRouteDecls = [...mainSource.matchAll(/\{\s*path:\s*['"](\/forum[^'"]*)['"][^}]*\}/g)]

/** 其中**不是** redirect 的那些 —— 它们会真的渲染页面，即 `/forum` 已复活。 */
const liveForumRoutes = forumRouteDecls.filter(d => !/redirect:/.test(d[0])).map(d => d[1])

/** `/forum` 是否处于「完全下线」：至少声明了 1 条 `/forum*` 路由，且全部是 redirect。 */
const forumIsOffline = forumRouteDecls.length > 0 && liveForumRoutes.length === 0

/*
 * 下线态的设计（避免「静默放宽」这个坑）：
 * - 末条测试是**无条件**的「下线态契约」—— 任何 `/forum*` 活路由都会让它**失败**，
 *   而不是让整套断言悄悄变成空跑。这样「复活论坛」必然是一次显式动作：
 *   必须先决定是否恢复 App.vue 的路由守卫、api 层的错误抑制分支、后端的论坛管道，
 *   并同步更新本文件。
 * - 其余断言仍以 `forumIsOffline` 为门控，这样在复活后不会产生一堆**误导性的**红灯
 *   （那时「不得指向 /forum」本身就不再成立）。
 */

test('src 中不存在指向已下线 /forum 子树的导航目标', () => {
  if (!forumIsOffline)
    return
  const offenders = navTargets.filter(t => t.target === '/forum' || t.target.startsWith('/forum/'))
  const detail = offenders.map(t => `${t.file}:${t.line} -> ${t.target}`).join('; ')
  assert.deepEqual(
    offenders,
    [],
    `发现指向已下线 /forum 的导航目标（点击后会静默跳回首页）：${detail}\n`
    + '修法：改指到该功能的活入口（探索页活入口是 /model 的 TravelView），'
    + '或先恢复 main.ts 里的 /forum 路由再改回。',
  )
})

test('下线状态的兜底：/forum 与 /forum/:pathMatch(.*)* 都必须保留 redirect', () => {
  if (!forumIsOffline)
    return
  assert.match(
    mainSource,
    /path:\s*['"]\/forum['"]\s*,\s*redirect:\s*['"]\/['"]/,
    '缺少 /forum -> / 的 redirect：旧深链会落到空白页',
  )
  assert.match(
    mainSource,
    /path:\s*['"]\/forum\/:pathMatch\(\.\*\)\*['"]\s*,\s*redirect:\s*['"]\/['"]/,
    '缺少 /forum/:pathMatch(.*)* -> / 的 redirect：/forum/<任意子路径> 旧深链会落到空白页',
  )
})

test('src/forum/ 子树保持冻结：main.ts 不注册它的任何组件', () => {
  const registrations = [...mainSource.matchAll(/import\(\s*['"]([^'"]*forum\/[^'"]+)['"]\s*\)/g)]
    .map(m => m[1])
  assert.deepEqual(
    registrations,
    [],
    `main.ts 里又出现了 /forum 子树的动态导入：${registrations.join(', ')}\n`
    + '若这是有意复活论坛，请同时更新本测试与 docs/travel-exploration-system.md §2。',
  )
})

test('导航目标扫描器本身可用（自检：样本必须命中且排除注释/前缀判断）', () => {
  const sample = [
    'router.push(\'/forum/quota\')',
    'navClick(`/model`)',
    '{ to: \'/eln\', label: \'ELN\' }',
    '<RouterLink to="/papers" />',
  ].join('\n')
  for (const pattern of NAV_TARGET_PATTERNS) {
    pattern.lastIndex = 0
    assert.ok(pattern.test(sample), `扫描器未命中样本: ${pattern}`)
  }
  // 前缀判断与注释不得被当成导航目标
  assert.equal(
    navTargets.some(t => t.target.includes('/forum/api')),
    false,
    '`/forum/api/` 是错误分类用的前缀判断，不应被当作导航目标',
  )
})

test('下线态契约：/forum* 路由必须存在且全部是 redirect（无条件）', () => {
  // 这条**故意不设门控**：它同时兜住两个方向的偏离 ——
  //   ① 把 /forum* 路由删掉（旧深链会落到空白页）；
  //   ② 把某条 /forum* 路由改成会渲染页面（= 论坛复活）。
  // 两者都必须被显式处理，而不是让上面的断言悄悄空跑。
  assert.ok(
    forumRouteDecls.length >= 2,
    `main.ts 里 /forum* 路由声明只剩 ${forumRouteDecls.length} 条，预期至少 2 条`
    + '（/forum 与 /forum/:pathMatch(.*)*）。删掉它们会让旧深链落到空白页；'
    + '若确为有意改动，请同步更新本文件全部 /forum 下线态断言与 docs/travel-exploration-system.md。',
  )
  assert.deepEqual(
    liveForumRoutes,
    [],
    `检测到活的 /forum* 路由：${liveForumRoutes.join(', ')}\n`
    + '这不是 bug —— 但本文件中「/forum 已下线」的全部断言，以及 App.vue 里被删掉的'
    + '/forum 路由守卫、api/index.ts 的错误抑制分支、后端 post_to_forum / forum_post_* 管道，'
    + '都建立在「/forum* 全是 redirect」之上。若这是有意复活论坛，'
    + '请一并恢复上述代码并更新本文件。',
  )

  // 领域路由不得变出 /forum：registerDomainRoutes() 固定注册 `/<pack.name>`，
  // 但要求视图 `src/views/domains/<name>/IndexView.vue` 存在（见 utils/domainPacks.ts）。
  // 只要该文件不存在，就不可能出现活的 /forum 领域路由。
  assert.equal(
    existsSync(path.join(SRC, 'views/domains/forum/IndexView.vue')),
    false,
    '出现了 src/views/domains/forum/IndexView.vue ⇒ 领域路由可能注入出活的 /forum 路径，'
    + 'App.vue 里那条被删掉的 /forum 路由守卫需要一并恢复。',
  )
})
