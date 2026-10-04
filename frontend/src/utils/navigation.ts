/**
 * 全局导航数据层（卷150 任务A/C）——侧边栏、命令面板、快捷键共用唯一真源。
 *
 * 纯数据 + 纯函数，无 Vue/Electron/Router 依赖 ⇒ node:test 可直接单测。
 * 视图层（AppSidebar / CommandPalette / App.vue 快捷键层）只消费，不自持清单。
 *
 * 分组约定（与工单一致）：
 *   对话 / 科研四件套(文献·ELN·数据·预测) / 知识三视图(记忆·知识库·思维) / 射频 / 系统
 */

export interface NavItem {
  /** 路由 path（vue-router hash 路由） */
  to: string
  /** 显示名（术语表 docs/ui-terms.md 为准） */
  label: string
  /** 命令面板别名/拼音关键词（小写） */
  keywords: string[]
  /** 内嵌 SVG path（24x24 viewBox, stroke=currentColor） */
  icon: string
  /** 是否为常用动作（非路由导航），命令面板可额外收录 */
  action?: 'new-eln' | 'new-chat' | 'doi-import'
  /** 悬浮球模式下是否可见（默认 true；悬浮球有自己的入口） */
  hiddenInFloating?: boolean
}

export interface NavGroup {
  /** 分组键（快捷键 Ctrl+<n> 用序号，不 hardcode 名） */
  key: string
  label: string
  items: NavItem[]
}

/** 内嵌 SVG：stroke 继承 currentColor（与 PanelView 的 menuIcon 同风格） */
export function navIcon(paths: string): string {
  return `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">${paths}</svg>`
}

// ── 分组定义（唯一真源）──────────────────────────────────────

export const NAV_GROUPS: NavGroup[] = [
  {
    key: 'chat',
    label: '对话',
    items: [
      {
        to: '/chat',
        label: '对话',
        keywords: ['chat', 'duihua', '聊天', '会话', 'message'],
        icon: navIcon('<path d="M21 15a2 2 0 0 1-2 2H8l-4 4V6a2 2 0 0 1 2-2h13a2 2 0 0 1 2 2z"/>'),
      },
      {
        to: '/model',
        label: '思维旅行',
        keywords: ['travel', 'model', 'siwei', 'lvxing', '旅行'],
        icon: navIcon('<circle cx="12" cy="12" r="9"/><path d="M12 3a15 15 0 0 1 0 18"/><path d="M3 12h18"/>'),
      },
    ],
  },
  {
    key: 'research',
    label: '科研四件套',
    items: [
      {
        to: '/papers',
        label: '文献',
        keywords: ['papers', 'wenxian', 'lunwen', '论文', '文献库'],
        icon: navIcon('<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><path d="M14 2v6h6"/><path d="M16 13H8"/><path d="M16 17H8"/>'),
      },
      {
        to: '/eln',
        label: 'ELN',
        keywords: ['eln', '实验记录', '电子实验记录', 'shíyàn'],
        icon: navIcon('<path d="M10 2v7.5a2 2 0 0 1-.2.9L4.7 20.5a1 1 0 0 0 .9 1.5h12.8a1 1 0 0 0 .9-1.5L14.2 10.4a2 2 0 0 1-.2-.9V2"/><path d="M8.5 2h7"/><path d="M7 16h10"/>'),
      },
      {
        to: '/voice-eln',
        label: '语音ELN',
        keywords: ['voice', 'yuyin', '语音', '语音实验'],
        icon: navIcon('<path d="M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z"/><path d="M19 10v2a7 7 0 0 1-14 0v-2"/>'),
      },
      {
        to: '/data',
        label: '数据',
        keywords: ['data', 'shuju', '数据处理', '图表'],
        icon: navIcon('<path d="M21 5c0 1.66-4 3-9 3S3 6.66 3 5s4-3 9-3 9 1.34 9 3z"/><path d="M3 5v14c0 1.66 4 3 9 3s9-1.34 9-3V5"/>'),
      },
    ],
  },
  {
    key: 'knowledge',
    label: '知识',
    items: [
      {
        to: '/memory',
        label: '记忆',
        keywords: ['memory', 'jiyi', '五元组', 'quintuple'],
        icon: navIcon('<path d="M12 3a9 9 0 1 0 9 9"/><path d="M12 7v5l3 2"/>'),
      },
      {
        to: '/knowledge',
        label: '知识库',
        keywords: ['knowledge', 'zhishi', '知识库', 'matchat', '文档'],
        icon: navIcon('<path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"/><path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"/>'),
      },
      {
        to: '/mind',
        label: '思维',
        keywords: ['mind', 'siwei', '思维导图', '图谱', 'graph'],
        icon: navIcon('<circle cx="12" cy="12" r="3"/><circle cx="5" cy="5" r="2"/><circle cx="19" cy="5" r="2"/><circle cx="5" cy="19" r="2"/><circle cx="19" cy="19" r="2"/><path d="M7 7l3 3M17 7l-3 3M7 17l3-3M17 17l-3-3"/>'),
      },
    ],
  },
  {
    key: 'radio',
    label: '射频',
    items: [
      {
        to: '/radio',
        label: '频谱',
        keywords: ['radio', 'pindao', '频谱', 'sdr', 'ic705', '电台'],
        icon: navIcon('<path d="M4 20V10"/><path d="M9 20V4"/><path d="M14 20V13"/><path d="M19 20V7"/>'),
      },
    ],
  },
  {
    key: 'system',
    label: '系统',
    items: [
      {
        to: '/skill',
        label: '技能',
        keywords: ['skill', 'jineng', '技能工坊', 'skills'],
        icon: navIcon('<path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z"/>'),
      },
      {
        to: '/market',
        label: '市场',
        keywords: ['market', 'shichang', '枢机集市', 'marketplace'],
        icon: navIcon('<path d="M6 2 3 6v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2V6l-3-4z"/><path d="M3 6h18"/><path d="M16 10a4 4 0 0 1-8 0"/>'),
      },
      {
        to: '/config',
        label: '设置',
        keywords: ['config', 'shezhi', '设置', '终端设置', 'settings'],
        icon: navIcon('<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 1 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 1 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 1 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 1 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/>'),
      },
      // 卷181-A：设置四子页直达（keywords 覆盖用户会搜的中文意图词，≥6 个）
      {
        to: '/config/model',
        label: '设置 · 模型连接',
        keywords: ['模型', '模型连接', '切换模型', '供应商', 'api', 'apikey', 'api密钥', '密钥', 'moxing', 'model'],
        icon: navIcon('<rect x="3" y="4" width="18" height="14" rx="2"/><path d="M7 9h10M7 13h6"/>'),
      },
      {
        to: '/config/memory',
        label: '设置 · 记忆连接',
        keywords: ['记忆', '记忆连接', '记忆库', '向量', '向量库', 'embedding', '记忆服务', 'jiyi', 'memory'],
        icon: navIcon('<ellipse cx="12" cy="5" rx="9" ry="3"/><path d="M21 5v14c0 1.66-4 3-9 3s-9-1.34-9-3V5"/>'),
      },
      {
        to: '/config/audio',
        label: '设置 · 音画配置',
        keywords: ['音画', '语音', '声音', '音色', 'live2d', '模型外观', '语音合成', 'tts', '唤醒词', 'terminal', 'yinxiang'],
        icon: navIcon('<path d="M11 5 6 9H2v6h4l5 4z"/><path d="M15.5 8.5a5 5 0 0 1 0 7"/><path d="M18.5 5.5a9 9 0 0 1 0 13"/>'),
      },
      {
        to: '/config/notifications',
        label: '设置 · 通知设置',
        keywords: ['通知', '推送', '提醒', '告警', '消息提醒', 'tongzhi', 'notification', 'push'],
        icon: navIcon('<path d="M18 8a6 6 0 0 0-12 0c0 7-3 9-3 9h18s-3-2-3-9"/><path d="M13.7 21a2 2 0 0 1-3.4 0"/>'),
      },
      {
        to: '/config/agent',
        label: '设置 · 干员设置',
        keywords: ['agent', 'agent设置', '干员', '干员设置', '通讯录', '人设', '工具权限', 'ganyuan', 'builtin'],
        icon: navIcon('<circle cx="12" cy="8" r="4"/><path d="M4 21c0-4 3.6-7 8-7s8 3 8 7"/>'),
      },
      {
        to: '/config/tools',
        label: '设置 · 工具健康',
        keywords: ['工具健康', '工具', '画像', '熔断', '调用统计', '延迟', '失败率', 'tool', 'health', 'circuit', 'gongju'],
        icon: navIcon('<path d="M3 12h4l2-7 4 14 2-7h6"/>'),
      },
    ],
  },
]

