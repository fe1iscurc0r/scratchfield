/**
 * verify_api_parity.cjs — 比对拆分前后 api 层的方法集合与签名。
 *
 * 旧: 用 TS API 解析 core.ts.bak 的 CoreApiClient 成员
 * 新: 用 TS API 解析 domains/*.ts 各导出对象的成员
 *
 * 输出：差集（旧有新无 / 新有旧无），以及每个方法的参数个数对比。
 * 用完即删。
 */
const fs = require('node:fs')
const path = require('node:path')
const ts = require('typescript')

const ROOT = path.resolve(__dirname, '..')
const OLD = process.argv[2]
const DOMAINS_DIR = path.join(ROOT, 'src/api/domains')

function parse(file) {
  const src = fs.readFileSync(file, 'utf8')
  return ts.createSourceFile(file, src, ts.ScriptTarget.Latest, true)
}

function methodInfo(node, sf) {
  const name = node.name.getText(sf)
  const params = node.parameters.length
  const isAsync = !!(ts.getCombinedModifierFlags(node) & ts.ModifierFlags.Async)
  const isGen = !!node.asteriskToken
  const ret = node.type ? node.type.getText(sf) : ''
  return { name, params, isAsync, isGen, ret }
}

// 旧：CoreApiClient 类成员
const oldSf = parse(OLD)
const oldMethods = new Map()
for (const st of oldSf.statements) {
  if (ts.isClassDeclaration(st) && st.name && st.name.text === 'CoreApiClient') {
    for (const m of st.members) {
      if (ts.isMethodDeclaration(m))
        oldMethods.set(m.name.getText(oldSf), methodInfo(m, oldSf))
    }
  }
}

// 新：各域导出对象的成员
const newMethods = new Map()
for (const f of fs.readdirSync(DOMAINS_DIR)) {
  if (!f.endsWith('.ts') || f.startsWith('_'))
    continue
  const sf = parse(path.join(DOMAINS_DIR, f))
  for (const st of sf.statements) {
    if (!ts.isVariableStatement(st))
      continue
    const mods = ts.getModifiers(st)
    if (!mods || !mods.some(m => m.kind === ts.SyntaxKind.ExportKeyword))
      continue
    for (const d of st.declarationList.declarations) {
      const init = d.initializer
      if (!init)
        continue
      let obj = init
      // 处理 satisfies 表达式
      if (ts.isSatisfiesExpression(init))
        obj = init.expression
      if (!ts.isObjectLiteralExpression(obj))
        continue
      for (const p of obj.properties) {
        if (ts.isMethodDeclaration(p))
          newMethods.set(p.name.getText(sf), { ...methodInfo(p, sf), file: f })
      }
    }
  }
}

console.log(`旧方法: ${oldMethods.size}`)
console.log(`新方法: ${newMethods.size}`)
const onlyOld = [...oldMethods.keys()].filter(k => !newMethods.has(k))
const onlyNew = [...newMethods.keys()].filter(k => !oldMethods.has(k))
console.log('')
console.log(`旧有新无 (${onlyOld.length}): ${onlyOld.join(', ') || '-'}`)
console.log(`新有旧无 (${onlyNew.length}): ${onlyNew.join(', ') || '-'}`)

// 参数个数 / async / gen 差异
console.log('')
let diffs = 0
for (const [name, o] of oldMethods) {
  const n = newMethods.get(name)
  if (!n)
    continue
  const issues = []
  if (o.params !== n.params)
    issues.push(`参数 ${o.params}→${n.params}`)
  if (o.isAsync !== n.isAsync)
    issues.push(`async ${o.isAsync}→${n.isAsync}`)
  if (o.isGen !== n.isGen)
    issues.push(`gen ${o.isGen}→${n.isGen}`)
  if (issues.length) {
    console.log(`  ${name}: ${issues.join(', ')}`)
    diffs++
  }
}
console.log(`签名差异: ${diffs}`)
