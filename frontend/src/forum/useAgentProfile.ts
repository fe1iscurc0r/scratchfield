import type { ForumProfile } from './types'
import { ref, watch } from 'vue'
import { ACCESS_TOKEN } from '@/api'
import { sessionRestored } from '@/composables/useAuth'
import { backendConnected } from '@/utils/config'
import { fetchProfile, updateProfile } from './api'

const profile = ref<ForumProfile | null>(null)
const profileError = ref('')
const profileLoading = ref(false)
let loading: Promise<void> | null = null

function formatForumError(e: any) {
  const detail = e?.response?.data?.detail
  if (e?.response?.status === 401) {
    return '登录状态已失效，请重新登录scratchpad 网络'
  }
  if (detail?.error === 'upstream_non_json_response') {
    return `社区服务暂不可用：上游返回 ${detail.statusCode || detail.status_code}，类型 ${detail.contentType || detail.content_type || 'unknown'}`
  }
  if (typeof detail === 'string' && detail.trim()) {
    return `加载失败: ${detail}`
  }
  if (detail?.message) {
    return `加载失败: ${detail.message}`
  }
  return `加载失败: ${e?.message || 'unknown error'}`
}

export function useForumProfile() {
  async function waitUntilReady() {
    if (!backendConnected.value) {
      await new Promise<void>((resolve) => {
        const stop = watch(backendConnected, (ready) => {
          if (ready) {
            stop()
            resolve()
          }
        })
        setTimeout(() => {
          stop()
          resolve()
        }, 5000)
      })
    }

    if (!ACCESS_TOKEN.value)
      return

    if (!sessionRestored.value) {
      await new Promise<void>((resolve) => {
        const stop = watch(sessionRestored, (ready) => {
          if (ready) {
            stop()
            resolve()
          }
        })
        setTimeout(() => {
          stop()
          resolve()
        }, 5000)
      })
    }
  }

  async function load() {
    if (profile.value)
      return

    await waitUntilReady()

    // 未登录（无 token）直接返回，不发请求
    if (!ACCESS_TOKEN.value) {
      profileError.value = '请先登录后使用scratchpad 网络'
      return
    }

    if (!loading) {
      profileLoading.value = true
      profileError.value = ''
      loading = fetchProfile().then((data) => {
        profile.value = data
      }).catch((e: any) => {
        profileError.value = formatForumError(e)
        // 请求失败，允许后续重试
        loading = null
      }).finally(() => {
        profileLoading.value = false
      })
    }
    await loading
  }

  async function reload() {
    loading = null
    profile.value = null
    profileError.value = ''
    await load()
  }

  async function setForumEnabled(enabled: boolean) {
    await updateProfile({ forumEnabled: enabled } as any)
    if (profile.value) {
      profile.value = { ...profile.value, forumEnabled: enabled }
    }
  }

  return { profile, profileError, profileLoading, load, reload, setForumEnabled }
}

// Backward-compatible alias
export function useAgentProfile() {
  return useForumProfile()
}
