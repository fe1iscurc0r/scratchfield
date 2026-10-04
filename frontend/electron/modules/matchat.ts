/**
 * MatChat BrowserView 主进程模块
 *
 * 职责：
 *   1) 创建并管理一个常驻的 BrowserView，用于内嵌 https://ai.matchat.cn/chat
 *   2) 通过 IPC 暴露 attach/detach/setBounds/reload/clearStorage/extractLastQA 等能力给渲染层
 *   3) 在主窗口几何变化时重算 BrowserView 的 bounds
 *
 * 安全要点：
 *   - BrowserView 使用独立 partition（persist:matchat）隔离 cookie/storage，与主应用隔离
 *   - contextIsolation:true + nodeIntegration:false + sandbox:true，保证 MatChat 页面无法拿到 Node 能力
 *   - setWindowOpenHandler 拦截所有 window.open，只允许 http/https 走系统浏览器，其余协议一律拒绝
 *   - executeJavaScript 注入的提取脚本只读 DOM 文本，不执行外部代码
 */
import { BrowserView, ipcMain, session, shell } from 'electron'
import { getMainWindow } from './window'

// MatChat 首页地址（内嵌 BrowserView 的固定入口）
const MATCHAT_URL = 'https://ai.matchat.cn/chat'
// 独立会话分区：MatChat 的 cookie/localStorage 与主应用彻底隔离，互不污染
const PARTITION = 'persist:matchat'
// 伪装 UA，避免 MatChat 前端做 Electron/爬虫检测导致界面异常
const USER_AGENT
  = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36'

/** BrowserView 的矩形区域（相对主窗口 content 左上角） */
export interface Rect {
  x: number
  y: number
  width: number
  height: number
}

// 模块级单例：BrowserView 在首次 attach 时创建，detach 只摘除不销毁，便于反复 attach
let matchatView: BrowserView | null = null
// 是否已挂到主窗口上（attach=true / detach=false），用于判断是否需要重算 bounds
let attached = false
// 渲染层最近一次设置的占位区，recomputeBounds 以此为基准做边界裁剪
let placeholderRect: Rect = { x: 16, y: 80, width: 720, height: 640 }
// 定时 flush cookie 的 timer（每 30 秒落盘一次，避免强杀时 cookie 丢失）
let cookieFlushTimer: NodeJS.Timeout | null = null

/**
 * 主窗口几何变化时由 main.ts 调用，触发 BV bounds 重算。
 * 用 setImmediate 节流，避免 resize 高频回调里同步布局。
 */
export function notifyGeometryChanged(): void {
  if (!attached)
    return
  setImmediate(recomputeBounds)
}

/**
 * 懒创建 BrowserView 单例。
 * 只在第一次 attach 时执行一次创建 + 加载首屏 + 绑定事件，后续直接复用。
 */
