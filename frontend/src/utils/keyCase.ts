/**
 * 前后端键名转换（snake_case ↔ camelCase）薄封装。
 *
 * 从 api/core.ts 抽出（原处直接调 camelcase-keys/snakecase-keys），
 * 统一 deep:true 语义，纯函数可单测。
 */
import camelcaseKeys from 'camelcase-keys'
import snakecaseKeys from 'snakecase-keys'

/** 请求体 → snake_case（deep） */
export function toSnake<T extends object>(data: T): Record<string, unknown> {
  return snakecaseKeys(data as Record<string, unknown>, { deep: true }) as Record<string, unknown>
}

/** 响应体 JSON → camelCase（deep） */
export function toCamel(data: string): Record<string, unknown> {
  return camelcaseKeys(JSON.parse(data), { deep: true }) as Record<string, unknown>
}