/** 命令面板额外收录的常用动作（非路由导航） */
export const NAV_ACTIONS: NavItem[] = [
  {
    to: 'action:new-eln',
    label: '新建 ELN 记录',
    keywords: ['new-eln', 'xinjian', '新建记录', 'eln'],
    icon: navIcon('<path d="M12 5v14M5 12h14"/>'),
    action: 'new-eln',
  },
  {
    to: 'action:new-chat',
    label: '新对话',
    keywords: ['new-chat', 'xinjian', '新会话', 'chat'],
    icon: navIcon('<path d="M12 5v14M5 12h14"/>'),
    action: 'new-chat',
  },
  {
    to: 'action:doi-import',
    label: 'DOI 导入文献',
    keywords: ['doi', 'daoru', '导入', 'import', '文献'],
    icon: navIcon('<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><path d="M7 10l5 5 5-5"/><path d="M12 15V3"/>'),
    action: 'doi-import',
  },
]

/** 扁平化的全部可导航项（视图） */
export function allNavItems(): NavItem[] {
  return NAV_GROUPS.flatMap(g => g.items)
}

/** 命令面板候选全集 = 视图 + 动作 */
export function commandCandidates(): NavItem[] {
  return [...allNavItems(), ...NAV_ACTIONS]
}

/** 按 path 查找（路由高亮用） */
export function findNavByPath(path: string): NavItem | undefined {
  return allNavItems().find(i => i.to === path)
}

/** 快捷键 Ctrl+<n> 的分组序号（n 从 1 起） */
export function groupIndexMap(): Record<string, number> {
  const map: Record<string, number> = {}
  NAV_GROUPS.forEach((g, i) => {
    map[g.key] = i + 1
  })
  return map
}
