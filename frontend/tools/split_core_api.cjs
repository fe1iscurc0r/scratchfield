/**
 * split_core_api.cjs — 用 TypeScript 编译器 API 把 api/core.ts 按域切分。
 *
 * 产物：
 *   src/api/domains/_context.ts   域方法工厂（已存在则跳过）
 *   src/api/domains/_types.ts     全部共享类型（原 core.ts 的 interface/type）
 *   src/api/domains/<domain>.ts   各域方法（纯搬运）
 *   src/api/core.ts               薄壳：re-export + 原型注入
 *
 * 只做机械搬运：方法体一字不改。
 *
 * 用法: node tools/split_core_api.cjs [--dry-run]
 */
const fs = require('node:fs')
const path = require('node:path')
const ts = require('typescript')

const ROOT = path.resolve(__dirname, '..')
const srcArg = process.argv.slice(2).find(a => !a.startsWith('--'))
const SRC = srcArg ? path.resolve(srcArg) : path.join(ROOT, 'src/api/core.ts')
const OUT_DIR = path.join(ROOT, 'src/api/domains')
const DRY = process.argv.includes('--dry-run')
console.log(`源文件: ${SRC}`)

const DOMAIN_MAP = {
  system: [
    'getActiveCharacter', 'health', 'agentServerHealth', 'agentServerFullHealth',
    'agentServerOpenclawHealth', 'systemInfo', 'systemConfig', 'setSystemConfig',
    'openclawGatewayStatus', 'openclawGatewayStart', 'openclawGatewayStop',
    'trackTelemetry', 'flushTelemetry', 'getTelemetryStatus',
    'getSystemPrompt', 'setSystemPrompt',
    'listCharacterTemplates', 'listCustomLive2DModels',
    'uploadCustomLive2DModel', 'deleteCustomLive2DModel',
  ],
  chat: [
    'chat', 'chatStream', 'getSessions', 'getSessionDetail', 'deleteSession',
    'clearAllSessions', 'getToolStatus', 'getClawdbotReplies',
    'uploadDocument', 'parseDocument',
  ],
  memory: [
    'getMemoryStats', 'ragIngestText', 'ragList', 'ragDelete', 'ragQuery',
    'getQuintuples', 'searchQuintuples', 'getGraphSummary',
    'getContextStats', 'loadContext',
  ],
  skills: [
    'getMcpStatus', 'getMcpServices', 'getMcpAssembly', 'getToolStats',
    'getToolCircuit', 'updateMcpAssembly', 'importMcpConfig',
    'updateMcpService', 'deleteMcpService',
    'importCustomSkill', 'getSkillCatalog', 'importScopedSkill', 'cloneSkill',
    'deleteSkill', 'installHubSkill', 'installHubMcp',
    'getOpenclawTasks', 'getOpenclawTaskDetail', 'getMcpTasks',
  ],
  media: [
    'getLive2dActions', 'getMusicCommands', 'transcribeAudio',
  ],
  auth: [
    'authLogin', 'authMe', 'authLogout', 'authRegister',
    'authSendVerification', 'authSendQqVerification', 'authBindQqEmail',
    'authGetQqEmailBinding', 'testQqNotification', 'authGetCaptcha',
  ],
  travel: [
    'startTravel', 'createTravelSession', 'updateTravelSessionBrowser',
    'sendTravelInstruction', 'getTravelStatus', 'getTravelSessions',
    'getTravelSession', 'getTravelSessionReport', 'getTravelSessionHistory',
    'stopTravel', 'stopTravelSession', 'getTravelHistory',
  ],
  market: [
    'getMarketItems', 'installMarketItem',
  ],
  agents: [
    'listAgents', 'createAgent', 'deleteAgent', 'renameAgent',
    'getAgentRuntime', 'getAgentHistory', 'getAgentSettings',
    'updateAgentSettings', 'relayAgentMessage', 'streamToAgent',
    'createAgentInstance', 'destroyAgentInstance', 'listAgentInstances',
    'sendToAgentInstance', 'streamToAgentInstance', 'renameAgentInstance',
    'getAgentInstanceHistory',
  ],
  papers: [
    'listPapers', 'getPaper', 'createPaper', 'updatePaper', 'deletePaper',
    'importPapers', 'importDoi', 'linkPaperExperiments',
  ],
  law: [
    'importLawCases', 'importLawFlk', 'getLawCaseQueue', 'getVonStatus',
    'getLawTagPendingPreview', 'tagLawCases', 'tagLawPending',
    'getLawTagQueue', 'confirmLawTag',
  ],
  eln: [
    'elnList', 'elnCreate', 'elnGet', 'elnUpdate', 'elnExport',
    'elnTemplates', 'elnFromDesign', 'elnUploadAttachment',
  ],
  apps: [
    'getAppsLaunchStatus', 'launchLocalApp',
  ],
  dataTools: [
    'dataToolsSamples', 'dataToolsParse', 'dataToolsPlot',
  ],
}

