// 模型充值域：商品列表 / 余额 / 兑换码（卷190-B2：从 MarketView.vue 纯搬移）
import type { Ref } from 'vue'
import { ref, watch } from 'vue'
import { getCredits, getPurchaseLink, redeemCode } from '@/api/business'
import { refreshUserStats, sessionRestored } from '@/composables/useAuth'
import { feedback } from '@/utils/feedback'

export interface Product { name: string, price: number, credits: number, url: string }

export function useRecharge() {
  const rechargeProducts = ref<Product[]>([])
  const rechargeLoading = ref(false)
  const rechargeError = ref('')
  const rechargeLoaded = ref(false)
  const currentCredits = ref<string | null>(null)
  const redeemInput = ref('')
  const redeemLoading = ref(false)
  let rechargeFallbackTimer: ReturnType<typeof setTimeout> | undefined

  async function loadRechargeData() {
    if (rechargeLoaded.value)
      return

    // 等待会话恢复完成，避免 token 未同步时 businessClient 401
    if (!sessionRestored.value) {
      rechargeLoading.value = true
      rechargeError.value = ''
      const stop = watch(sessionRestored, (ready) => {
        if (ready) {
          stop()
          _doLoadRecharge()
        }
      })
      // 5秒超时兜底（未登录用户不会触发 sessionRestored）
      rechargeFallbackTimer = setTimeout(() => {
        stop()
        if (!rechargeLoaded.value)
          _doLoadRecharge()
      }, 5000)
      return
    }
    _doLoadRecharge()
  }

  async function _doLoadRecharge() {
    if (rechargeLoaded.value)
      return
    rechargeLoading.value = true
    rechargeError.value = ''
    try {
      const [purchaseData, creditsData] = await Promise.all([
        getPurchaseLink(),
        getCredits().catch(() => null),
      ])
      rechargeProducts.value = purchaseData.products || []
      if (creditsData)
        currentCredits.value = creditsData.creditsAvailable
      rechargeLoaded.value = true
    }
    catch (e: any) {
      rechargeError.value = e?.response?.status === 401
        ? '请先登录后使用充值功能'
        : `加载失败: ${e?.response?.data?.detail || e.message}`
    }
    rechargeLoading.value = false
  }

  function disposeRecharge() {
    if (rechargeFallbackTimer) {
      clearTimeout(rechargeFallbackTimer)
      rechargeFallbackTimer = undefined
    }
  }

  function openPurchaseUrl(url: string) {
    window.open(url, '_blank')
  }

  async function handleRedeem() {
    const code = redeemInput.value.trim()
    if (!code)
      return
    redeemLoading.value = true
    try {
      const result = await redeemCode(code)
      feedback.success('兑换成功', `+${result.creditsAdded} 积分`)
      currentCredits.value = result.creditsAvailable
      redeemInput.value = ''
      refreshUserStats()
    }
    catch (e: any) {
      feedback.error('兑换失败', e?.response?.data?.detail || e.message)
    }
    redeemLoading.value = false
  }

  return {
    rechargeProducts,
    rechargeLoading,
    rechargeError,
    rechargeLoaded,
    currentCredits,
    redeemInput,
    redeemLoading,
    loadRechargeData,
    disposeRecharge,
    openPurchaseUrl,
    handleRedeem,
  }
}

export type { Ref }
