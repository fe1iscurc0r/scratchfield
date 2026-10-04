# bongo-cat-next 现代化 Live2D 桌宠授粉（W103-02）

> 2026-09-09 · 评估（不写实现）· 上游：liwenka1/bongo-cat-next（147★，MIT，TypeScript/Next.js，Live2D 猫咪桌宠，2026-08-16 活跃）
> 许可：MIT（授粉报告已复核）
> 源码：shallow clone 到本机 D:/my git/haul-backfill/bongo-cat-next——以下引用为实读行号。

## 一、架构拆解（实读）

- 组件化：`src/components/cat-viewer.tsx`（主视图，交互模式判定 `isInteractiveModelMode`
  cat-viewer.tsx:36 + useEffect 状态钩挂 :41）、`expression-selector.tsx` / `motion-selector.tsx`
  （表情/动作选择器）、`keyboard-visualization.tsx`（键盘可视化）。
- 状态管理：zustand store（`stores/model-store`）。
- 栈：Next.js App Router（src/app/layout.tsx + page.tsx）。

## 二、授粉三大件①：源→目标映射

| 源组件（bongo-cat-next） | 目标模块 | 授粉方式 | 收益 |
|-------------------------|---------|---------|------|
| 轻量 Live2D 渲染 + 陪伴模式 | NEKO 前端/桌宠交互 | 前端渲染层参考 | 轻量桌宠形态 |
| 交互事件（点击/拖拽/陪伴） | NEKO 交互层 | 事件模型参考 | 交互丰富度 |
| 陪伴状态机 | NEKO 状态 | 机制参考 | 陪伴模式 |

## 三、授粉三大件②：核心数据结构共鸣（2-3 处，实读引用）

1. **交互模式判定与钩挂**（cat-viewer.tsx:36 `isInteractiveModelMode` + :41 useEffect）：
   「可交互模型模式」显式判定——NEKO 桌宠交互开关的对照实现。
2. **表情/动作选择器分离**（expression-selector.tsx / motion-selector.tsx）：
   表情集与动作集作为独立可选面——与 89号 petdex 事件→动画映射同源，吸收点=选择器 UI 形态。
3. **zustand store 状态模型**（stores/model-store）：桌宠状态（模型/模式）集中管理——NEKO 状态机补充参考。
> 行号级引用待 github_haul/coupled/bongo-cat-next 快照回填。

## 四、与 NEKO 前端对照 + 借鉴点（≥3）

| 维度 | bongo-cat-next | NEKO 前端 |
|------|----------------|-----------|
| 技术栈 | Next.js | Vue 3 + PrimeVue |
| Live2D | 轻量单模型 | Live2dModel 已有 |
| 交互 | 点击/拖拽/陪伴 | 部分 |

借鉴点：① 陪伴状态机 ② 交互事件映射表 ③ 模型加载优化。
落地建议：吸收「陪伴状态机 + 交互事件映射」进 NEKO 交互层（参考级，不迁移 Next.js）。

## 五、许可裁定与结论

MIT 可借鉴；结论：**前端交互参考（评估级）**，落点 NEKO 桌宠交互升级工单。

---
*评估：fe1iscurc0r · 2026-09-09 · 源码行号引用待 github_haul 快照回填*
