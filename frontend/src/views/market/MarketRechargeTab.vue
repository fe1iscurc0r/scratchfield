<!-- 模型充值 tab（卷190-B2：从 MarketView.vue 纯搬移，template+style 同进退） -->
<script setup lang="ts">
import { onMounted, onUnmounted, watch } from 'vue'
import { useRecharge } from './composables/useRecharge'

const props = defineProps<{
  activeTab: string
}>()

const {
  rechargeProducts,
  rechargeLoading,
  rechargeError,
  currentCredits,
  redeemInput,
  redeemLoading,
  loadRechargeData,
  disposeRecharge,
  openPurchaseUrl,
  handleRedeem,
} = useRecharge()

onMounted(() => {
  if (props.activeTab === 'recharge')
    loadRechargeData()
})

onUnmounted(disposeRecharge)

watch(() => props.activeTab, (tab) => {
  if (tab === 'recharge')
    loadRechargeData()
})
</script>

<template>
  <section class="recharge-section">
    <div v-if="currentCredits !== null" class="recharge-balance">
      当前余额: <span class="balance-value">{{ currentCredits }}</span> 积分
    </div>

    <div v-if="rechargeLoading" class="recharge-placeholder">加载中...</div>
    <div v-else-if="rechargeError" class="recharge-placeholder recharge-error">{{ rechargeError }}</div>

    <div v-else class="recharge-grid">
      <div
        v-for="product in rechargeProducts" :key="product.name"
        class="recharge-card"
        @click="openPurchaseUrl(product.url)"
      >
        <div class="card-credits">{{ product.credits }}</div>
        <div class="card-unit">积分</div>
        <div class="card-price">{{ product.price }}</div>
      </div>
    </div>

    <div class="recharge-redeem">
      <input
        v-model="redeemInput" class="redeem-input" type="text"
        placeholder="输入兑换码" @keyup.enter="handleRedeem"
      >
      <button class="redeem-btn" :disabled="redeemLoading || !redeemInput.trim()" @click="handleRedeem">
        {{ redeemLoading ? '兑换中...' : '兑换' }}
      </button>
    </div>

    <div class="recharge-tip">点击商品卡片跳转爱发电支付，支付完成后积分自动到账</div>
    <div class="recharge-notice">充值会在一个工作日内到账</div>
  </section>
</template>

<style scoped>
/* ── 模型充值 ── */
.recharge-section {
  flex: 1; display: flex; flex-direction: column; gap: 1.2rem;
  padding: 1rem 0.5rem; overflow-y: auto;
}
.recharge-balance {
  text-align: center; color: rgba(255,255,255,0.6); font-size: 0.85rem;
}
.balance-value { color: #d4af37; font-weight: bold; font-size: 1.1rem; }

.recharge-grid {
  display: grid; grid-template-columns: repeat(auto-fill, minmax(140px, 1fr)); gap: 0.8rem;
}
.recharge-card {
  display: flex; flex-direction: column; align-items: center; gap: 0.3rem;
  padding: 1.2rem 0.8rem; border-radius: 12px;
  background: rgba(255,255,255,0.04); border: 1px solid rgba(255,255,255,0.08);
  cursor: pointer; transition: all 0.2s;
}
.recharge-card:hover {
  background: rgba(212,175,55,0.08); border-color: rgba(212,175,55,0.3);
  transform: translateY(-2px);
}
.recharge-card .card-credits { font-size: 1.8rem; font-weight: bold; color: #d4af37; }
.recharge-card .card-unit { font-size: 0.7rem; color: rgba(255,255,255,0.4); margin-top: -0.2rem; }
.recharge-card .card-price { font-size: 1rem; font-weight: 600; color: rgba(255,255,255,0.9); margin-top: 0.2rem; }

.recharge-redeem { display: flex; gap: 0.5rem; max-width: 360px; margin: 0 auto; }
.redeem-input {
  flex: 1; padding: 0.5rem 0.8rem; border-radius: 8px;
  border: 1px solid rgba(255,255,255,0.12); background: rgba(255,255,255,0.04);
  color: white; font-size: 0.85rem; outline: none;
}
.redeem-input:focus { border-color: rgba(212,175,55,0.4); }
.redeem-btn {
  padding: 0.5rem 1rem; border-radius: 8px; border: none;
  background: rgba(212,175,55,0.2); color: #d4af37;
  font-size: 0.85rem; cursor: pointer; transition: background 0.2s; white-space: nowrap;
}
.redeem-btn:hover:not(:disabled) { background: rgba(212,175,55,0.35); }
.redeem-btn:disabled { opacity: 0.4; cursor: not-allowed; }

.recharge-placeholder { text-align: center; color: rgba(255,255,255,0.4); padding: 2rem; }
.recharge-error { color: rgba(255,100,100,0.7); }
.recharge-tip { text-align: center; color: rgba(255,255,255,0.3); font-size: 0.75rem; }
.recharge-notice { text-align: center; color: rgba(255,255,255,0.2); font-size: 0.7rem; margin-top: 6px; }
</style>
