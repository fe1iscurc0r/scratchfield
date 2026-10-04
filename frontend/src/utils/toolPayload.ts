/**
 * 工具事件载荷格式化（从 MessageItem.vue 抽出，纯函数可单测）。
 */

export function formatToolPayload(value: unknown): string {
  if (value == null)
    return ''
  if (typeof value === 'string')
    return value
  try {
    return JSON.stringify(value, null, 2)
  }
  catch {
    return String(value)
  }
}

export function toolSummary(event: { name?: string, type?: string, isError?: boolean }): string {
  const name = event.name || '工具'
  if (event.type === 'tool_call') {
    return `🔧 ${name}`
  }
  return `${event.isError ? '❌' : '✅'} ${name}`
}

export function toolBody(event: { type?: string, args?: unknown, result?: unknown }): string {
  if (event.type === 'tool_call') {
    return formatToolPayload(event.args)
  }
  return formatToolPayload(event.result)
}
