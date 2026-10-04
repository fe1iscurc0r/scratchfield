# airi 授粉报告 · 灵魂容器 → NEKO 人格标准化 + 知识按需注入

> 来源：moeru-ai/airi（48k★，MIT，TypeScript，自托管 AI 伴侣 / Neuro-sama 复刻）
> 审查：实验田维护者（Hermes）｜日期：2026-08-17
> 定位：融合参考层——不整包吞，提取「灵魂容器格式 + 按需知识注入 + 能力解耦」三大件，授粉到 NEKO 交互层与陆墨人格层。

---

## 一、这是什么

airi 自称 "a container of souls"（灵魂容器）——把 AI 虚拟角色的人格、记忆、能力、外观封装成可独立装载的单元，多个 soul 在同一 runtime 共存。核心不是 Live2D（那是皮），是**角色卡（Character Card V3）作为灵魂的可移植格式**。

对我们（NEKO + 陆墨）的关键判断：**不抄它的多灵魂市场，抄它的「灵魂容器格式」**。NEKO 是单一灵魂（陆墨脑 + NEKO 身体），但陆墨这个人格目前散在配置里，没有标准化、不可移植、不可版本化。airi 给了标准答案。

---

## 二、源领域 → 目标域 映射

| 源（airi） | 目标（scratchpad） | 授粉方式 | 收益 |
|---|---|---|---|
| Character Card V3（`ccc/codec/characterCardV3.ts`） | 陆墨人格快照（NEKO 端 + 工作端的同一人格） | 抄 CCv3 schema 做人格标准化格式 | 高 |
| `character_book`（Lorebook：keys 触发词 + 正则 + priority + selective） | 陆墨科研知识按需注入（替代全塞 system prompt） | 抄 Lorebook 检索注入机制 | 高 |
| `extensions.depth_prompt`（按对话深度分层提示） | NEKO 闲聊 vs 工作模式的提示切换 | 抄 depth_prompt 分层 | 中 |
| CharacterCapability（每角色独立 llm/tts/vlm/asr 后端） | NEKO 的 LLM/TTS 后端解耦（呼应「协议无关抽象层」） | 抄 capability 绑定模式 | 高 |
| `contracts/`（AgentLLMPort / AgentContextPort / SessionPort / StreamPort） | NEKO 插件化端口抽象 | 抄端口/适配器模式 | 中 |
| memory-pgvector（记忆独立微服务） | NEKO 记忆模块独立化 | 参考架构，暂不落地 | 低 |

---

## 三、核心数据结构共鸣（四处最值钱的）

### 3.1 Character Card V3 —— 灵魂的可移植快照

```ts
// packages/ccc/src/codec/characterCardV3.ts
const characterCardDataSchema = objectWithRest({
  name, description, personality, scenario,
  first_mes, mes_example, alternate_greetings,      // 人格 + 开场 + 示例对话
  system_prompt, post_history_instructions,          // 系统提示 + 历史后置指令
  character_book,                                    // Lorebook 按需知识
  extensions: { depth_prompt, talkativeness, world }, // 分层提示 + 话痨度 + 世界观
  tags, creator, creator_notes, ...
}, unknown())
```

**共鸣点**：NEKO 的「陆墨人格」现在是一堆散落的 prompt/配置。授粉后人格变成一个 `chara_card_v3` 快照——**可版本化、可 diff、可换机迁移、可给别的 agent 复用**。`first_mes`/`mes_example`/`post_history_instructions` 三个字段把「人设 + 对话风格 + 行为边界」钉死，正是人格持久化缺的三根钉子。

### 3.2 Lorebook（character_book）—— 知识按需注入，不是全塞

```ts
// packages/ccc/src/codec/characterCardV3.ts
const characterBookEntrySchema = objectWithRest({
  keys: array(string()),       // 触发词
  content: string(),           // 注入内容
  enabled: boolean(), insertion_order: number(),
  use_regex: boolean(), priority: optional(number()),
  selective: optional(boolean()),             // 只在被点名时注入
  position: optional(picklist(['before_char','after_char'])), // 注入位置
}, unknown())
```

**共鸣点**：这是整份报告最值钱的一行。陆墨的科研知识（木质素/水凝胶/材料）如果全塞进 system prompt，token 爆炸且稀释人格。Lorebook 的判据是：**知识用「触发词 + 正则 + 优先级」动态检索，命中才注入**，`selective` 控制「仅在被点名时才带上」，`position` 控制注入在人格前后。NEKO 授粉后：陆墨闲聊时零科研知识负载，聊到「木质素」时命中 keys 才把相关条目注入——省 token 且不污染人格。