function ensureView(): BrowserView {
  if (matchatView)
    return matchatView
  matchatView = new BrowserView({
    webPreferences: {
      partition: PARTITION, // 独立会话分区，cookie/storage 与默认 session 隔离
      contextIsolation: true, // 渲染层 JS 与 preload 隔离
      nodeIntegration: false, // 禁止 MatChat 页面使用 Node API
      sandbox: true, // 沙箱化，进一步限制渲染进程能力
      javascript: true, // MatChat 是 SPA，必须开 JS
    },
  })
  matchatView.webContents.setUserAgent(USER_AGENT)
  // 拦截页面内所有 window.open / target=_blank：
  // 【安全】只允许 http/https 协议交给系统浏览器打开，拒绝 file:/javascript:/data: 等危险协议，
  // 防止恶意页面通过 window.open('file:///...') 触发本地文件协议或执行 javascript: URL。
  matchatView.webContents.setWindowOpenHandler(({ url }) => {
    try {
      const u = new URL(url)
      if (u.protocol === 'http:' || u.protocol === 'https:') {
        // 合法网页：用系统默认浏览器打开，BrowserView 自身不新建窗口
        shell.openExternal(url)
      }
      // 其它协议（file/javascript/data/vbscript 等）一律静默丢弃
    }
    catch {
      // URL 解析失败（非法字符串），忽略，不打开任何东西
    }
    return { action: 'deny' } // 始终拒绝在 BrowserView 内部开新窗口
  })
  // 监听导航完成，把最新 URL 推给渲染层（用于顶栏显示当前地址）
  matchatView.webContents.on('did-navigate', (_e, url) => {
    const win = getMainWindow()
    win?.webContents.send('matchat:url-change', url)
  })
  // 导航完成时 flush cookie：MatChat 登录后通常会跳转，此时 cookie 刚写入，
  // 立即落盘可避免强杀进程时丢失登录态
  matchatView.webContents.on('did-finish-load', () => {
    session.fromPartition(PARTITION).cookies.flushStore().catch(() => {})
  })
  // 定时 flush cookie：lumo.ps1 退出时用 taskkill /F 强杀 Electron，
  // before-quit 钩子不执行，flushStore 不会被调用。
  // 每 30 秒自动落盘一次，确保即使强杀也能保留最近 30 秒内的登录态。
  if (cookieFlushTimer)
    clearInterval(cookieFlushTimer)
  cookieFlushTimer = setInterval(() => {
    if (!matchatView || matchatView.webContents.isDestroyed())
      return
    session.fromPartition(PARTITION).cookies.flushStore().catch(() => {})
  }, 30_000)
  // 加载首屏；失败时把错误推给渲染层 toast 提示
  matchatView.webContents.loadURL(MATCHAT_URL).catch((err) => {
    const win = getMainWindow()
    win?.webContents.send('matchat:load-error', String(err))
  })
  return matchatView
}

/**
 * 依据 placeholderRect 重算 BrowserView 实际 bounds，并做边界兜底：
 * - x/y 钳到窗口可视区内（防止异常 rect 跑到窗口外）
 * - 宽高不小于 1（防止 0 尺寸导致 BrowserView 消失），且不超出窗口右下边界
 *
 * 注意：渲染层（KnowledgeView）已经用 getBoundingClientRect() 测量了占位 div 的精确位置和尺寸，
 * 这里必须原样信任传入的 placeholderRect，不能再强制套用 300x200 之类的最小值——
 * 否则会把渲染层测出来的精确 rect（比如 360x520）强行放大到 300x200，导致 BrowserView 比
 * 占位区更大、覆盖到右侧知识库面板，表现为"适配不良"。
 *
 * 仅保留两类兜底：
 *   1) 最小值 1（防止 0 尺寸，不改变有效测量值）
 *   2) 窗口边界裁剪（窗口缩小时旧 rect 可能超出新窗口，需要裁剪到可视区内）
 */
function recomputeBounds(): void {
  const win = getMainWindow()
  if (!win || !matchatView || !attached)
    return
  const [cw, ch] = win.getContentSize()
  // 横向：x 钳到 [0, cw-1]，避免完全跑到右侧不可见区
  const x = Math.max(0, Math.min(placeholderRect.x, Math.max(0, cw - 1)))
  // 纵向：y 钳到 [0, ch-1]
  const y = Math.max(0, Math.min(placeholderRect.y, Math.max(0, ch - 1)))
  // 宽度：信任渲染层测量值，仅做最小值 1 与窗口右边距 1px 兜底
  const w = Math.max(1, Math.min(placeholderRect.width, Math.max(1, cw - x - 1)))
  // 高度：信任渲染层测量值，仅做最小值 1 与窗口下边距 1px 兜底
  const h = Math.max(1, Math.min(placeholderRect.height, Math.max(1, ch - y - 1)))
  matchatView.setBounds({ x, y, width: w, height: h })
}

