import type { ComputedRef, Ref } from 'vue'
import type { RouteLocationNormalizedLoaded } from 'vue-router'
import { useWindowSize } from '@vueuse/core'
import { computed, defineAsyncComponent, ref, watch } from 'vue'
import { CONFIG } from '@/utils/config'
import { clearExpression, setExpression } from '@/utils/live2dController'
import { ensureLive2dCoreLoaded } from '@/utils/live2dCoreLoader'
import { messageViewExpanded } from '@/utils/uiState'

/**
 * Live2D 渲染舞台族（工单204 任务三 · App.vue 抽取步骤⑥，本任务最后一项）
 *
 * 依据依赖图 docs/app-vue-state-graph-2026-10-07.md §三 末行「渲染/peek 变换 ~16 个」。
 * 按精确计数（tools/measure_stage.py，区分脚本侧/模板侧）定案本族拥有 **20 个符号**：
 *   Live2dModel / width / height / scale / live2dRenderKey / modelReady /
 *   live2dTransform / live2dTransformOrigin / live2dTransition / initialPositionSet /
 *   onModelReady / live2dShouldShow / isChatPeekMode / PEEK_EXPRESSION / applyPeekExpression /
 *   live2dPeekShellStyle / live2dModelX / live2dModelY / live2dCombinedTransform /
 *   live2dCombinedTransition / live2dPeekShellTransition
 * 外加随族迁入的两个 watch（effectiveLive2dSource → live2dRenderKey；isChatPeekMode → 表情）。
 *
 * 三处对依赖图原表的校正（均为实测，非推断）：
 * 1. `isChatPeekMode` 原表倾向「留在 App.vue」。实测其 6 个消费点
 *    （onModelReady / live2dPeekShellStyle / live2dModelX / live2dModelY /
 *      live2dPeekShellTransition / watch(isChatPeekMode)）**全部**落在本族内部，
 *    模板侧引用数为 0 ⇒ 随族迁入才是内聚边界。其 5 个依赖中 `messageViewExpanded`
 *    是模块级共享 ref（@/utils/uiState），按步骤④ 先例直接 import；
 *    其余 4 个（splashVisible / showMainContent / currentRoute / isFloatingMode）作参数注入。
 *    （`isChatPeekMode` 无需导出：App.vue 侧零引用。）
 * 2. `width` / `height` / `scale` 原表未单列。实测三者**只被模板消费**
 *    （width/height 脚本侧仅 useWindowSize 解构；scale 脚本侧仅声明，另两处命中
 *      分别是中文注释与 CSS 字符串字面量）⇒ 连同 `useWindowSize()` 调用一并迁入。
 * 3. `live2dRenderKey` 在原 useLive2dSource.ts 文件头被记为「属本族边界、其 watch 仍留在
 *    App.vue」。本步骤把该 watch 一并迁入（它唯一职责就是自增本族的 renderKey）。
 *
 * 另有一处**声明顺序**调整（属 lint 驱动，非边界问题）：`isChatPeekMode` 在原 App.vue 里声明于
 * `onModelReady` **之后**，靠「`<script>` + `<script setup>` 双脚本块结构」躲过了
 * `ts/no-use-before-define`（实测：同一段代码删掉前置 `<script>` 块即报错 ⇒ App.vue 属该规则的盲区），
 * 但本文件是纯 .ts，实测会被抓到 ⇒ 把 peek 判定 / PEEK_EXPRESSION / applyPeekExpression 整体
 * 提前到 `onModelReady` 之前。**仅调整声明顺序，逻辑零改动**，与步骤③ useLive2dSource 同一处理。
 *
 * 依赖（8 个参数，全部作参数注入，避免重复实例化）：
 *   splashVisible / showMainContent（步骤⑤ useAppSplash）
 *   currentRoute / isFloatingMode（仍留在 App.vue）
 *   effectiveLive2dSource / activeLive2dSource / persistStartupLive2dSource（步骤③ useLive2dSource）
 *   notifyModelReady（useStartupProgress）
 * `CONFIG` 为模块级 ref，直接 import（App.vue 自身仍在 onMounted 里读 CONFIG.value.floating）。
 *
 * 写穿透（与步骤⑤ 同型）：`enterMainContent`（18 依赖的编排汇聚点，必须留在 App.vue）
 * 会写 `live2dTransition` / `live2dTransform` / `live2dTransformOrigin` / `initialPositionSet`。
 * 其中 `initialPositionSet` 原为 setup 作用域 `let`，跨边界写穿透要求它升级为 `ref`
 * （语句顺序与语义零变化）。若后续希望把它收回内部，可改为暴露 resetInitialPosition()。
 *
 * 须在 setup() 内**同步**调用，且调用点必须晚于步骤⑤（本处读取 splashVisible / showMainContent）。
 */
