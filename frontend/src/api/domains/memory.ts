import type { DomainShape } from './_context'
/**
 * memory 域 API（卷191-A2 从 core.ts 拆出）。
 *
 * 方法体纯搬运，签名与返回类型零变化。
 */
import type { GraphSummary, MemoryStats, QuintuplePage } from './_types'

export const memoryMethods = {
  getMemoryStats(): Promise<{
    status: string
    memoryStats: { enabled: true } & MemoryStats
      | { enabled: false, message: string }
  }> {
    return this.instance.get('/memory/stats')
  },

  ragIngestText(params: {
    title: string
    content: string
    tags?: string[]
    source?: string
    metadata?: Record<string, any>
  }): Promise<{
    success: boolean
    docId?: string
    doc?: { docId: string, title: string, tags: string[], source?: string }
    error?: string
  }> {
    return this.instance.post('/api/rag/document', params, { timeout: 180 * 1000 })
  },

  ragList(params?: {
    keyword?: string
    source?: string
    limit?: number
    offset?: number
  }): Promise<{
    success: boolean
    documents: Array<{
      docId: string
      title: string
      tags: string[]
      source?: string
      chunkCount: number
      createdAt: string
      preview: string
    }>
    total: number
    error?: string
  }> {
    return this.instance.get('/api/rag/documents', { params: params || {} })
  },

  ragDelete(docId: string): Promise<{ success: boolean, error?: string }> {
    return this.instance.delete(`/api/rag/documents/${encodeURIComponent(docId)}`, { timeout: 30 * 1000 })
  },

  ragQuery(params: {
    query: string
    topK?: number
    tags?: string[]
    minScore?: number
    rerank?: boolean
  }): Promise<any> {
    return this.instance.post('/api/rag/query', params, { timeout: 60 * 1000 })
  },

  getQuintuples(params?: {
    offset?: number
    limit?: number
    entityType?: string
    q?: string
    orderBy?: string
    withDegree?: boolean
  }): Promise<QuintuplePage> {
    const qs = new URLSearchParams()
    if (params?.offset !== undefined)
      qs.set('offset', String(params.offset))
    if (params?.limit !== undefined)
      qs.set('limit', String(params.limit))
    if (params?.entityType)
      qs.set('entity_type', params.entityType)
    if (params?.q)
      qs.set('q', params.q)
    if (params?.orderBy)
      qs.set('order_by', params.orderBy)
    if (params?.withDegree)
      qs.set('with_degree', 'true')
    const suffix = qs.toString() ? `?${qs}` : ''
    return this.instance.get(`/memory/quintuples${suffix}`)
  },

  searchQuintuples(keywords: string): Promise<QuintuplePage> {
    return this.instance.get(`/memory/quintuples/search?keywords=${encodeURIComponent(keywords)}`)
  },

  getGraphSummary(topN = 20): Promise<GraphSummary> {
    return this.instance.get(`/memory/graph/summary?top_n=${topN}`)
  },

  getContextStats(days?: number) {
    return this.instance.get(`/logs/context/statistics?days=${days}`)
  },

  loadContext(days?: number): Promise<{
    status: 'success'
    messages: { role: 'user' | 'assistant', content: string }[]
    count: number
    days: number
  }> {
    return this.instance.get(`/logs/context/load?days=${days}`)
  },
} satisfies DomainShape
