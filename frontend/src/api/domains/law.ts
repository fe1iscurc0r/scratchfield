import type { DomainShape } from './_context'
/**
 * law 域 API（卷191-A2 从 core.ts 拆出）。
 *
 * 方法体纯搬运，签名与返回类型零变化。
 */
import type { Paper, VonStatus } from './_types'

export const lawMethods = {
  importLawCases(
    files: File[],
    source = 'manual',
    licenseNote = '',
    autoTag = true,
  ): Promise<{
    success: boolean
    domain: string
    total_files: number
    imported: number
    queued_count: number
    inserted: Array<{ filename: string, id: number, case_no: string, court: string, title: string }>
    queued: Array<{ filename: string, error: string, queued_path?: string }>
    tagging?: {
      enabled: boolean
      attempted: number
      tagged?: number
      low_confidence?: number
      failed?: number
      skipped: boolean
      reason?: string
    }
  }> {
    const form = new FormData()
    for (const f of files)
      form.append('files', f)
    form.append('source', source)
    form.append('license_note', licenseNote)
    form.append('auto_tag', autoTag ? 'true' : 'false')
    return this.instance.post('/api/domains/law/import-cases', form, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
  },

  importLawFlk(names?: string[]): Promise<Record<string, unknown>> {
    return this.instance.post('/api/domains/law/import-flk', names ? { names } : {})
  },

  getLawCaseQueue(): Promise<{ success: boolean, count: number, items: Array<Record<string, unknown>> }> {
    return this.instance.get('/api/domains/law/queue')
  },

  getVonStatus(): Promise<VonStatus> {
    return this.instance.get('/api/domains/law/von-status')
  },

  getLawTagPendingPreview(): Promise<{
    success: boolean
    pending: number
    total: number
    von: Omit<VonStatus, 'success'>
  }> {
    return this.instance.get('/api/domains/law/tag-pending-preview')
  },

  tagLawCases(
    ids: number[] = [],
    onlyUntagged = true,
  ): Promise<{
    success: boolean
    von_available: boolean
    message?: string
    processed: number
    tagged?: number
    low_confidence?: number
    results?: Array<Record<string, unknown>>
  }> {
    return this.instance.post('/api/domains/law/tag-cases', {
      ids,
      only_untagged: onlyUntagged,
    })
  },

  tagLawPending(ids: number[] = []): Promise<{
    success: boolean
    von_available: boolean
    message?: string
    processed: number
  }> {
    return this.instance.post('/api/domains/law/tag-pending', ids.length ? { ids } : {})
  },

  getLawTagQueue(): Promise<{ success: boolean, count: number, items: Array<Record<string, unknown>> }> {
    return this.instance.get('/api/domains/law/tag-queue')
  },

  confirmLawTag(
    id: number,
    question: string,
    value: string | boolean | number,
  ): Promise<{
    success: boolean
    id: number
    question: string
    value: string | boolean | number
    confidence: number
    source: string
    queue_entry_removed: boolean
    paper: Paper
  }> {
    return this.instance.post('/api/domains/law/tag-confirm', { id, question, value })
  },
} satisfies DomainShape
