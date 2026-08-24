export interface ParsedQqBindingTarget {
  raw: string
  normalizedQq: string
  normalizedEmail: string
  isEmpty: boolean
  isValid: boolean
  isAliasEmail: boolean
  errorMessage: string
}

const QQ_NUMBER_RE = /^\d+$/
const QQ_DIGIT_EMAIL_RE = /^(\d+)@qq\.com$/i
const QQ_ANY_EMAIL_RE = /^[^@\s]+@qq\.com$/i

export function parseQqBindingTarget(rawValue: string): ParsedQqBindingTarget {
  const raw = rawValue.trim()
  if (!raw) {
    return {
      raw: '',
      normalizedQq: '',
      normalizedEmail: '',
      isEmpty: true,
      isValid: false,
      isAliasEmail: false,
      errorMessage: '',
    }
  }

  if (QQ_NUMBER_RE.test(raw)) {
    return {
      raw,
      normalizedQq: raw,
      normalizedEmail: `${raw}@qq.com`,
      isEmpty: false,
      isValid: true,
      isAliasEmail: false,
      errorMessage: '',
    }
  }

  const digitEmailMatch = raw.match(QQ_DIGIT_EMAIL_RE)
  if (digitEmailMatch) {
    const qq = digitEmailMatch[1] || ''
    return {
      raw,
      normalizedQq: qq,
      normalizedEmail: `${qq}@qq.com`,
      isEmpty: false,
      isValid: true,
      isAliasEmail: false,
      errorMessage: '',
    }
  }

  if (QQ_ANY_EMAIL_RE.test(raw)) {
    return {
      raw,
      normalizedQq: '',
      normalizedEmail: '',
      isEmpty: false,
      isValid: false,
      isAliasEmail: true,
      errorMessage: 'QQ 邮箱不支持别名，请填写纯数字 QQ 号或纯数字@qq.com。',
    }
  }

  return {
    raw,
    normalizedQq: '',
    normalizedEmail: '',
    isEmpty: false,
    isValid: false,
    isAliasEmail: false,
    errorMessage: '请输入纯数字 QQ 号或纯数字@qq.com。',
  }
}

export function hasQqEmailVerificationCode(rawValue: string): boolean {
  return rawValue.trim().length > 0
}
