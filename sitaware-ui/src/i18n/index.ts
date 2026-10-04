import { createI18n } from 'vue-i18n'
import zh from './zh'
import en from './en'

const saved = (typeof localStorage !== 'undefined' && localStorage.getItem('sitaware-lang')) || 'zh'

export const i18n = createI18n({
  legacy: false,
  locale: saved,
  fallbackLocale: 'zh',
  messages: { zh, en },
})

export function setLang(locale: string) {
  i18n.global.locale.value = locale as any
  localStorage.setItem('sitaware-lang', locale)
}