export interface Live2dStageDeps {
  /** 启动闪屏可见性（步骤⑤）：splash 阶段面部居中判据 + 首帧不透明度判据 */
  splashVisible: Ref<boolean>
  /** 主内容是否已显示（步骤⑤）：peek 模式判据之一 + peek watch 守卫 */
  showMainContent: Ref<boolean>
  /** 当前路由：peek 模式判据（/chat 前缀） */
  currentRoute: RouteLocationNormalizedLoaded
  /** 悬浮球模式：peek 模式判据（悬浮球下不 peek） */
  isFloatingMode: ComputedRef<boolean>
  /** 生效 Live2D 源（步骤③）：变化即换 key 重挂载模型 */
  effectiveLive2dSource: ComputedRef<string>
  /** 当前活跃源（步骤③）：model-ready 时回写启动缓存 */
  activeLive2dSource: Ref<string>
  /** 启动缓存回写（步骤③） */
  persistStartupLive2dSource: (source?: string | null) => void
  /** 模型首帧就绪通知（useStartupProgress）：驱动启动进度条 */
  notifyModelReady: () => void
}

export function useLive2dStage({
  splashVisible,
  showMainContent,
  currentRoute,
  isFloatingMode,
  effectiveLive2dSource,
  activeLive2dSource,
  persistStartupLive2dSource,
  notifyModelReady,
}: Live2dStageDeps) {
  // Live2D 链（pixi.js + pixi-live2d-display，数百 KB）改异步组件，
  // 首屏入口 chunk 不再打包 WebGL 栈，按需加载。
  // 顺序硬约束：pixi-live2d-display 在**模块顶层**就有
  // `if (!window.Live2DCubismCore) throw new Error('Could not find Cubism 4 runtime...')`，
  // 所以核心库必须在 import 之前注入，否则整个 vendor-pixi chunk 一被 import 就抛错，
  // 异步组件永远挂载不上 —— 表现就是 Live2D 主体消失（只剩背景光斑）。
  const Live2dModel = defineAsyncComponent(async () => {
    await ensureLive2dCoreLoaded()
    return import('@/components/Live2dModel.vue')
  })

  const { width, height } = useWindowSize()
  const scale = computed(() => height.value / (10000 - CONFIG.value.web_live2d.model.size))
  const live2dRenderKey = ref(0)

  // 首帧就绪标志（模板经 :model-ready 传给 SplashScreen）
  const modelReady = ref(false)

  // Live2D 居中/过渡控制
  const live2dTransform = ref('')
  const live2dTransformOrigin = ref('')
  const live2dTransition = ref(false)

  // 记录首次 model-ready 是否已处理（避免 watch 重复触发时反复设置 transform）
  // ⚠️ 跨边界写穿透：由 App.vue 的 enterMainContent 在过渡结束后复位
  const initialPositionSet = ref(false)

  // ⚠️ 声明顺序（与步骤③ useLive2dSource 同一处理）：
  // `onModelReady` 读取 `isChatPeekMode`，而原 App.vue 里后者声明在它**之后** ——
  // 因 App.vue 是「<script> + <script setup>」双脚本块结构，实测该写法在 .vue 下不触发
  // `ts/no-use-before-define`（属 App.vue 的 lint 盲区）；但本文件是纯 .ts，实测会报
  // 「'isChatPeekMode' was used before it was defined」。故把 peek 判定/常量/施加函数
  // 整体提前到 `onModelReady` 之前 —— **仅调整声明顺序，逻辑零改动**（computed 与
  // const 对象均为惰性/无副作用创建，函数声明本就可提升）。
  const isChatPeekMode = computed(() => {
    return showMainContent.value
      && !splashVisible.value
      && currentRoute.path.startsWith('/chat')
      && messageViewExpanded.value
      && !isFloatingMode.value
  })

  const PEEK_EXPRESSION = {
    ParamBodyAngleX: -18,
    ParamAngleZ: -14,
    ParamAngleX: 8,
    ParamEyeLOpen: 0,
    ParamEyeROpen: 1,
  } as const

  function applyPeekExpression() {
    setExpression({ ...PEEK_EXPRESSION })
  }

  function onModelReady(pos: { faceX: number, faceY: number }) {
    if (!modelReady.value) {
      modelReady.value = true
      notifyModelReady()
    }

    persistStartupLive2dSource(activeLive2dSource.value)

    // splash 阶段：将 Live2D 面部居中到矩形框中央
    if (splashVisible.value && !initialPositionSet.value) {
      initialPositionSet.value = true
      // frame-mask 中心: left 50%, top 38% (见 SplashScreen.vue --frame-y)
      const cx = window.innerWidth * 0.5
      const cy = window.innerHeight * 0.38
      // 以面部为缩放原点，保证 scale 后面部仍居中
      live2dTransformOrigin.value = `${pos.faceX}px ${pos.faceY}px`
      live2dTransform.value = `translate(${cx - pos.faceX}px, ${cy - pos.faceY}px) scale(2.2)`
      // 开屏闭眼 + 身体静止
      setExpression({ ParamEyeLOpen: 0, ParamEyeROpen: 0, ParamBodyAngleX: 0, ParamAngleZ: 0 })
    }

    if (isChatPeekMode.value) {
      applyPeekExpression()
    }
  }

  // 模型加载完成后即显示（不等标题动画）
  const live2dShouldShow = computed(() => {
    return modelReady.value
  })

  const live2dPeekShellStyle = computed(() => {
    if (!isChatPeekMode.value) {
      return {
        transform: undefined,
        transformOrigin: undefined,
      }
    }
    return {
      transform: 'translate3d(-234px, -1.6vh, 0) rotate(-4deg) scale(1.05)',
      transformOrigin: '24% 72%',
    }
  })

  const live2dModelX = computed(() => {
    if (!isChatPeekMode.value) {
      return CONFIG.value.web_live2d.model.x
    }
    return Math.min(CONFIG.value.web_live2d.model.x, -0.17)
  })

  const live2dModelY = computed(() => {
    if (!isChatPeekMode.value) {
      return CONFIG.value.web_live2d.model.y
    }
    return CONFIG.value.web_live2d.model.y - 0.15
  })

  const live2dCombinedTransform = computed(() => {
    return live2dTransform.value
  })

  const live2dCombinedTransition = computed(() => {
    if (live2dTransition.value) {
      return 'transform 1.2s cubic-bezier(0.4, 0, 0.2, 1), opacity 0.8s ease'
    }
    return 'opacity 0.35s ease'
  })

  const live2dPeekShellTransition = computed(() => {
    if (isChatPeekMode.value) {
      return 'transform 2.3s cubic-bezier(0.16, 0.84, 0.24, 1) 0.36s'
    }
    return 'transform 0.52s cubic-bezier(0.4, 0, 0.2, 1)'
  })

  // 仅在 effectiveLive2dSource 真正变化时才重新挂载 Live2dModel（销毁旧 PIXI.Application + 创建新 WebGL context）。
  // 不再把 backendConnected / activeTabId / activeAgentCharacterTemplate 放进 watch：
  //   - backendConnected 在后端断连重连时会 true/false 来回切换，会导致 Live2D 频繁重挂载，反复创建 WebGL context，
  //     旧 context 来不及释放时会耗尽浏览器 WebGL context 配额（通常 16 个），表现为"Live2D 加载不出来"。
  //   - activeTabId / activeAgentCharacterTemplate 的变化已经会通过 effectiveLive2dSource 这个 computed 反映出来，
  //     这里再列一次属于重复触发。
  watch(effectiveLive2dSource, () => {
    live2dRenderKey.value += 1
  })

  watch(isChatPeekMode, (peeking) => {
    if (!showMainContent.value || splashVisible.value) {
      return
    }
    if (peeking) {
      applyPeekExpression()
      return
    }
    clearExpression()
  }, { immediate: true })

  return {
    Live2dModel,
    width,
    height,
    scale,
    live2dRenderKey,
    modelReady,
    live2dTransform,
    live2dTransformOrigin,
    live2dTransition,
    initialPositionSet,
    onModelReady,
    live2dShouldShow,
    live2dPeekShellStyle,
    live2dModelX,
    live2dModelY,
    live2dCombinedTransform,
    live2dCombinedTransition,
    live2dPeekShellTransition,
  }
}
