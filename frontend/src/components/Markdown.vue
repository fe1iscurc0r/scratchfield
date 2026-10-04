<script  lang="ts">
import DOMPurify from 'dompurify'
import MarkdownIt from 'markdown-it'
import { decodeHtmlEntities } from '@/utils/htmlEntities'
</script>

<script setup lang="ts">
import { computed, onUnmounted, ref, watch } from 'vue'

const props = defineProps<{ source: string }>()

const md = new MarkdownIt({ html: true })

const ALLOWED_TAGS = [
  'h1',
  'h2',
  'h3',
  'h4',
  'h5',
  'h6',
  'p',
  'br',
  'hr',
  'div',
  'span',
  'strong',
  'em',
  'b',
  'i',
  'u',
  's',
  'del',
  'ins',
  'sub',
  'sup',
  'ul',
  'ol',
  'li',
  'dl',
  'dt',
  'dd',
  'blockquote',
  'pre',
  'code',
  'a',
  'img',
  'table',
  'thead',
  'tbody',
  'tr',
  'th',
  'td',
  'details',
  'summary',
  'kbd',
  'mark',
  'abbr',
  'small',
  'big',
]

const ALLOWED_ATTR = [
  'href',
  'src',
  'alt',
  'title',
  'class',
  'id',
  'style',
  'target',
  'rel',
  'width',
  'height',
  'colspan',
  'rowspan',
  'role',
]

function render(content: string) {
  let html = md.render(preprocessPlanBlocks(content))
  html = html.replace(
    /<pre><code class="language-tool-result">([\s\S]*?)<\/code><\/pre>/g,
    (_, raw) => {
      const decoded = decodeHtmlEntities(raw).trim()
      const lines = decoded.split('\n')
      const summary = lines[0] || '工具结果'
      const body = lines.slice(1).join('\n').trim()
      if (!body) {
        return `<div class="tool-result-line">${summary}</div>`
      }
      return `<details class="tool-result"><summary>${summary}</summary><pre class="tool-result-body">${body}</pre></details>`
    },
  )
  // W121-03：执行计划卡片（[PLAN]…[/PLAN] → ```plan），等宽列出待执行的写操作步骤
  html = html.replace(
    /<pre><code class="language-plan">([\s\S]*?)<\/code><\/pre>/g,
    (_, raw) => {
      const decoded = decodeHtmlEntities(raw).trim()
      const items = decoded
        .split('\n')
        .map(line => line.trim())
        .filter(Boolean)
      if (!items.length) {
        return ''
      }
      const rows = items.map(line => `<div class="plan-row">${line}</div>`).join('')
      return `<details class="plan-card" open><summary>📋 执行计划（写操作待确认）</summary><div class="plan-body">${rows}</div></details>`
    },
  )
  html = DOMPurify.sanitize(html, {
    ALLOWED_TAGS,
    ALLOWED_ATTR,
    FORBID_TAGS: ['script', 'style', 'iframe', 'object', 'embed', 'form', 'input', 'button', 'textarea', 'select', 'video', 'audio'],
    FORBID_ATTR: ['onclick', 'onmouseover', 'onerror', 'onload', 'onfocus', 'onblur', 'onsubmit', 'onchange'],
    ALLOW_DATA_ATTR: false,
    WHOLE_DOCUMENT: false,
    SANITIZE_DOM: true,
  })
  return html
}

/**
 * W121-03：把 `[PLAN]…[/PLAN]` 段转成 ```plan 围栏，复用上面既有的 code-block 卡片通道。
 * 未闭合（流式输出中途）也照常转换，从 `[PLAN]` 到文本末尾都当计划内容。
 */
function preprocessPlanBlocks(content: string): string {
  if (!content || !content.includes('[PLAN]')) {
    return content
  }
  return content.replace(/\[PLAN\]([\s\S]*?)(?:\[\/PLAN\]|$)/g, (_, body: string) => {
    const safe = String(body).replace(/```/g, '\'\'\'').trim()
    return `\n\`\`\`plan\n${safe}\n\`\`\`\n`
  })
}

// 流式输出时 source 每个 token 增长一次，每个 chunk 全量 re-parse 是 O(n²)。
// 这里做两层缓解：displaySource 消抖合并突发；computed 记忆化避免
// 父组件与 source 无关的重渲染触发解析。
const displaySource = ref(props.source)
let debounceTimer: ReturnType<typeof setTimeout> | undefined

watch(() => props.source, (source) => {
  if (debounceTimer)
    clearTimeout(debounceTimer)
  debounceTimer = setTimeout(() => {
    displaySource.value = source
  }, 100)
})

onUnmounted(() => {
  if (debounceTimer)
    clearTimeout(debounceTimer)
})

const html = computed(() => render(displaySource.value))
</script>

<template>
  <div v-html="html" />
</template>
