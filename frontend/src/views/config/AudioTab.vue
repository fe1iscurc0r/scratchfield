<script setup lang="ts">
/**
 * 音画配置设置页（卷181-D：从 ConfigView 巨石搬移，纯搬移不重构逻辑）。
 *
 * 状态来源：CONFIG/DEFAULT_CONFIG/MODELS/DEFAULT_MODEL/SYSTEM_PROMPT/backendConnected
 * （@/utils/config 全局 ref）+ useAudio/useAuth/useVersionCheck + live2dController/live2dModels；
 * 原先定义在 ConfigView 的 characterLocked/characterLockedHint/selectedModel/onModelChange/
 * ssaaInputRef/recoverUiConfig/askRecoverUiConfig/doRecoverUiConfig/confirmRecoverVisible/
 * accordionTerminal/柏斯阔落 watch/autoLaunchEnabled/isElectron/onAutoLaunchChange/
 * syncCharacterProfile/customLive2d 系列/handleCheckUpdate/toggleFloatingMode/
 * 删除自定义模型 ConfirmDialog 随块搬入本组件（这些符号只服务本块）。
 */
import type { CustomLive2DModel } from '@/api/core'
import { useStorage } from '@vueuse/core'
import { Accordion, Button, ConfirmDialog, Divider, InputNumber, InputText, Select, Slider, Textarea, ToggleSwitch } from 'primevue'
import { computed, onMounted, ref, useTemplateRef, watch } from 'vue'
import { useRouter } from 'vue-router'
import API from '@/api/core'
import ConfigGroup from '@/components/ConfigGroup.vue'
import ConfigItem from '@/components/ConfigItem.vue'
import { audioSettings, effectFileOptions, wakeVoiceOptions } from '@/composables/useAudio'
import { cloudUser } from '@/composables/useAuth'
import { checkForUpdate } from '@/composables/useVersionCheck'
import { backendConnected, CONFIG, DEFAULT_CONFIG, DEFAULT_MODEL, MODELS, SYSTEM_PROMPT } from '@/utils/config'
import { feedback } from '@/utils/feedback'
import { trackingCalibration } from '@/utils/live2dController'
import { applyCustomLive2DModel, applyLive2DModel, toCustomLive2DModelConfig, upsertCustomLive2DModel } from '@/utils/live2dModels'

const accordionTerminal = useStorage('accordion-config', [])

// ── 终端 Tab 逻辑（原 ConfigView） ──
const characterLocked = computed(() => !!CONFIG.value.system.active_character)
const characterLockedHint = computed(() =>
  characterLocked.value
    ? `由角色「${CONFIG.value.system.active_character}.json」管理，不可直接修改`
    : undefined,
)

const selectedModel = computed(() => Object.entries(MODELS).find(([_, model]) => {
  return model.source === CONFIG.value.web_live2d.model.source
})?.[0] ?? DEFAULT_MODEL)

function onModelChange(value: keyof typeof MODELS) {
  applyLive2DModel({ ...MODELS[value] })
  CONFIG.value.system.active_character = ''
}

const ssaaInputRef = useTemplateRef<{
  updateModel: (event: null, value: number) => void
}>('ssaaInputRef')

function recoverUiConfig() {
  if (!characterLocked.value) {
    CONFIG.value.system.ai_name = DEFAULT_CONFIG.system.ai_name
    onModelChange(DEFAULT_MODEL)
  }
  CONFIG.value.ui.user_name = DEFAULT_CONFIG.ui.user_name
  ssaaInputRef.value?.updateModel(null, DEFAULT_CONFIG.web_live2d.ssaa)
}

// ── 破坏性操作二次确认（卷150 任务D：统一 ConfirmDialog） ──
const confirmRecoverVisible = ref(false)

function askRecoverUiConfig() {
  confirmRecoverVisible.value = true
}

function doRecoverUiConfig() {
  confirmRecoverVisible.value = false
  recoverUiConfig()
}

const configRouter = useRouter()

let _previousUserName = CONFIG.value.ui.user_name
watch(() => CONFIG.value.ui.user_name, (newVal) => {
  if (newVal.includes('柏斯阔落')) {
    feedback.success('系统提示', '此名词不可用')
    CONFIG.value.ui.user_name = '用户'
  }
  else {
    _previousUserName = newVal
  }
})

const autoLaunchEnabled = ref(false)
const isElectron = !!window.electronAPI

/**
 * 角色档案一致性：昵称（CONFIG.system.ai_name）必须与当前启用角色同源。
 * 切换角色（集市/干员）只改 active_character 时，会出现「角色名称是旧角色、
 * 系统提示词是新角色」的错位——这里按当前角色回填昵称。
 */
