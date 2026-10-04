/**
 * auth 域 API（卷191-A2 从 core.ts 拆出）。
 *
 * 方法体纯搬运，签名与返回类型零变化。
 */
import type { DomainShape } from './_context'

export const authMethods = {
  authLogin(username: string, password: string, captchaId?: string, captchaAnswer?: string): Promise<{
    success: boolean
    user: { username: string, sub?: string } | null
    accessToken: string
    memoryUrl?: string
  }> {
    return this.instance.post('/auth/login', { username, password, captcha_id: captchaId, captcha_answer: captchaAnswer })
  },

  authMe(): Promise<{ user: { username: string, sub?: string }, memoryUrl?: string, accessToken?: string }> {
    return this.instance.get('/auth/me')
  },

  authLogout(): Promise<{ success: boolean }> {
    return this.instance.post('/auth/logout')
  },

  authRegister(username: string, email: string, password: string, verificationCode: string): Promise<{
    success: boolean
    user?: { username: string, email: string, sub?: string }
    accessToken?: string
  }> {
    return this.instance.post('/auth/register', { username, email, password, verification_code: verificationCode })
  },

  authSendVerification(email: string, username: string, captchaId?: string, captchaAnswer?: string): Promise<{
    success: boolean
    message: string
  }> {
    return this.instance.post('/auth/send-verification', { email, username, captcha_id: captchaId, captcha_answer: captchaAnswer })
  },

  authSendQqVerification(email: string, captchaId?: string, captchaAnswer?: string): Promise<{
    success: boolean
    message: string
  }> {
    return this.instance.post('/auth/send-qq-verification', { email, captcha_id: captchaId, captcha_answer: captchaAnswer })
  },

  authBindQqEmail(qqEmail: string, verificationCode: string): Promise<{
    ok: boolean
    message: string
    binding?: {
      userId: string
      username: string
      qqEmail: string
      qqNumber: string
    }
  }> {
    return this.instance.post('/auth/qq-email', { qq_email: qqEmail, verification_code: verificationCode })
  },

  authGetQqEmailBinding(): Promise<{
    ok: boolean
    binding: null | {
      userId: string
      username: string
      qqEmail: string
      qqNumber: string
    }
    qqEmail: string | null
    qqNumber: string | null
    currentAccountQqEmail: string | null
    currentAccountQqNumber: string | null
    currentAccountEmailVerified: boolean
    directBindAvailable: boolean
  }> {
    return this.instance.get('/auth/qq-email')
  },

  testQqNotification(qqUserId: string, message?: string): Promise<{
    status: 'success'
    deliveryStatus: string
  }> {
    return this.instance.post('/system/notifications/qq/test', { qq_user_id: qqUserId, message })
  },

  authGetCaptcha(format?: 'image'): Promise<{
    captchaId: string
    question?: string
    imageData?: string
    mimeType?: string
    answerLength?: number
    type?: 'image' | 'math'
    legacyCompatible?: boolean
  }> {
    const params = format ? { format } : undefined
    return this.instance.get('/auth/captcha', { params })
  },
} satisfies DomainShape