### 3.3 CharacterCapability —— 能力按灵魂绑定

```ts
// packages/stage-ui/src/types/character.ts
const CharacterCapabilityConfigSchema = object({
  apiKey, apiBaseUrl,
  llm: optional(object({ temperature, model })),
  tts: optional(object({ ssml, voiceId, speed, pitch })),
  vlm: optional(object({ image })),
  asr: optional(object({ audio })),
})
const CharacterCapabilityTypeSchema = union([literal('llm'), literal('tts'), literal('vlm'), literal('asr')])
```

**共鸣点**：NEKO 当前 LLM/TTS 是全局单一后端。airi 的答案是**每个 soul 独立绑定自己的 llm/tts/vlm/asr 配置**。授粉后：陆墨工作端（天选7）绑 DeepSeek V4 Pro + Edge TTS，NEKO 宠物端绑轻量模型 + 本地 TTS——同一个灵魂，不同端不同后端，跟记忆里「协议无关设备抽象层」是同一个哲学。

### 3.4 contracts 端口抽象 —— agent 不依赖具体实现

```ts
// packages/core-agent/src/contracts/llm-port.ts
export interface AgentLLMPort {
  stream: (model, chatProvider, messages, options?) => Promise<void>
}
// packages/core-agent/src/contracts/context-port.ts
export interface AgentContextPort {
  ingest: (envelope) => void; snapshot: () => Record<string, ContextMessage[]>; reset: () => void
}
```

**共鸣点**：核心 agent 只认 `AgentLLMPort`/`AgentContextPort` 接口，不碰具体 provider——换模型、换记忆实现都不动核心。NEKO 插件化可直接抄这个「端口 + 适配器」骨架。

---

## 四、难度 × 收益

| 授粉项 | 难度 | 收益 | 建议 |
|---|---|---|---|
| Character Card V3 人格标准化 | **低**（纯 schema，无运行时依赖） | **高**（人格可版本化/可迁移） | **立即授粉**，陆墨人格先导出成 CCv3 |
| Lorebook 按需知识注入 | **中**（需写检索 + 注入管线） | **高**（科研知识省 token 不污染人格） | **立即授粉**，先做木质素/水凝胶两条目验证 |
| CharacterCapability 能力解耦 | **中**（需重构 NEKO 后端绑定） | **高**（工作端/宠物端独立后端） | 立即授粉，配合 M3 反向事件通道 |
| depth_prompt 分层提示 | **低**（一个字段） | **中**（闲聊/工作模式切换） | 参考，随 CCv3 一起落 |
| contracts 端口抽象 | **中**（重构 NEKO 核心） | **中**（插件化） | 参考，不急着照搬 |

**总评**：airi 的 48k★ 值在「灵魂容器格式」——把人格、知识、能力三者解耦成可独立装载的单元。NEKO 不抄它的多灵魂市场，抄「单一灵魂的标准化 + 知识按需注入 + 能力解耦」这三个点。最高优先级是 **3.1（人格 CCv3 化）+ 3.2（Lorebook 知识注入）**，因为这两处直接解决陆墨「人格散落 + 科研知识 token 爆炸」两个真实痛点，且纯格式/管线，不碰 Live2D 皮。

---

## 五、可执行验收（可 grep / assert）

```bash
# 1. 本报告含三大件（工单验收）
grep -c "源领域" docs/airi-授粉报告.md        # ≥1
grep -c "数据结构共鸣" docs/airi-授粉报告.md   # ≥1
grep -c "难度 × 收益" docs/airi-授粉报告.md    # ≥1

# 2. 授粉引用到真实源码文件
grep -c "characterCardV3" docs/airi-授粉报告.md      # ≥2
grep -c "character_book" docs/airi-授粉报告.md       # ≥1
grep -c "contracts" docs/airi-授粉报告.md            # ≥1

# 3. 不碰主流程（本报告只落 docs，无代码改动）
git diff --stat -- NEKO apiserver | wc -l            # 0
```

---

*授权：MIT → 主仓 AGPL v3 允许直接吞。本报告仅授粉，不拉源码进主仓（源码归档在 github_haul/fusion/airi/，仅 readme + 关键 schema，未 clone 534MB 资产）。*
