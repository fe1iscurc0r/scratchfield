// 文件上传域：解析文档 / 二进制上传（卷190-B3：从 MessageView.vue setup 纯搬移）
import { ref } from 'vue'
import API from '@/api/core'

interface FileUploadDeps {
  pushSystemMessage: (content: string) => any
  dispatchToActiveTab: (content: string, options?: any) => void
}

export function useMessageFileUpload(deps: FileUploadDeps) {
  const { pushSystemMessage, dispatchToActiveTab } = deps

  const fileInput = ref<HTMLInputElement | null>(null)

  function triggerUpload() {
    fileInput.value?.click()
  }

  async function handleFileUpload(event: Event) {
    const target = event.target as HTMLInputElement
    const file = target.files?.[0]
    if (!file)
      return

    const ext = file.name.split('.').pop()?.toLowerCase()
    const parseable = ['docx', 'xlsx', 'txt', 'csv', 'md']

    if (ext && parseable.includes(ext)) {
      // 解析文档内容后发送给文本模型
      const msg = pushSystemMessage(`正在解析文件: ${file.name}...`)
      try {
        const result = await API.parseDocument(file)
        const truncNote = result.truncated ? '（内容过长，已截断）' : ''
        msg.content = `文件解析完成: ${file.name}${truncNote}`
        dispatchToActiveTab(`以下是文件「${file.name}」的内容：\n\n${result.content}\n\n请分析这个文件的内容。`)
      }
      catch (err: any) {
        msg.content = `文件解析失败: ${err?.response?.data?.detail || err.message}`
      }
    }
    else {
      // 其他格式走原有上传逻辑
      const msg = pushSystemMessage(`正在上传文件: ${file.name}...`)
      try {
        const result = await API.uploadDocument(file)
        msg.content = `文件上传成功: ${file.name}`
        if (result.filePath) {
          dispatchToActiveTab(`请分析我刚上传的文件「${file.name}」，文件完整路径: ${result.filePath}`)
        }
      }
      catch (err: any) {
        msg.content = `文件上传失败: ${err.message}`
      }
    }
    target.value = ''
  }

  return {
    fileInput,
    triggerUpload,
    handleFileUpload,
  }
}
