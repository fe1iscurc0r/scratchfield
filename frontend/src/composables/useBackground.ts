import { ref, watch } from 'vue'

export interface BackgroundItem {
  id: string // filename (作为唯一标识)
  name: string // 显示名称（去掉扩展名）
  filename: string // 完整文件名
  price: number // 兑换积分
}

// 默认价格
const DEFAULT_PRICE = 200

const STORAGE_KEY_OWNED = 'lumo-bg-owned'
const STORAGE_KEY_ACTIVE = 'lumo-bg-active'

function loadOwned(): string[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY_OWNED)
    return raw ? JSON.parse(raw) : []
  }
  catch {
    return []
  }
}

function loadActive(): string | null {
  return localStorage.getItem(STORAGE_KEY_ACTIVE) || null
}

const backgroundList = ref<BackgroundItem[]>([])
const ownedBackgrounds = ref<string[]>(loadOwned())
const activeBackground = ref<string | null>(loadActive())

watch(ownedBackgrounds, (ids) => {
  localStorage.setItem(STORAGE_KEY_OWNED, JSON.stringify(ids))
}, { deep: true })

watch(activeBackground, (id) => {
  if (id) {
    localStorage.setItem(STORAGE_KEY_ACTIVE, id)
  }
  else {
    localStorage.removeItem(STORAGE_KEY_ACTIVE)
  }
})

export function useBackground() {
  async function loadBackgrounds() {
    const files: string[] = await window.electronAPI?.backgrounds?.scan() ?? []
    backgroundList.value = files.map(filename => ({
      id: filename,
      name: filename.replace(/\.[^.]+$/, ''),
      filename,
      price: DEFAULT_PRICE,
    }))
  }

  function isOwned(id: string): boolean {
    return ownedBackgrounds.value.includes(id)
  }

  function isActive(id: string): boolean {
    return activeBackground.value === id
  }

  function purchase(id: string): boolean {
    if (ownedBackgrounds.value.includes(id))
      return false
    ownedBackgrounds.value = [...ownedBackgrounds.value, id]
    return true
  }

  function apply(id: string) {
    activeBackground.value = id
  }

  function resetToDefault() {
    activeBackground.value = null
  }

  function getBackgroundUrl(id: string): string {
    return `lumo-bg://${id}`
  }

  function getActiveBackgroundUrl(): string | null {
    if (!activeBackground.value)
      return null
    return getBackgroundUrl(activeBackground.value)
  }

  return {
    backgroundList,
    ownedBackgrounds,
    activeBackground,
    isOwned,
    isActive,
    purchase,
    apply,
    resetToDefault,
    getBackgroundUrl,
    getActiveBackgroundUrl,
    loadBackgrounds,
  }
}
