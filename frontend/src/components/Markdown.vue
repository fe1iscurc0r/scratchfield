<script  lang="ts">
import MarkdownIt from 'markdown-it'
import DOMPurify from 'dompurify'

const md = new MarkdownIt({ html: true })

const ALLOWED_TAGS = [
  'h1','h2','h3','h4','h5','h6','p','br','hr','div','span',
  'strong','em','b','i','u','s','del','ins','sub','sup',
  'ul','ol','li','dl','dt','dd',
  'blockquote','pre','code','a','img','table','thead','tbody','tr','th','td',
  'details','summary','kbd','mark','abbr','small','big',
]

const ALLOWED_ATTR = [
  'href','src','alt','title','class','id','style',
  'target','rel','width','height','colspan','rowspan',
  'role',
]

function decodeHtmlEntities(s: string): string {
  return s.replace(/&amp;/g, '&').replace(/&lt;/g, '<').replace(/&gt;/g, '>').replace(/&quot;/g, '"')
}

export function render(content: string) {
  let html = md.render(content)
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
</script>

<script setup lang="ts">
defineProps<{ source: string }>()
</script>

<template>
  <div v-html="render(source)" />
</template>
