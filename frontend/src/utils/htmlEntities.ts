/**
 * HTML 实体解码（从 Markdown.vue 抽出，纯函数可单测）。
 */
export function decodeHtmlEntities(s: string): string {
  return s.replace(/&amp;/g, '&').replace(/&lt;/g, '<').replace(/&gt;/g, '>').replace(/&quot;/g, '"')
}
