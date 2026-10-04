// 界面背景购买域：兑换确认弹窗 / 购买 / 重置（卷190-B2：从 MarketView.vue 纯搬移）
import type { Ref } from 'vue'
import { computed, ref } from 'vue'
import { cloudUser, isLoggedIn, refreshUserStats } from '@/composables/useAuth'
import { feedback } from '@/utils/feedback'

interface BackgroundMarketDeps {
  backgroundList: { readonly value: any[] }
  isOwned: (id: string) => boolean
  isActive: (id: string) => boolean
  purchase: (id: string) => boolean
  apply: (id: string) => void
  resetToDefault: () => void
}

export function useBackgroundMarket(deps: BackgroundMarketDeps) {
  const { backgroundList, isOwned, isActive, purchase, apply, resetToDefault } = deps

  const bgConfirmTarget = ref<string | null>(null)
  const bgPurchasing = ref(false)

  function handleBgAction(bgId: string) {
    if (isActive(bgId))
      return
    if (isOwned(bgId)) {
      apply(bgId)
      feedback.success('已应用', '背景已切换')
      return
    }
    bgConfirmTarget.value = bgId
  }

  async function confirmPurchase() {
    const bgId = bgConfirmTarget.value
    if (!bgId || bgPurchasing.value)
      return
    const bg = backgroundList.value.find(b => b.id === bgId)
    if (!bg)
      return

    if (!isLoggedIn.value) {
      feedback.warn('请先登录', '登录后才能兑换背景')
      bgConfirmTarget.value = null
      return
    }

    const userPoints = cloudUser.value?.points ?? 0
    if (userPoints < bg.price) {
      feedback.error('积分不足', `需要 ${bg.price} 积分，当前余额 ${userPoints}`)
      bgConfirmTarget.value = null
      return
    }

    bgPurchasing.value = true
    try {
      const ok = purchase(bgId)
      if (!ok) {
        // 已拥有（确认弹窗竞态兜底）：不重复扣分
        feedback.success('已拥有', `${bg.name} 已在库中`)
        return
      }
      // 扣分为纯前端乐观更新；后台扣分/购买接口暂未接入（purchase 仅改本地拥有列表）
      if (cloudUser.value) {
        cloudUser.value.points = userPoints - bg.price
      }
      apply(bgId)
      feedback.success('兑换成功', `${bg.name} 已解锁并应用`)
      refreshUserStats()
    }
    finally {
      bgPurchasing.value = false
      bgConfirmTarget.value = null
    }
  }

  function cancelPurchase() {
    bgConfirmTarget.value = null
  }

  function handleResetBg() {
    resetToDefault()
    feedback.success('已重置', '已恢复默认向日葵边框')
  }

  const confirmBgItem = computed(() => {
    if (!bgConfirmTarget.value)
      return null
    return backgroundList.value.find(b => b.id === bgConfirmTarget.value) ?? null
  })

  return {
    bgConfirmTarget,
    bgPurchasing,
    handleBgAction,
    confirmPurchase,
    cancelPurchase,
    handleResetBg,
    confirmBgItem,
  }
}

// 壳会传入 Ref 类型（useBackground 的返回是 ref 单例），此处只为类型标注引用
export type { Ref }
