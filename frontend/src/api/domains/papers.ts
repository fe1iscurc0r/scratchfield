import type { DomainShape } from './_context'
/**
 * papers 域 API（卷191-A2 从 core.ts 拆出）。
 *
 * 方法体纯搬运，签名与返回类型零变化。
 */
import type { Paper } from './_types'

export const papersMethods = {
  listPapers(params: { q?: string, tag?: string, year?: number, limit?: number, offset?: number } = {}): Promise<{ success: boolean, papers: Paper[], total: number }> {
    return this.instance.get('/api/papers', { params })
  },

  getPaper(id: number): Promise<{ success: boolean, paper: Paper }> {
    return this.instance.get(`/api/papers/${id}`)
  },

  createPaper(data: Partial<Paper> & { title: string }): Promise<{ success: boolean, paper: Paper }> {
    return this.instance.post('/api/papers', data)
  },

  updatePaper(id: number, data: Partial<Paper>): Promise<{ success: boolean, paper: Paper }> {
    return this.instance.put(`/api/papers/${id}`, data)
  },

  deletePaper(id: number): Promise<{ success: boolean }> {
    return this.instance.delete(`/api/papers/${id}`)
  },

  importPapers(items: Array<Record<string, unknown>>): Promise<{ success: boolean, imported: number, ids: number[], skipped: Array<{ index: number, error: string }> }> {
    return this.instance.post('/api/papers/import', items)
  },

  importDoi(doi: string, tags?: string[]): Promise<{ success: boolean, paper?: Paper, doi?: string, error?: string, fallback?: string }> {
    return this.instance.post('/api/papers/import-doi', { doi, tags })
  },

  linkPaperExperiments(id: number, experimentIds: string[]): Promise<{ success: boolean, paper: Paper }> {
    return this.instance.put(`/api/papers/${id}/experiments`, { experiment_ids: experimentIds })
  },
} satisfies DomainShape
