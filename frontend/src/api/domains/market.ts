import type { DomainShape } from './_context'
/**
 * market 域 API（卷191-A2 从 core.ts 拆出）。
 *
 * 方法体纯搬运，签名与返回类型零变化。
 */
import type { MarketItem, OpenClawStatus } from './_types'

export const marketMethods = {
  getMarketItems(): Promise<{
    status: 'success'
    openclaw: OpenClawStatus
    items: MarketItem[]
  }> {
    return this.instance.get('/openclaw/market/items')
  },

  installMarketItem(itemId: string): Promise<{
    status: 'success'
    message: string
    item: MarketItem
    openclaw: OpenClawStatus
  }> {
    return this.instance.post(`/openclaw/market/items/${itemId}/install`, {}, {
      timeout: 5 * 60 * 1000,
    })
  },
} satisfies DomainShape
