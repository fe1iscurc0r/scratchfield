/**
 * dataTools 域 API（卷191-A2 从 core.ts 拆出）。
 *
 * 方法体纯搬运，签名与返回类型零变化。
 */
import type { DomainShape } from './_context'

export const dataToolsMethods = {
  dataToolsSamples(): Promise<{
    ok: boolean
    samples: Record<'tga' | 'dsc' | 'xrd' | 'raman', { label: string, content: string }>
  }> {
    return this.instance.get('/api/data-tools/samples')
  },

  dataToolsParse(file: File): Promise<{
    ok: boolean
    filename: string
    delimiter: string
    columns: string[]
    numericColumns: string[]
    rowCount: number
    preview: Record<string, string | number | null>[]
  }> {
    const formData = new FormData()
    formData.append('file', file)
    return this.instance.post('/api/data-tools/parse', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
      timeout: 60000,
    })
  },

  dataToolsPlot(params: {
    file: File
    dataType: 'tga' | 'dsc' | 'xrd' | 'raman'
    xCol: string
    yCol: string
    title?: string
    massMg?: number
    smoothWindow?: number
    topic?: string
    recordId?: string
  }): Promise<{ ok: boolean, attachment: string, recordId: string | null, dataType: string }> {
    const formData = new FormData()
    formData.append('file', params.file)
    formData.append('data_type', params.dataType)
    formData.append('x_col', params.xCol)
    formData.append('y_col', params.yCol)
    if (params.title)
      formData.append('title', params.title)
    if (params.massMg != null)
      formData.append('mass_mg', String(params.massMg))
    if (params.smoothWindow != null)
      formData.append('smooth_window', String(params.smoothWindow))
    if (params.topic)
      formData.append('topic', params.topic)
    if (params.recordId)
      formData.append('record_id', params.recordId)
    return this.instance.post('/api/data-tools/plot', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
      timeout: 60000,
    })
  },
} satisfies DomainShape
