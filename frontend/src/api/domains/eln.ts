import type { DomainShape } from './_context'
/**
 * eln 域 API（卷191-A2 从 core.ts 拆出）。
 *
 * 方法体纯搬运，签名与返回类型零变化。
 */
import type { ElnRecord, ElnRecordInput } from './_types'

export const elnMethods = {
  elnList(q?: string): Promise<{
    ok: boolean
    count: number
    records: ElnRecord[]
  }> {
    return this.instance.get('/api/eln/records', { params: q ? { q } : {} })
  },

  elnCreate(record: ElnRecordInput): Promise<{ ok: boolean, record: ElnRecord }> {
    return this.instance.post('/api/eln/records', record)
  },

  elnGet(recordId: string): Promise<{ ok: boolean, record: ElnRecord }> {
    return this.instance.get(`/api/eln/records/${encodeURIComponent(recordId)}`)
  },

  elnUpdate(recordId: string, record: ElnRecordInput): Promise<{ ok: boolean, record: ElnRecord }> {
    return this.instance.put(`/api/eln/records/${encodeURIComponent(recordId)}`, record)
  },

  elnExport(recordId: string): Promise<{ ok: boolean, recordId: string, filename: string, markdown: string }> {
    return this.instance.get(`/api/eln/records/${encodeURIComponent(recordId)}/export`)
  },

  elnTemplates(): Promise<{ ok: boolean, count: number, templates: string[] }> {
    return this.instance.get('/api/eln/templates')
  },

  elnFromDesign(params: {
    topic: string
    date?: string
    status?: string
    factors: Record<string, [number, number]>
  }): Promise<{ ok: boolean, record: ElnRecord, runs: number }> {
    return this.instance.post('/api/eln/from-design', params)
  },

  elnUploadAttachment(recordId: string, file: File): Promise<{ ok: boolean, recordId: string, attachment: string, bytes: number }> {
    const formData = new FormData()
    formData.append('file', file)
    return this.instance.post(`/api/eln/records/${encodeURIComponent(recordId)}/attachments`, formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
      timeout: 60000,
    })
  },
} satisfies DomainShape
