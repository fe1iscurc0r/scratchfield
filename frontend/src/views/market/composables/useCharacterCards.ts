// 角色注册卡域：加载/卡片宽度计算/展开交互 + 自定义角色表单（卷190-B2：从 MarketView.vue 纯搬移）
import { computed, reactive, ref } from 'vue'
import API from '@/api/core'
import { CONFIG, SYSTEM_PROMPT } from '@/utils/config'
import { feedback } from '@/utils/feedback'
import { applyCustomLive2DModel, upsertCustomLive2DModel } from '@/utils/live2dModels'
import { wasDragging } from './useDragScroll'

export interface CharacterCard {
  id: string
  name: string
  bio: string
  portraitUrl: string
}

export function useCharacterCards() {
  const expandedCard = ref<string | null>(null)
  const charCardRefs: Record<string, HTMLElement> = {}

  // 角色注册卡：从后端 /system/characters 动态加载（卷112「一端注册两端可用」），
  // 不再硬编码——新增角色（目录 + 元数据）刷新即出现在集市。
  const characters = ref<CharacterCard[]>([])

  function characterAssetUrl(name: string, asset: string): string {
    const origin = import.meta.env.DEV ? 'http://localhost:8000' : window.location.origin
    return `${origin}/characters/${encodeURIComponent(name)}/${encodeURIComponent(asset)}`
  }

  async function loadRegisteredCharacters() {
    try {
      const res = await API.listCharacterTemplates()
      characters.value = (res.characters || []).map(c => ({
        id: c.name,
        name: c.name,
        bio: c.bio || '',
        portraitUrl: c.portrait ? characterAssetUrl(c.name, c.portrait) : '',
      }))
    }
    catch (err) {
      console.warn('[Market] 角色注册列表加载失败', err)
    }
  }

  // 立绘统一比例 3:4（宽:高），直接显示完整画布
  // 展开 = cardH × 3/4（原图宽高比）
  // 收缩 = cardH × 2/5
  function computeAllCardWidths() {
    for (const char of characters.value) {
      const el = charCardRefs[char.id]
      if (!el)
        continue
      const h = el.offsetHeight
      if (h <= 0)
        continue
      el.style.setProperty('--collapsed-w', `${Math.round(h * 2 / 5)}px`)
      el.style.setProperty('--expanded-w', `${Math.round(h * 3 / 4)}px`)
    }
    // custom card
    const customEl = charCardRefs.custom
    if (customEl) {
      const ch = customEl.offsetHeight
      if (ch > 0) {
        customEl.style.setProperty('--collapsed-w', `${Math.round(ch * 2 / 5)}px`)
        customEl.style.setProperty('--expanded-w', `${Math.round(ch * 3 / 4)}px`)
      }
    }
  }

  function setCardRef(charId: string, el: any) {
    if (el)
      charCardRefs[charId] = el as HTMLElement
  }

  function toggleCard(id: string) {
    if (wasDragging.value)
      return
    expandedCard.value = expandedCard.value === id ? null : id
  }

  function onSectionClick() {
    if (!wasDragging.value)
      expandedCard.value = null
  }

  function applyCharacter(name: string) {
    CONFIG.value.system.active_character = name
  }

  // ── 自定义角色 ──
  const customChar = reactive({
    name: '',
    modelFiles: [] as File[],
    modelPath: '',
    prompt: '',
    uploading: false,
  })
  const customReady = computed(() =>
    customChar.name.trim() !== '' && customChar.modelFiles.length > 0 && customChar.prompt.trim() !== '',
  )
  const fileInputRef = ref<HTMLInputElement | null>(null)

  function triggerFileInput() {
    fileInputRef.value?.click()
  }

  function onFileChange(e: Event) {
    const input = e.target as HTMLInputElement
    const files = Array.from(input.files ?? [])
    customChar.modelFiles = files
    const modelFiles = files
      .map(file => file.webkitRelativePath || file.name)
      .filter(path => path.toLowerCase().endsWith('.model3.json'))
    customChar.modelPath = modelFiles.length === 1 ? modelFiles[0] ?? '' : ''
  }

  async function applyCustomCharacter() {
    if (!customReady.value || customChar.uploading)
      return
    customChar.uploading = true
    try {
      const res = await API.uploadCustomLive2DModel({
        name: customChar.name.trim(),
        files: customChar.modelFiles,
        modelPath: customChar.modelPath || undefined,
      })
      const savedModel = upsertCustomLive2DModel(res.model)
      applyCustomLive2DModel(savedModel)
      feedback.success('角色已录入', customChar.name.trim())
    }
    catch (e: any) {
      feedback.error('录入失败', e?.response?.data?.detail || e.message)
      return
    }
    finally {
      customChar.uploading = false
    }
    CONFIG.value.system.ai_name = customChar.name
    CONFIG.value.system.active_character = ''
    SYSTEM_PROMPT.value = customChar.prompt
  }

  return {
    expandedCard,
    characters,
    loadRegisteredCharacters,
    computeAllCardWidths,
    setCardRef,
    toggleCard,
    onSectionClick,
    applyCharacter,
    customChar,
    customReady,
    fileInputRef,
    triggerFileInput,
    onFileChange,
    applyCustomCharacter,
  }
}
