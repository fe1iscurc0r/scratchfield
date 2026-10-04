/**
 * 命令面板模糊匹配评分（卷150 任务A）——纯函数，node:test 可直接单测。
 *
 * 设计目标（验收项：输入 "eln" 两个键直达 ELN 视图）：
 * - 前缀命中 > 词首命中 > 连续子串 > 非连续子串 > 拼音/关键词命中
 * - 无引入任何库（自研，permissive 无忧；工单允许自研或轻量库，这里选自研）
 *
 * 评分越大越优先；0 = 不匹配。
 */

/** 单个候选词的得分 */
function scoreToken(query: string, token: string): number {
  if (!query || !token)
    return 0
  const q = query.toLowerCase()
  const t = token.toLowerCase()
  if (t === q)
    return 120 // 完全相等
  if (t.startsWith(q))
    return 100 - Math.min(t.length, 20) // 前缀命中，短词更优
  const idx = t.indexOf(q)
  if (idx === 0)
    return 100 - Math.min(t.length, 20)
  if (idx > 0) {
    // 词首字符命中加权（"e" 命中 "eln" 的 e 首字符）
    const boundary = /[\s\-_./]/.test(t[idx - 1] ?? '')
    return boundary ? 70 - Math.min(t.length, 20) : 50 - Math.min(t.length, 20) - Math.min(idx, 10)
  }
  // 非连续子串：字符全按序出现
  let ti = 0
  let hits = 0
  for (const ch of q) {
    const found = t.indexOf(ch, ti)
    if (found < 0)
      return 0
    ti = found + 1
    hits++
  }
  return hits === q.length ? 20 - Math.min(t.length - q.length, 10) : 0
}

export interface MatchCandidate {
  label: string
  keywords?: string[]
  /** 可选附加匹配文本（如英文说明） */
  extra?: string
}

export interface MatchResult<T extends MatchCandidate> {
  item: T
  score: number
}

/** 对候选集打分并排序（稳定排序，同分保持原序） */
export function fuzzyMatch<T extends MatchCandidate>(
  query: string,
  candidates: T[],
): MatchResult<T>[] {
  if (!query.trim())
    return candidates.map(item => ({ item, score: 1 }))

  const q = query.trim().toLowerCase()
  const out: MatchResult<T>[] = []
  for (const item of candidates) {
    const tokens = [item.label, ...(item.keywords ?? []), ...(item.extra ? [item.extra] : [])]
    let best = 0
    for (const tk of tokens) {
      const s = scoreToken(q, tk)
      if (s > best)
        best = s
    }
    if (best > 0) {
      // 动作条目降权 30：同等匹配度下视图显著优先
      // （"eln" 直达 ELN 视图而非"新建 ELN 记录"；30 = 高置信分差阈值 25，
      //   保证同分视图/动作对不会被误判为"唯一命中"）
      const isAction = !!(item as { action?: unknown }).action
      if (isAction && best > 30)
        best -= 30
      out.push({ item, score: best })
    }
  }
  // 稳定排序：score 相等时保持原顺序（Array.prototype.sort 在现代引擎是稳定的）
  out.sort((a, b) => b.score - a.score)
  return out
}

/** 是否命中「唯一且高分」——命中后可直接回车跳转（双键直达体验） */
export function isConfidentTopHit<T extends MatchCandidate>(
  results: MatchResult<T>[],
  minScore = 95,
): boolean {
  if (results.length === 0)
    return false
  const top = results[0]!
  if (top.score < minScore)
    return false
  if (results.length === 1)
    return true
  const second = results[1]!
  return top.score - second.score >= 25
}