/**
 * 构造注入 MatChat 页面的 QA 提取脚本（字符串形式，由 executeJavaScript 执行）。
 *
 * 三级提取策略（逐级降级）：
 *   1) 精确 selector：覆盖已知 DOM 结构（.message-item.user 等）
 *   2) 通用启发式：扫描 class 含 message/chat/msg/bubble/item 的元素，
 *      通过 class 中的 user/human/me vs assistant/bot/ai 关键词区分
 *   3) 顺序交替：找到消息列表但无法区分角色时，按奇偶顺序配对（user→assistant→user→...）
 *
 * 配对逻辑：对每条 user 消息，找"在它之后、下一条 user 消息之前"的所有 assistant 消息，拼接为回答。
 * 取最后 N 条（N 钳到 [1,20]）返回。
 * 全部失败时返回 { __debug: true, candidates: [...] } 供排查 DOM 结构。
 */
function buildExtractScript(pairs: number): string {
  // 钳到 [1, 20]，防止传入 0 或超大值
  const N = Math.max(1, Math.min(20, pairs | 0))
  return `(() => {
  try {
  const $$ = (s, r = document) => Array.from(r.querySelectorAll(s))
  // 判断元素是否为"有效对话内容"：排除 script/style/noscript/link 等框架标签
  const isContentTag = (el) => {
    const tag = (el.tagName || '').toUpperCase()
    return tag !== 'SCRIPT' && tag !== 'STYLE' && tag !== 'NOSCRIPT' && tag !== 'LINK' && tag !== 'META'
  }
  // 判断文本是否为"有效对话文本"：排除 Next.js/React 框架 hydration 数据
  const isRealContent = (text) => {
    if (!text || text.length < 2) return false
    // Next.js SSR hydration 特征
    if (text.includes('self.__next_f') || text.includes('self.__next')) return false
    if (text.includes('__next_f.push') || text.includes('self.__next_s')) return false
    // React/Remix 等框架数据
    if (text.includes('__reactF$') || text.includes('__reactInternalInstance$')) return false
    // JS chunk / asset 路径
    if (/\\/_next\\/static\\/chunks\\//.test(text)) return false
    if (text.includes('data-reactroot') && text.length > 500) return false
    return true
  }
  // 从元素中提取纯文本：克隆后移除所有非正文节点，再取 innerText
  const getText = (el) => {
    // 跳过框架标签本身
    if (!isContentTag(el)) return ''
    const c = el.cloneNode(true)
    // 移除所有非正文子节点（包括 type=application/json 的 Next.js 数据 script）
    c.querySelectorAll('script, style, noscript, link, meta, [type="application/json"]').forEach((n) => n.remove())
    // 移除 data 标签中的 script 类子元素
    const text = (c.innerText || c.textContent || '').trim()
    return isRealContent(text) ? text : ''
  }
  // 判断元素角色：返回 'user' / 'assistant' / null
  const roleOf = (el) => {
    const cls = (typeof el.className === 'string' ? el.className : '').toLowerCase()
    const dr = (el.getAttribute('data-role') || '').toLowerCase()
    const testid = (el.getAttribute('data-testid') || '').toLowerCase()
    const all = cls + ' ' + dr + ' ' + testid
    if (/user|human|\\bme\\b|self|question|prompt|发送/.test(all)) return 'user'
    if (/assistant|bot|\\bai\\b|model|answer|response|reply|gpt|回复/.test(all)) return 'assistant'
    return null
  }

  // ===== 配对组装容器 =====
  const pairList = []

  // ===== 策略 0：MatChat 专用 —— Tailwind CSS 段落提取 =====
  // MatChat 使用纯 Tailwind CSS，对话段落 class 为 "text-gray-700 mb-3 ..."
  // 用户问题和 AI 回答的段落 class 相同，按出现顺序区分：
  // 第一个段落 = 用户问题，后续段落 = AI 回答
  {
    const paras = $$('.text-gray-700, [class*="leading-relaxed"]').filter(el => {
      if (!isContentTag(el)) return false
      const t = getText(el)
      return t.length > 2 && t.length < 20000 && isRealContent(t)
    })
    if (paras.length >= 2) {
      const q = getText(paras[0])
      const a = paras.slice(1).map(getText).filter(t => t.length > 0).join('\\n\\n')
      if (q && a) pairList.push({ q, a })
    }
  }

  // ===== 策略 1-3：传统语义化选择器（策略 0 失败时回退） =====
  let qs = [], as = []
  if (!pairList.length) {
    // ===== 策略 1：精确 selector =====
    const STRATEGIES = [
      { q: '.message-item.user, [data-role="user"], .chat-message__user, div[class*="user-message"], .chat-item.user',
        a: '.message-item.assistant, [data-role="assistant"], .chat-message__assistant, div[class*="assistant-message"], .chat-item.assistant' },
      { q: 'li[data-role="user"], [data-testid*="user-message"]',
        a: 'li[data-role="assistant"], [data-testid*="assistant-message"]' },
    ]
    for (const s of STRATEGIES) {
      qs = $$(s.q).filter(isContentTag); as = $$(s.a).filter(isContentTag)
      if (qs.length && as.length) break
    }

    // ===== 策略 2：通用启发式扫描（精确 selector 失败时） =====
    if (!qs.length || !as.length) {
      const msgSelectors = '[class*="message"], [class*="chat-item"], [class*="msg-"], [class*="bubble"], [class*="chat-msg"], [class*="chat-message"]'
      const allMsgs = $$(msgSelectors).filter(el => {
        if (!isContentTag(el)) return false
        const t = getText(el)
        return t.length > 2 && t.length < 10000
      })
      const users = allMsgs.filter(el => roleOf(el) === 'user')
      const assistants = allMsgs.filter(el => roleOf(el) === 'assistant')
      if (users.length && assistants.length) {
        qs = users; as = assistants
      }
    }

    // ===== 策略 3：顺序交替配对（能找到消息但无法区分角色时） =====
    if (!qs.length || !as.length) {
      const containers = $$('[class*="chat-list"], [class*="message-list"], [class*="messages"], [class*="conversation"], [class*="chat-body"]')
      let container = containers[0] || document.body
      const children = Array.from(container.children).filter(el => {
        if (!isContentTag(el)) return false
        const t = getText(el)
        return t.length > 2 && t.length < 5000
      })
      if (children.length >= 2) {
        qs = children.filter((_, i) => i % 2 === 0)
        as = children.filter((_, i) => i % 2 === 1)
      }
    }

    // ===== 配对组装 =====
    if (qs.length && as.length) {
      qs.forEach((qEl, idx) => {
        const nextQ = qs[idx + 1]
        const relatedA = as.filter((a) =>
          (qEl.compareDocumentPosition(a) & Node.DOCUMENT_POSITION_FOLLOWING)
          && (!nextQ || (nextQ.compareDocumentPosition(a) & Node.DOCUMENT_POSITION_PRECEDING))
        )
        const q = getText(qEl)
        const a = relatedA.map(getText).filter(Boolean).join('\\n\\n---\\n\\n')
        if (q && a) pairList.push({ q, a })
      })
    }
  }

  if (pairList.length) {
    return pairList.slice(pairList.length - ${N})
  }

  // ===== 全部失败：返回调试信息 =====
  const debugCandidates = []
  const allEls = $$('[class*="message"], [class*="chat"], [class*="msg"], [class*="bubble"], [class*="item"]')
  const seen = new Set()
  allEls.forEach(el => {
    if (!isContentTag(el)) return
    const t = (el.innerText || '').trim()
    if (t.length < 5 || t.length > 5000) return
    if (!isRealContent(t)) return
    const cls = typeof el.className === 'string' ? el.className : ''
    const key = el.tagName + '|' + cls
    if (seen.has(key)) return
    seen.add(key)
    debugCandidates.push({
      tag: el.tagName,
      class: cls.slice(0, 120),
      dataRole: el.getAttribute('data-role'),
      childCount: el.children.length,
      count: -1,
      textPreview: t.slice(0, 100),
    })
  })
  return { __debug: true, totalCandidates: debugCandidates.length, candidates: debugCandidates.slice(0, 30) }
  } catch (e) {
    return { __error: true, message: String(e?.message || e), stack: String(e?.stack || '').slice(0, 500) }
  }
})()`
}