async function syncCharacterProfile() {
  try {
    const res = await API.getActiveCharacter()
    const aiName = String(res?.character?.ai_name || '').trim()
    if (aiName && CONFIG.value.system.ai_name !== aiName) {
      CONFIG.value.system.ai_name = aiName
    }
  }
  catch {
    // 后端未就绪时忽略：档案面板保持原值
  }
}

async function onAutoLaunchChange(value: boolean) {
  if (isElectron) {
    await window.electronAPI!.autoLaunch.set(value)
    autoLaunchEnabled.value = value
  }
}

const checkingUpdate = ref(false)
const customLive2dModels = computed(() => CONFIG.value.web_live2d.custom_models)
const customLive2dName = ref('')
const customLive2dFiles = ref<File[]>([])
const customLive2dModelPath = ref('')
const customLive2dUploading = ref(false)
const customLive2dLoading = ref(false)
const customLive2dFileInputRef = ref<HTMLInputElement | null>(null)
const customLive2dReady = computed(() =>
  customLive2dName.value.trim() !== '' && customLive2dFiles.value.length > 0,
)

function formatFileSize(bytes: number) {
  if (!Number.isFinite(bytes) || bytes <= 0)
    return '0 KB'
  if (bytes < 1024 * 1024)
    return `${Math.max(1, Math.round(bytes / 1024))} KB`
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`
}

function getFileRelativePath(file: File) {
  return file.webkitRelativePath || file.name
}

function pickCustomLive2dFolder() {
  customLive2dFileInputRef.value?.click()
}

function handleCustomLive2dFilesChange(event: Event) {
  const input = event.target as HTMLInputElement
  const files = Array.from(input.files ?? [])
  customLive2dFiles.value = files
  const modelFiles = files
    .map(getFileRelativePath)
    .filter(path => path.toLowerCase().endsWith('.model3.json'))
  customLive2dModelPath.value = modelFiles.length === 1 ? modelFiles[0] ?? '' : ''
  if (!customLive2dName.value.trim() && customLive2dModelPath.value) {
    const parts = customLive2dModelPath.value.split('/')
    customLive2dName.value = parts.length > 1
      ? parts[parts.length - 2] ?? ''
      : parts[0]?.replace(/\.model3\.json$/i, '') ?? ''
  }
}

async function loadCustomLive2dModels() {
  if (!backendConnected.value || customLive2dLoading.value)
    return
  customLive2dLoading.value = true
  try {
    const res = await API.listCustomLive2DModels()
    CONFIG.value.web_live2d.custom_models = (res.models || []).map(toCustomLive2DModelConfig)
  }
  catch {
    // 后端旧版本或暂不可用时不影响其他设置
  }
  finally {
    customLive2dLoading.value = false
  }
}

watch(backendConnected, (connected) => {
  if (connected) {
    loadCustomLive2dModels()
  }
}, { immediate: true })

async function uploadCustomLive2dModel() {
  if (!customLive2dReady.value || customLive2dUploading.value)
    return
  customLive2dUploading.value = true
  try {
    const res = await API.uploadCustomLive2DModel({
      name: customLive2dName.value.trim(),
      files: customLive2dFiles.value,
      modelPath: customLive2dModelPath.value || undefined,
    })
    const savedModel = upsertCustomLive2DModel(res.model)
    applyCustomLive2DModel(savedModel)
    customLive2dName.value = ''
    customLive2dFiles.value = []
    customLive2dModelPath.value = ''
    if (customLive2dFileInputRef.value) {
      customLive2dFileInputRef.value.value = ''
    }
    feedback.success('Live2D 已应用', res.model.name)
  }
  catch (e: any) {
    feedback.error('上传失败', e?.response?.data?.detail || e.message)
  }
  finally {
    customLive2dUploading.value = false
  }
}

// ── 删除自定义模型二次确认（卷150 任务D：列出影响范围） ──
const confirmModelDeleteVisible = ref(false)
const pendingModelDelete = ref<CustomLive2DModel | typeof CONFIG.value.web_live2d.custom_models[number] | null>(null)

function askDeleteCustomLive2dModel(model: CustomLive2DModel | typeof CONFIG.value.web_live2d.custom_models[number]) {
  pendingModelDelete.value = model
  confirmModelDeleteVisible.value = true
}

async function doDeleteCustomLive2dModel() {
  const model = pendingModelDelete.value
  if (!model)
    return
  confirmModelDeleteVisible.value = false
  try {
    await API.deleteCustomLive2DModel(model.id)
    CONFIG.value.web_live2d.custom_models = CONFIG.value.web_live2d.custom_models.filter(item => item.id !== model.id)
    if (CONFIG.value.web_live2d.model.source === model.source) {
      applyLive2DModel({ ...MODELS[DEFAULT_MODEL] })
    }
    feedback.success('已删除', model.name)
  }
  catch (e: any) {
    feedback.error('删除失败', e?.response?.data?.detail || e.message)
  }
  finally {
    pendingModelDelete.value = null
  }
}

async function handleCheckUpdate() {
  if (checkingUpdate.value)
    return
  checkingUpdate.value = true
  try {
    const hasUpdate = await checkForUpdate()
    if (!hasUpdate) {
      feedback.success('已是最新版本', `当前版本 v${CONFIG.value.system.version}`)
    }
  }
  catch {
    feedback.error('检查更新失败', '请稍后重试')
  }
  finally {
    checkingUpdate.value = false
  }
}

function toggleFloatingMode(enabled: boolean) {
  CONFIG.value.floating.enabled = enabled
  if (!isElectron)
    return
  if (enabled) {
    window.electronAPI?.floating.enter()
  }
  else {
    window.electronAPI?.floating.exit()
  }
}

onMounted(async () => {
  if (isElectron) {
    autoLaunchEnabled.value = await window.electronAPI!.autoLaunch.get()
  }
  syncCharacterProfile()
})
</script>

<template>
  <Accordion :value="accordionTerminal" class="pb-6" multiple>
    <ConfigGroup value="ui">
      <template #header>
        <div class="w-full flex justify-between items-center -my-1.5">
          <span>显示设置</span>
          <Button size="small" label="恢复默认" @click.stop="askRecoverUiConfig" />
        </div>
      </template>
      <div class="grid gap-4">
        <ConfigItem name="用户昵称" description="聊天窗口显示的用户昵称">
          <InputText v-model="CONFIG.ui.user_name" />
        </ConfigItem>
        <Divider class="m-1!" />
        <ConfigItem layout="column" name="Live2D 模型" description="上传整套 Cubism 模型目录，或从已保存模型中切换">
          <div class="live2d-model-panel">
            <div class="builtin-live2d-row">
              <Select
                :options="Object.keys(MODELS)"
                :model-value="selectedModel"
                :disabled="characterLocked"
                @change="(event) => onModelChange(event.value)"
              />
              <Button
                size="small"
                label="角色注册"
                @click="configRouter.push('/market?tab=memory-skin')"
              />
            </div>
            <div v-if="characterLocked" class="live2d-lock-hint">
              {{ characterLockedHint }}
            </div>

            <div class="custom-live2d-uploader">
              <input
                ref="customLive2dFileInputRef"
                type="file"
                webkitdirectory
                directory
                multiple
                hidden
                @change="handleCustomLive2dFilesChange"
              >
              <InputText
                v-model="customLive2dName"
                class="min-w-0"
                placeholder="自定义模型名称"
              />
              <Button
                size="small"
                outlined
                :label="customLive2dFiles.length ? `${customLive2dFiles.length} 个文件` : '选择目录'"
                @click="pickCustomLive2dFolder"
              />
              <Button
                size="small"
                label="上传并应用"
                :disabled="!customLive2dReady"
                :loading="customLive2dUploading"
                @click="uploadCustomLive2dModel"
              />
            </div>
            <div v-if="customLive2dModelPath" class="live2d-path-hint">
              入口文件：{{ customLive2dModelPath }}
            </div>

            <div class="custom-live2d-list">
              <div v-if="customLive2dLoading" class="custom-live2d-empty">
                正在读取模型列表...
              </div>
              <div v-else-if="customLive2dModels.length === 0" class="custom-live2d-empty">
                暂无自定义 Live2D 模型
              </div>
              <template v-else>
                <div
                  v-for="model in customLive2dModels"
                  :key="model.id"
                  class="custom-live2d-item"
                  :class="{ active: CONFIG.web_live2d.model.source === model.source }"
                >
                  <div class="custom-live2d-meta">
                    <div class="custom-live2d-name">{{ model.name }}</div>
                    <div class="custom-live2d-detail">
                      {{ model.file_count }} 个文件 · {{ formatFileSize(model.total_bytes) }}
                    </div>
                  </div>
                  <div class="custom-live2d-actions">
                    <Button
                      size="small"
                      :label="CONFIG.web_live2d.model.source === model.source ? '使用中' : '应用'"
                      :disabled="CONFIG.web_live2d.model.source === model.source"
                      @click="applyCustomLive2DModel(model)"
                    />
                    <Button
                      size="small"
                      severity="danger"
                      outlined
                      label="删除"
                      @click="askDeleteCustomLive2dModel(model)"
                    />
                  </div>
                </div>
              </template>
            </div>
          </div>
        </ConfigItem>
        <Divider class="m-1!" />
        <ConfigItem name="Live2D 模型位置">
          <div class="flex flex-col items-center justify-evenly">
            <label v-for="direction in ['x', 'y'] as const" :key="direction" class="w-full flex items-center">
              <div class="capitalize w-0 -translate-x-4">{{ direction }}</div>
              <Slider
                v-model="CONFIG.web_live2d.model[direction]"
                class="w-full" :min="-2" :max="2" :step="1e-3"
              />
            </label>
          </div>
        </ConfigItem>
        <ConfigItem name="Live2D 模型缩放">
          <Slider v-model="CONFIG.web_live2d.model.size" :min="0" :max="9000" />
        </ConfigItem>
        <ConfigItem name="Live2D 模型超采样倍数">
          <InputNumber
            ref="ssaaInputRef"
            v-model="CONFIG.web_live2d.ssaa"
            :min="1" :max="4" show-buttons
          />
        </ConfigItem>
        <Divider class="m-1!" />
        <ConfigItem name="视角校准" description="调整追踪参考点到模型面部位置，开启准星后拖动滑块使红色十字对准面部">
          <div class="flex items-center gap-3 w-full">
            <Slider
              v-model="CONFIG.web_live2d.face_y_ratio"
              class="flex-1" :min="0" :max="1" :step="0.01"
            />
            <Button
              :label="trackingCalibration ? '关闭准星' : '显示准星'"
              :severity="trackingCalibration ? 'danger' : 'secondary'"
              size="small"
              @click="trackingCalibration = !trackingCalibration"
            />
          </div>
        </ConfigItem>
        <ConfigItem name="视角追踪延迟" description="按住鼠标超过该时间(毫秒)后才开始视角追踪，0=点击即追踪">
          <InputNumber
            :model-value="CONFIG.web_live2d.tracking_hold_delay_ms ?? 100"
            :min="0" :max="5000" :step="100"
            show-buttons
            @update:model-value="(v: number | null) => { CONFIG.web_live2d.tracking_hold_delay_ms = v ?? 100 }"
          />
        </ConfigItem>
        <Divider class="m-1!" />
        <ConfigItem v-if="isElectron" name="悬浮球模式" description="启用后窗口变为可拖拽的悬浮球，点击展开聊天面板">
          <ToggleSwitch
            :model-value="CONFIG.floating.enabled"
            @update:model-value="toggleFloatingMode"
          />
        </ConfigItem>
      </div>
    </ConfigGroup>
    <ConfigGroup value="character">
      <template #header>
        <div class="w-full flex justify-between items-center -my-1.5">
          <span>角色档案</span>
          <Button size="small" label="切换角色" @click.stop="configRouter.push('/market?tab=memory-skin')" />
        </div>
      </template>
      <div class="grid gap-4">
        <ConfigItem name="角色名称" :description="characterLockedHint ?? '聊天窗口显示的 AI 昵称'">
          <InputText v-model="CONFIG.system.ai_name" :disabled="characterLocked" />
        </ConfigItem>
        <ConfigItem name="L2D 模型" :description="characterLocked ? characterLockedHint : '在上方 Live2D 模型入口切换内置或自定义模型'">
          <span class="live2d-source-preview">
            {{ CONFIG.web_live2d.model.source }}
          </span>
        </ConfigItem>
        <ConfigItem
          layout="column"
          name="系统提示词"
          :description="characterLocked ? characterLockedHint : '编辑对话风格提示词，影响AI的回复风格和语言特点'"
        >
          <div class="flex flex-col gap-1 mt-3">
            <Textarea v-model="SYSTEM_PROMPT" rows="10" class="resize-none" :disabled="characterLocked" />
          </div>
        </ConfigItem>
      </div>
    </ConfigGroup>
    <ConfigGroup value="audio">
      <template #header>
        <div class="w-full flex justify-between items-center -my-1.5">
          <span>音乐设置</span>
        </div>
      </template>
      <div class="grid gap-4">
        <ConfigItem name="背景音乐" description="启用/关闭背景音乐">
          <ToggleSwitch v-model="audioSettings.bgmEnabled" />
        </ConfigItem>
        <ConfigItem name="音乐音量">
          <Slider v-model="audioSettings.bgmVolume" :min="0" :max="1" :step="0.01" />
        </ConfigItem>
        <Divider class="m-1!" />
        <ConfigItem name="点击音效" description="启用/关闭UI交互音效">
          <ToggleSwitch v-model="audioSettings.effectEnabled" />
        </ConfigItem>
        <ConfigItem name="音效音量">
          <Slider v-model="audioSettings.effectVolume" :min="0" :max="1" :step="0.01" />
        </ConfigItem>
        <ConfigItem name="音效文件" description="选择点击音效">
          <Select v-model="audioSettings.clickEffect" :options="effectFileOptions" />
        </ConfigItem>
        <Divider class="m-1!" />
        <ConfigItem name="唤醒语音" description="点击唤醒时播放的语音包">
          <Select v-model="audioSettings.wakeVoice" :options="wakeVoiceOptions" />
        </ConfigItem>
      </div>
    </ConfigGroup>
    <ConfigGroup value="system">
      <template #header>
        <div class="flex w-full justify-between">
          <span>系统设置</span>
          <span>v{{ CONFIG.system.version }}</span>
        </div>
      </template>
      <div class="grid gap-4">
        <ConfigItem name="当前账号">
          <div v-if="cloudUser" class="flex items-center gap-3">
            <div class="w-8 h-8 rounded-full bg-amber-600/60 flex items-center justify-center text-white text-sm font-bold shrink-0">
              {{ cloudUser.username.charAt(0).toUpperCase() }}
            </div>
            <span class="text-white/80">{{ cloudUser.username }}</span>
          </div>
          <span v-else class="text-white/40">未登录</span>
        </ConfigItem>
        <ConfigItem v-if="isElectron" name="开机自启动" description="系统启动时自动运行应用">
          <ToggleSwitch :model-value="autoLaunchEnabled" @update:model-value="onAutoLaunchChange" />
        </ConfigItem>
      </div>
    </ConfigGroup>
  </Accordion>
  <div class="terminal-footer">
    <div class="terminal-footer-version">
      当前版本 v{{ CONFIG.system.version }}
    </div>
    <Button
      size="small"
      outlined
      :loading="checkingUpdate"
      label="检查更新"
      @click="handleCheckUpdate"
    />
  </div>

  <!-- 删除自定义模型确认（卷150 任务D：列出影响范围） -->
  <ConfirmDialog v-model:visible="confirmModelDeleteVisible" @confirm="doDeleteCustomLive2dModel">
    <template #message>
      确认删除自定义模型「{{ pendingModelDelete?.name }}」？
      <br>若当前正在使用将回退到默认模型，此操作不可恢复。
    </template>
  </ConfirmDialog>

  <!-- 恢复默认确认（卷150 任务D：重置走 ConfirmDialog） -->
  <ConfirmDialog v-model:visible="confirmRecoverVisible" @confirm="doRecoverUiConfig">
    <template #message>
      确认恢复默认界面配置？
      <br>角色名、用户名与 Live2D 渲染精度将被重置。
    </template>
  </ConfirmDialog>
</template>

<style scoped>
.live2d-model-panel {
  display: grid;
  gap: 0.75rem;
  margin-top: 0.75rem;
}

.builtin-live2d-row,
.custom-live2d-uploader,
.custom-live2d-actions {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  min-width: 0;
}

.custom-live2d-uploader {
  flex-wrap: wrap;
}

.live2d-lock-hint,
.live2d-path-hint,
.custom-live2d-empty,
.live2d-source-preview {
  color: rgba(255, 255, 255, 0.48);
  font-size: 12px;
  line-height: 1.6;
  overflow-wrap: anywhere;
}

.custom-live2d-list {
  display: grid;
  gap: 0.5rem;
}

.custom-live2d-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.75rem;
  min-width: 0;
  padding: 0.65rem 0.75rem;
  border: 1px solid rgba(255, 255, 255, 0.1);
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.04);
}

.custom-live2d-item.active {
  border-color: rgba(74, 222, 128, 0.42);
  background: rgba(74, 222, 128, 0.08);
}

.custom-live2d-meta {
  min-width: 0;
}

.custom-live2d-name {
  color: rgba(255, 255, 255, 0.88);
  font-weight: 600;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.custom-live2d-detail {
  margin-top: 0.15rem;
  color: rgba(255, 255, 255, 0.42);
  font-size: 12px;
}

.terminal-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 1rem;
  margin-top: 0.25rem;
  padding: 0.9rem 0.25rem 0;
  border-top: 1px solid rgba(255, 255, 255, 0.08);
}

.terminal-footer-version {
  color: rgba(255, 255, 255, 0.5);
  font-size: 12px;
}
</style>
