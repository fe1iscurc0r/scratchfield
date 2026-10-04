/**
 * inspect_ts_class.cjs — 用 TypeScript 编译器 API 列出某个类的全部成员（方法/属性）。
 *
 * 用法: node tools/inspect_ts_class.cjs src/api/core.ts CoreApiClient
 *
 * 输出: 每行 —— 类型 + 名称 + 起止行号 + 代码行数。
 * 用完即删，不入库。
 */
const fs = require('node:fs')
const ts = require('typescript')

const file = process.argv[2]
const className = process.argv[3]
if (!file || !className) {
  console.error('usage: node inspect_ts_class.cjs <file.ts> <ClassName>')
  process.exit(1)
}

const src = fs.readFileSync(file, 'utf8')
const sf = ts.createSourceFile(file, src, ts.ScriptTarget.Latest, true)

function loc(node) {
  const s = sf.getLineAndCharacterOfPosition(node.getStart(sf)).line + 1
  const e = sf.getLineAndCharacterOfPosition(node.getEnd()).line + 1
  return [s, e]
}

let found = false
for (const st of sf.statements) {
  if (!ts.isClassDeclaration(st) || !st.name || st.name.text !== className)
    continue
  found = true
  const rows = []
  for (const m of st.members) {
    const [s, e] = loc(m)
    let kind = 'member'
    let name = ''
    if (ts.isMethodDeclaration(m)) {
      kind = 'method'
      name = m.name.getText(sf)
    }
    else if (ts.isGetAccessorDeclaration(m)) {
      kind = 'getter'
      name = m.name.getText(sf)
    }
    else if (ts.isPropertyDeclaration(m)) {
      kind = 'prop'
      name = m.name.getText(sf)
    }
    else {
      kind = ts.SyntaxKind[m.kind]
      name = m.name ? m.name.getText(sf) : '?'
    }
    rows.push({ kind, name, s, e, lines: e - s + 1 })
  }
  console.log(`class ${className} @ ${file}`)
  console.log(`members: ${rows.length}`)
  console.log('')
  for (const r of rows)
    console.log(`${String(r.s).padStart(5)}-${String(r.e).padStart(5)}  ${String(r.lines).padStart(4)}L  ${r.kind.padEnd(7)} ${r.name}`)
  const total = rows.reduce((a, b) => a + b.lines, 0)
  console.log('')
  console.log(`total member lines: ${total}`)
}
if (!found)
  console.error(`class ${className} not found`)