/**
 * 注册所有 matchat:* IPC 通道。在 app ready 后由 main.ts 调用一次。
 * - handle: 双向调用（渲染层 await 拿结果）
 * - on:     单向发送（渲染层 fire-and-forget）
 */
export function registerMatchatIpc(): void {
  // attach：把 BrowserView 挂到主窗口并设置初始 bounds
  ipcMain.handle('matchat:attach', async (_e, rect: Rect) => {
    placeholderRect = rect || placeholderRect
    const win = getMainWindow()
    if (!win)
      return false
    const view = ensureView()
    win.addBrowserView(view)
    attached = true
    recomputeBounds()
    // 把 BrowserView 置顶（部分 Electron 版本需要显式调用）
    if (typeof (win as any).setTopBrowserView === 'function') {
      try {
        ;(win as any).setTopBrowserView(view)
      }
      catch { /* noop */ }
    }
    return true
  })

  // detach：从主窗口摘除 BrowserView（不销毁 webContents，保留登录态/会话）
  ipcMain.handle('matchat:detach', () => {
    const win = getMainWindow()
    if (win && matchatView)
      win.removeBrowserView(matchatView)
    attached = false
    return true
  })

  // setBounds：更新占位区并重算 bounds。高频调用（拖拽 splitter 时），用 ipcMain.on 单向发送避免 invoke 往返
  ipcMain.on('matchat:setBounds', (_e, rect: Rect) => {
    placeholderRect = rect || placeholderRect
    recomputeBounds()
  })

  // reload：重新加载 MatChat 首页
  ipcMain.handle('matchat:reload', () => {
    matchatView?.webContents.loadURL(MATCHAT_URL).catch(() => {})
    return true
  })

  // openExternal：用系统默认浏览器打开 MatChat
  ipcMain.handle('matchat:openExternal', () => {
    shell.openExternal(MATCHAT_URL)
    return true
  })

  // clearStorage：清除 MatChat 独立分区的持久化存储，用于切换账号/重置登录态
  ipcMain.handle('matchat:clearStorage', async () => {
    const sess = session.fromPartition(PARTITION)
    await sess.clearStorageData({ storages: ['cookies', 'localstorage', 'indexdb', 'cachestorage'] })
    matchatView?.webContents.loadURL(MATCHAT_URL).catch(() => {})
    return true
  })

  // extractLastQA：注入提取脚本到 MatChat 页面，返回最近 N 轮问答对
  ipcMain.handle('matchat:extractLastQA', async (_e, pairs = 1) => {
    if (!matchatView)
      return { ok: false, error: 'view_not_ready' }
    try {
      // 第二参数 true = userGesture，确保脚本在用户手势上下文执行（部分站点 CSP 限制）
      const data = await matchatView.webContents.executeJavaScript(buildExtractScript(pairs), true)
      // 诊断日志：仅打印长度信息，不输出 Q/A 原文（避免泄露用户对话内容到进程日志）
      if (Array.isArray(data)) {
        console.log(`[MatChat提取] 成功提取 ${data.length} 对问答`)
        data.forEach((pair: any, i: number) => {
          const qLen = String(pair?.q || '').length
          const aLen = String(pair?.a || '').length
          console.log(`  [${i + 1}] Q.len=${qLen} A.len=${aLen}`)
        })
      }
      else if (data && data.__debug) {
        console.warn(`[MatChat提取] 提取失败，返回调试信息:`, JSON.stringify(data).slice(0, 500))
      }
      else if (data && data.__error) {
        console.error(`[MatChat提取] 脚本内部异常: ${data.message}\n${data.stack}`)
        return { ok: false, error: `脚本异常: ${data.message}` }
      }
      return { ok: true, data }
    }
    catch (err: any) {
      console.error(`[MatChat提取] 异常:`, err?.message || err)
      return { ok: false, error: String(err?.message || err) }
    }
  })

  // openDevTools：调试 DOM selector 用，detach 模式独立窗口
  ipcMain.on('matchat:openDevTools', () => {
    matchatView?.webContents.openDevTools({ mode: 'detach' })
  })
}
