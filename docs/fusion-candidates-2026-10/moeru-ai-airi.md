# 融合候选：moeru-ai/airi

> **优先级 P0（本批第一）** ｜ 采集：2026-10-08 GitHub API 实测

## 0. 实测元数据

| 项 | 值 |
|---|---|
| 仓库 | `moeru-ai/airi` |
| ★ | **50147**（工单初勘 50138，实涨） |
| 许可 | **MIT** ✓（可引码） |
| 语言 / 体积 | TypeScript / **568 MB**（⚠️ 与 HanLog 327MB 同级，调研期不 clone） |
| 最近 push | **2026-10-08**（当天仍活跃） |
| topics | `ai-companion` / `ai-vtuber` / `live2d` / `neuro-sama` / `digital-life` |

## 1. 架构一句话（**描述级**，未读源码）

自托管的 **AI 伴侣容器**：把「Live2D 舞台 + 语音管线 + 记忆」封装成可自部署的一体化应用，
目标是复刻 Neuro-sama 那种"可持续直播/陪伴"的形态（`ai-vtuber` / `digital-life` 主题 +
"container of souls" 的自我描述）。**与陆墨定位最接近的开源同位素。**

## 2. 与自家对应模块的差距

| 维度 | airi | 陆墨现状 |
|---|---|---|
| 舞台 | `stage-web`（工单点名：手游级前端架构） | NEKO `neko-electron-shell` + `frontend` 的 `FloatingView` / Live2D 链 |
| 语音 | 一体化语音管线 | NEKO 语音候选准入（10-07 同步已进）+ `apiserver` voice 线 |
| 记忆 | 内置记忆 | `mcpserver/memory_maas` + `graph_memory_adapter` + `event_bus` |
| 形态 | 单体自托管容器 | **能力总线**（MCP 多工具）+ 多 shell（NEKO / Electron） |

**差距的本质**：airi 是**单体一体机**，陆墨是**总线 + 多壳**。可借的是**壳内体验工程**，不是整体架构。

## 3. 可借用的具体设计（非代码）

1. **舞台与逻辑分离的边界划法** —— 看它怎么切"舞台渲染 / 角色状态 / 语音输入"三层
   （对应我们的 `characters/` 模板 vs 实例状态，正是 `.naga` 实例存储那层）。
2. **手游级前端的资源调度**：Live2D 模型 + 音频 + 动画在浏览器端的**按需加载与降级**策略
   （可对照我们 `renderer.ts` 已做的"异步组件 + 按需加载"，见工单209 任务二）。
3. **语音管线的端到端时延切分**：VAD / ASR / LLM / TTS 各段的缓冲与打断（barge-in）处理。
4. **伴生形态的产品化细节**：启动/待机/互动/离线的状态机（可对照 `agent_expression.py` 的 6 状态）。

## 4. 许可与边界

- **MIT** → 引用代码在许可上无障碍；但 568 MB 体量 + 与我们的壳架构差异大 →
  **本轮只借设计**，不引码、不 clone。
- ⚠️ **查重**：`docs/openclaw-架构对标-2026-09-09.md` 已提及 airi（W101-04），
  但那是**执行层对标**视角；本卡增量 = **舞台/语音/伴生形态**视角。

## 5. 融合优先级与下一步

**P0** —— 与陆墨定位最接近，参考价值最高。
**下一步（若选中）**：开 SPEC 做**源码级复核**，重点回答三个问题：
① stage-web 的渲染分层能不能喂给我们的 `FloatingView`/NEKO 壳？
② 语音打断（barge-in）策略与我们的 `voice` 线差异？
③ 角色状态机 vs 我们的 `agent_expression` 六状态 + NEKO 5 情绪标准集的映射是否更优？
