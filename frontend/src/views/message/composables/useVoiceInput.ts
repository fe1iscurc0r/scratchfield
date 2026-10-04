// 语音输入域：MediaRecorder + ASR API（卷190-B3：从 MessageView.vue setup 纯搬移）
import { ref } from 'vue'
import API from '@/api/core'
import { CONFIG } from '@/utils/config'

interface VoiceInputDeps {
  pushSystemMessage: (content: string) => any
  dispatchToActiveTab: (content: string, options?: { voiceInput?: boolean }) => void
}

export function useVoiceInput(deps: VoiceInputDeps) {
  const { pushSystemMessage, dispatchToActiveTab } = deps

  const isRecording = ref(false)
  let mediaRecorder: MediaRecorder | null = null
  let audioChunks: Blob[] = []

  async function toggleVoiceInput() {
    if (!CONFIG.value.voice_realtime.enabled)
      return

    if (isRecording.value) {
      stopVoiceInput()
      return
    }

    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
      audioChunks = []
      mediaRecorder = new MediaRecorder(stream, { mimeType: getSupportedMimeType() })

      mediaRecorder.ondataavailable = (e) => {
        if (e.data.size > 0)
          audioChunks.push(e.data)
      }

      mediaRecorder.onstop = async () => {
        // 停止所有音轨，释放麦克风
        stream.getTracks().forEach(t => t.stop())
        if (audioChunks.length === 0)
          return

        const audioBlob = new Blob(audioChunks, { type: mediaRecorder?.mimeType || 'audio/webm' })
        try {
          const { text } = await API.transcribeAudio(audioBlob, { language: 'zh' })
          if (text && typeof text === 'string' && text.trim()) {
            // 语音识别成功：直接发送（带语音标注前缀）
            dispatchToActiveTab(`以下是用户的语音输入：【${text.trim()}】`, { voiceInput: true })
          }
        }
        catch (err: any) {
          const status = err?.response?.status
          if (status === 401) {
            pushSystemMessage('语音识别需要登录后使用')
          }
          else if (status === 402) {
            pushSystemMessage('余额不足，无法使用语音识别')
          }
          else {
            pushSystemMessage(`语音识别失败: ${err.message || err}`)
          }
        }
      }

      mediaRecorder.start()
      isRecording.value = true
    }
    catch (err: any) {
      if (err.name === 'NotAllowedError') {
        pushSystemMessage('麦克风权限被拒绝，请在系统设置中允许麦克风访问')
      }
      else {
        pushSystemMessage(`无法启动录音: ${err.message || err}`)
      }
    }
  }

  function stopVoiceInput() {
    if (mediaRecorder && mediaRecorder.state !== 'inactive') {
      mediaRecorder.stop()
    }
    mediaRecorder = null
    isRecording.value = false
  }

  function getSupportedMimeType(): string {
    const types = ['audio/webm;codecs=opus', 'audio/webm', 'audio/ogg;codecs=opus', 'audio/mp4']
    for (const t of types) {
      if (MediaRecorder.isTypeSupported(t))
        return t
    }
    return ''
  }

  return {
    isRecording,
    toggleVoiceInput,
    stopVoiceInput,
  }
}
