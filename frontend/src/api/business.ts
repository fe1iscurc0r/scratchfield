import type { AxiosError } from 'axios'
import axios from 'axios'
import camelcaseKeys from 'camelcase-keys'
import { ACCESS_TOKEN } from './index'

const BUSINESS_BASE = 'http://localhost:8000'

const businessClient = axios.create({
  baseURL: BUSINESS_BASE,
  timeout: 15_000,
  headers: { 'Content-Type': 'application/json' },
  transformResponse: [(data: string) => {
    try {
      return camelcaseKeys(JSON.parse(data), { deep: true })
    }
    catch { return data }
  }],
})

businessClient.interceptors.request.use((config) => {
  if (ACCESS_TOKEN.value) {
    config.headers.Authorization = `Bearer ${ACCESS_TOKEN.value}`
  }
  return config
})

// 401 时通过本地后端刷新 token 并重试（businessClient 直连 NagaBusiness，不经过本地后端的刷新逻辑）
let _bizRefreshing = false
let _bizRefreshQueue: Array<(token: string) => void> = []

businessClient.interceptors.response.use(
  response => response,
  async (error: AxiosError & { config: { _retry?: boolean } }) => {
    if (error.response?.status !== 401 || !error.config || error.config._retry || !ACCESS_TOKEN.value) {
      return Promise.reject(error)
    }
    if (_bizRefreshing) {
      return new Promise((resolve) => {
        _bizRefreshQueue.push((token: string) => {
          error.config.headers.Authorization = `Bearer ${token}`
          resolve(businessClient(error.config))
        })
      })
    }
    error.config._retry = true
    _bizRefreshing = true
    try {
      // 调用本地后端刷新（后端管理 refresh_token）
      const port = 8000
      const resp = await axios.post<{ access_token: string }>(`http://localhost:${port}/auth/refresh`, {})
      const newToken = resp.data.access_token
      if (newToken) {
        ACCESS_TOKEN.value = newToken
        _bizRefreshQueue.forEach(cb => cb(newToken))
        _bizRefreshQueue = []
        _bizRefreshing = false
        error.config.headers.Authorization = `Bearer ${newToken}`
        return businessClient(error.config)
      }
    }
    catch { /* refresh failed */ }
    _bizRefreshing = false
    _bizRefreshQueue.forEach(cb => cb(''))
    _bizRefreshQueue = []
    return Promise.reject(error)
  },
)

// ── 模型定价 ──

export interface ModelPricing {
  id: string
  inputPrice?: number | string
  outputPrice?: number | string
  [key: string]: unknown
}

export function getModels(): Promise<{ object: string, data: ModelPricing[] }> {
  return businessClient.get('/api/v1/models').then(r => r.data)
}

// ── 积分 ──

export function getCredits(): Promise<{
  creditsTotal: string
  creditsUsed: string
  creditsFrozen: string
  creditsAvailable: string
  dailyRequests: number
  planId: number
}> {
  return businessClient.get('/api/quota/credits').then(r => r.data)
}

export function redeemCode(code: string): Promise<{
  message: string
  creditsAdded: string
  creditsAvailable: string
}> {
  return businessClient.post('/api/quota/redeem', { code }).then(r => r.data)
}

export function getCreditsLogs(page = 1, perPage = 20): Promise<{
  logs: Array<{
    id: number
    userId: string
    changeType: string
    creditsChange: string
    creditsBefore: string
    creditsAfter: string
    reason: string | null
    operatorId: string | null
    createdAt: string
  }>
  total: number
  page: number
  pages: number
}> {
  return businessClient.get('/api/quota/credits/logs', { params: { page, per_page: perPage } }).then(r => r.data)
}

export function getQuotaMe(): Promise<{
  planName: string
  planId: number
  creditsTotal: string
  creditsUsed: string
  creditsFrozen: string
  creditsAvailable: string
  dailyRequestsUsed: number
  dailyRequestsLimit: number
  monthlyRequestsUsed: number
  monthlyRequestsLimit: number
  allowedModels: string[]
  expiresAt: string | null
}> {
  return businessClient.get('/api/quota/me').then(r => r.data)
}

// ── 熟悉度 ──

export function getAffinity(): Promise<{
  level: number
  affinityPoints: string
  peakAffinityPoints: string
  nextLevel: number | null
  pointsNeeded: string | null
  progressPct: number
  streakDays: number
  recoveryMode: boolean
  lastCheckinDate: string
  lastActiveDate: string
}> {
  return businessClient.get('/api/affinity/me').then(r => r.data)
}

export function checkIn(): Promise<{
  alreadyCheckedIn: boolean
  affinityEarned: string
  creditsEarned: number
  streakDays: number
  bonusType: string | null
  bonusCredits: number
  recoveryMode: boolean
}> {
  return businessClient.post('/api/affinity/check-in').then(r => r.data)
}

export function getCheckInStatus(): Promise<{
  checkedInToday: boolean
  streakDays: number
  lastCheckinDate: string
}> {
  return businessClient.get('/api/affinity/check-in/status').then(r => r.data)
}

export function getAffinityTasks(): Promise<Array<{
  id: string
  title: string
  description: string
  affinityReward: string
  completed: boolean
}>> {
  return businessClient.get('/api/affinity/tasks').then(r => r.data)
}

export function completeTask(taskId: string): Promise<{
  alreadyCompleted: boolean
  affinityEarned?: string
  recoveryMode?: boolean
}> {
  return businessClient.post(`/api/affinity/tasks/${taskId}/complete`).then(r => r.data)
}

// ── 充值 ──

export function getPurchaseLink(): Promise<{
  token: string
  username: string
  products: Array<{
    name: string
    price: number
    credits: number
    url: string
  }>
  afdianPage: string
}> {
  return businessClient.get('/api/afdian/purchase-link').then(r => r.data)
}
