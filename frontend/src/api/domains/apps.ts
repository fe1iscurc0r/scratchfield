/**
 * apps 域 API（卷191-A2 从 core.ts 拆出）。
 *
 * 方法体纯搬运，签名与返回类型零变化。
 */
import type { DomainShape } from './_context'

export const appsMethods = {
  getAppsLaunchStatus(): Promise<{
    neko: { running: boolean, detail: string }
    hamlog: { running: boolean, detail: string }
  }> {
    return this.instance.get('/apps/launch-status')
  },

  launchLocalApp(app: 'neko' | 'hamlog'): Promise<{ status: string, message: string, data: Record<string, unknown> }> {
    return this.instance.post(`/apps/launch/${app}`)
  },
} satisfies DomainShape
