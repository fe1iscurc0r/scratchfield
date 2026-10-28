// A2+A3 解析器逻辑测试（纯 node，无依赖）
//   node tools/mcp_add_parse.test.mjs
// 验证：粘贴 {"mcpServers":{...}} 能剥壳 + 推断 transport + 就地校验
let failed = 0
function eq(actual, expected, label) {
  const ok = JSON.stringify(actual) === JSON.stringify(expected)
  if (!ok) { failed++; console.error(`✗ ${label}\n   期望 ${JSON.stringify(expected)}\n   实际 ${JSON.stringify(actual)}`) }
  else console.log(`✓ ${label}`)
}

function validateMcpConfig(data, suggestedName) {
  const errors = []
  if (!data || typeof data !== 'object' || Array.isArray(data))
    return { ok: false, errors: ['配置必须是 JSON 对象'] }
  const type = String(data.type || data.transport || '').toLowerCase()
  const hasCommand = typeof data.command === 'string' && data.command.trim().length > 0
  const hasUrl = typeof data.url === 'string' && data.url.trim().length > 0
  let transport = 'stdio'
  if (type === 'http' || type === 'streamable-http') transport = 'http'
  else if (type === 'sse') transport = 'sse'
  else if (!hasCommand && hasUrl) transport = 'http'
  if (transport === 'stdio' && !hasCommand) errors.push('stdio 类型必须提供 command')
  if (transport !== 'stdio' && !hasUrl) errors.push(`${transport} 类型必须提供 url`)
  if (transport !== 'stdio' && hasUrl && !/^https?:\/\//i.test(String(data.url))) errors.push('url 必须 http(s) 开头')
  if (Array.isArray(data.args) && data.args.some(a => typeof a !== 'string')) errors.push('args 必须是字符串数组')
  return { ok: errors.length === 0, config: errors.length ? undefined : data, name: suggestedName, transport, errors }
}

function parseMcpConfigPayload(raw) {
  const text = (raw || '').trim()
  if (!text) return { ok: false, errors: ['请输入 JSON 配置'] }
  let data
  try { data = JSON.parse(text) } catch { return { ok: false, errors: ['JSON 格式无效（检查引号/逗号）'] } }
  if (data && typeof data === 'object' && !Array.isArray(data)) {
    const servers = data.mcpServers
    if (servers && typeof servers === 'object' && !data.command && !data.url) {
      const entries = Object.entries(servers)
      if (entries.length === 0) return { ok: false, errors: ['mcpServers 为空'] }
      // A3：剥壳 + 用第一个 key 作为建议名
      return validateMcpConfig(entries[0][1], entries[0][0])
    }
  }
  return validateMcpConfig(data, undefined)
}

// 1) 裸 stdio 配置
eq(parseMcpConfigPayload('{"command":"npx","args":["-y","@mcp/server"],"type":"stdio"}'),
  { ok: true, config: { command: 'npx', args: ['-y', '@mcp/server'], type: 'stdio' }, name: undefined, transport: 'stdio', errors: [] },
  '裸 stdio 配置通过')

// 2) A3：Claude/Cursor 风格的外壳（自动剥壳 + 取名）
const wrapped = parseMcpConfigPayload(JSON.stringify({ mcpServers: { fetch: { command: 'uvx', args: ['mcp-server-fetch'] } } }))
eq({ ok: wrapped.ok, name: wrapped.name, transport: wrapped.transport, command: wrapped.config?.command },
  { ok: true, name: 'fetch', transport: 'stdio', command: 'uvx' },
  'mcpServers 外壳：剥壳 + 自动取名 fetch')

// 3) url 推断 http
const byUrl = parseMcpConfigPayload('{"url":"https://mcp.example.com/sse","type":"sse"}')
eq({ ok: byUrl.ok, transport: byUrl.transport }, { ok: true, transport: 'sse' }, 'type=sse 识别为 sse')

const inferred = parseMcpConfigPayload('{"url":"https://mcp.example.com/mcp"}')
eq({ ok: inferred.ok, transport: inferred.transport }, { ok: true, transport: 'http' }, '无 type 但有 url ⇒ 推断 http')

// 4) A2：缺必填的就地报错
eq(parseMcpConfigPayload('{"type":"stdio"}').errors, ['stdio 类型必须提供 command'], 'stdio 缺 command 报错')
eq(parseMcpConfigPayload('{"type":"http"}').errors, ['http 类型必须提供 url'], 'http 缺 url 报错')
eq(parseMcpConfigPayload('{"url":"ftp://x"}').errors, ['url 必须 http(s) 开头'], '非 http(s) url 报错')
eq(parseMcpConfigPayload('{"command":"npx","args":[1,2]}').errors, ['args 必须是字符串数组'], 'args 非字符串数组报错')

// 5) 坏 JSON / 空
eq(parseMcpConfigPayload('{').errors, ['JSON 格式无效（检查引号/逗号）'], '坏 JSON 报错')
eq(parseMcpConfigPayload('').errors, ['请输入 JSON 配置'], '空输入报错')
eq(parseMcpConfigPayload('{"mcpServers":{}}').errors, ['mcpServers 为空'], '空 mcpServers 报错')
eq(parseMcpConfigPayload('[1,2]').errors, ['配置必须是 JSON 对象'], '数组不是合法配置')

console.log(failed ? `\n❌ ${failed} 个用例失败` : '\n✅ 全部用例通过')
process.exit(failed ? 1 : 0)
