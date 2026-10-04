/**
 * media 域 API（卷191-A2 从 core.ts 拆出）。
 *
 * 方法体纯搬运，签名与返回类型零变化。
 */
import type { DomainShape } from './_context'

export const mediaMethods = {
  getLive2dActions(): Promise<{ actions: string[] }> {
    return this.instance.get('/live2d/actions')
  },

  getMusicCommands(): Promise<{ commands: Array<{ action: string, track?: string }> }> {
    return this.instance.get('/music/commands')
  },

  transcribeAudio(file: Blob, options?: {
    language?: string
    model?: string
    prompt?: string
  }): Promise<{ text: string }> {
    const formData = new FormData()
    formData.append('file', file, 'recording.webm')
    if (options?.language)
      formData.append('language', options.language)
    if (options?.model)
      formData.append('model', options.model)
    if (options?.prompt)
      formData.append('prompt', options.prompt)
    return this.instance.post('/asr/transcribe', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
      timeout: 30000,
    })
  },
} satisfies DomainShape