/** 从 core 顶部 import 进来的**类型**符号 */
const EXTERNAL_TYPE_SYMBOLS = ['TravelSession', 'Config', 'StreamChunk']

/** 从 core 顶部 import 进来的**值**符号 */
const EXTERNAL_VALUE_SYMBOLS = [
  'decodeStreamChunk', 'readerToMessageStream', 'toCamel', 'toSnake',
  'ACCESS_TOKEN', 'aiter', 'axios',
]

/** core.ts 内部定义的模块级辅助（值） */
const LOCAL_SYMBOLS = ['agentAxios']

const GLOBAL_TYPE_SYMBOLS = [...EXTERNAL_TYPE_SYMBOLS]
const GLOBAL_VALUE_SYMBOLS = [...EXTERNAL_VALUE_SYMBOLS, ...LOCAL_SYMBOLS]

/** 某些域内部有跨方法调用，需要给 this 补上被依赖方法的类型 */
const DOMAIN_SELFREF = {
  agents: [
    'streamToAgent(id: string, message: string, timeoutSeconds?: number): AsyncGenerator<{ type: string, text: string }>',
    'getAgentHistory(id: string, limit?: number): Promise<{ messages: Array<{ role: string, content: string }> }>',
  ],
}

function main() {
  const src = fs.readFileSync(SRC, 'utf8')
  const sf = ts.createSourceFile(SRC, src, ts.ScriptTarget.Latest, true)
  const srcLines = src.split('\n')

  // 顶层语句
  const typeDecls = []   // interface / type
  const imports = []     // 顶部 import
  let cls = null

  for (const st of sf.statements) {
    if (ts.isImportDeclaration(st))
      imports.push(st.getText(sf))
    else if (ts.isInterfaceDeclaration(st) || ts.isTypeAliasDeclaration(st))
      typeDecls.push({ name: st.name.text, text: st.getText(sf) })
    else if (ts.isClassDeclaration(st) && st.name && st.name.text === 'CoreApiClient')
      cls = st
  }
  if (!cls)
    throw new Error('CoreApiClient not found')

  const members = []
  for (const m of cls.members) {
    if (!m.name)
      continue
    members.push({ name: m.name.getText(sf), text: m.getText(sf) })
  }
  const memberByName = new Map(members.map(m => [m.name, m]))

  // 校验覆盖
  const allAssigned = Object.values(DOMAIN_MAP).flat()
  const dup = allAssigned.filter((n, i) => allAssigned.indexOf(n) !== i)
  if (dup.length)
    throw new Error(`重复分配: ${dup.join(', ')}`)
  const missing = members.map(m => m.name).filter(n => !allAssigned.includes(n))
  if (missing.length)
    throw new Error(`未分配方法: ${missing.join(', ')}`)

  // 类型归属：全放 _types.ts（简单、无循环依赖）
  const typeNames = typeDecls.map(t => t.name)

  // _types.ts
  const typesOut = [
    '/* eslint-disable ts/consistent-type-definitions */',
    '/**',
    ' * api 层共享类型（卷191-A2 从 core.ts 拆出）。',
    ' * 原样搬运，字段与注释零改动。',
    ' */',
    '',
    ...typeDecls.map(t => `${t.text}\n`),
  ].join('\n')

  // 各域文件
  const usedGlobalByDomain = {}
  const files = {}
  for (const [domain, names] of Object.entries(DOMAIN_MAP)) {
    const body = names.map(n => memberByName.get(n).text).join('\n\n')
    // 该域用到的外部符号
    const usedValue = GLOBAL_VALUE_SYMBOLS.filter(s => new RegExp(`\\b${s}\\b`).test(body))
    const usedExternalType = GLOBAL_TYPE_SYMBOLS.filter(s => new RegExp(`\\b${s}\\b`).test(body))
    const usedLocalTypes = typeNames.filter(t => new RegExp(`\\b${t}\\b`).test(body))
    usedGlobalByDomain[domain] = {
      value: usedValue,
      type: [...usedExternalType, ...usedLocalTypes],
    }

    const lines = []
    lines.push('/**')
    lines.push(` * ${domain} 域 API（卷191-A2 从 core.ts 拆出）。`)
    lines.push(' *')
    lines.push(' * 方法体纯搬运，签名与返回类型零变化。')
    lines.push(' */')
    if (usedLocalTypes.length)
      lines.push(`import type { ${usedLocalTypes.join(', ')} } from './_types'`)
    if (usedValue.length)
      lines.push(`import { ${usedValue.join(', ')} } from './_internals'`)
    if (usedExternalType.length)
      lines.push(`import type { ${usedExternalType.join(', ')} } from './_internals'`)
    lines.push(`import type { DomainShape } from './_context'`)
    lines.push('')
    if (DOMAIN_SELFREF[domain]) {
      lines.push('/** 同域跨方法调用所需的自身方法签名（仅用于 this 类型） */')
      lines.push(`interface ${domain[0].toUpperCase()}${domain.slice(1)}SelfRef {`)
      for (const sig of DOMAIN_SELFREF[domain])
        lines.push(`  ${sig}`)
      lines.push('}')
      lines.push('')
      lines.push(`type ${domain[0].toUpperCase()}${domain.slice(1)}Shape =`)
      lines.push('  & Record<string, (...args: any[]) => any>')
      lines.push(`  & ThisType<import('./_context').DomainContext & ${domain[0].toUpperCase()}${domain.slice(1)}SelfRef>`)
      lines.push('')
      lines.push('export const ' + domain + 'Methods = {')
    }
    else {
      lines.push('export const ' + domain + 'Methods = {')
    }
    names.forEach((n, i) => {
      const suffix = i < names.length - 1 ? ',' : ''
      lines.push(`  ${memberByName.get(n).text}${suffix}`)
      lines.push('')
    })
    while (lines[lines.length - 1] === '')
      lines.pop()
    if (DOMAIN_SELFREF[domain]) {
      const nm = `${domain[0].toUpperCase()}${domain.slice(1)}Shape`
      lines.push(`} satisfies ${nm}`)
    }
    else {
      lines.push('} satisfies DomainShape')
    }
    lines.push('')
    files[`${domain}.ts`] = lines.join('\n')
  }

  // 打印统计
  console.log('域分布：')
  for (const [d, names] of Object.entries(DOMAIN_MAP)) {
    const u = usedGlobalByDomain[d]
    console.log(`  ${d.padEnd(11)} ${String(names.length).padStart(2)} 方法  值:[${u.value.join(',')}]  类型:[${u.type.join(',')}]`)
  }

  if (DRY)
    return

  fs.mkdirSync(OUT_DIR, { recursive: true })
  fs.writeFileSync(path.join(OUT_DIR, '_types.ts'), typesOut, 'utf8')
  for (const [name, content] of Object.entries(files))
    fs.writeFileSync(path.join(OUT_DIR, name), content, 'utf8')
  console.log(`\n写入 ${Object.keys(files).length + 1} 个域文件到 ${OUT_DIR}`)
}

main()
