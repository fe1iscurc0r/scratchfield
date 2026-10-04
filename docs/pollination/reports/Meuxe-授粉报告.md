# Meuxe 授粉报告 · ACP 脑 + Live2D 皮 → 陆墨脑 + NEKO 皮

> 来源：meet447/Meuxe（72★，MIT，Rust + React / Tauri 2）
> 审查：实验田维护者（Hermes）｜日期：2026-08-16
> 定位：融合参考层——自托管 AI 伴侣桌宠，与我们「陆墨脑 + NEKO 皮」**架构同构**，授粉其 ACP 脑分离与关系状态。

---

## 一、这是什么

Meuxe 是一个 **Tauri 2 桌面伴侣**——屏幕上的角色，能记住你、说话、随时间成长。关键设计：**聊天不内嵌 LLM**，而是作为 **ACP（Agent Client Protocol）客户端**，把推理交给用户安装的 CLI agent（Claude Code / Codex / OpenCode / 自定义）。

---

## 二、源领域 → 目标域 映射

| 源（Meuxe） | 目标（scratchpad） | 授粉方式 | 收益 |
|---|---|---|---|
| **ACP-backed chat**（不内嵌 LLM，走 CLI agent） | **陆墨脑（Hermes/Naga）+ NEKO 皮** | 同构验证 | 高 |
| 分层角色（`soul.md`/`style.md`/`rules.md`） | 陆墨角色卡分层 | 抄分层结构 | 中 |
| 关系状态（trust/affection/mood/energy 演化） | 陆墨的长期关系记忆 | 参考状态机 | 中 |
| `<<expression>>` 情感标签实时解析 | NEKO 表情驱动的流式解析 | 抄标签协议 | 高 |
| 平行 TTS（并行合成语音段降延迟） | 陆墨语音层延迟优化 | 参考 | 中 |
| 本地长期记忆（语义/情景/反思式） | 陆墨记忆体系（summer_memory） | 参考分类 | 中 |

---

## 三、核心共鸣（两处最值钱）

### 3.1 ACP-backed = 我们的「脑皮分离」在桌面端的同构实现

Meuxe 明确：**不内嵌 OpenAI 兼容 LLM 客户端**，每条消息都发给一个走 ACP 协议的子进程 agent。persona/memory/relationship 上下文每轮写入 `companion-home/`，作为 agent 的工作目录。

**共鸣点**：这跟我们的「陆墨脑（Hermes/Naga 决策）+ NEKO 皮（Live2D 交互）」是**同一范式**，只是它们用 ACP、我们用 MCP + 事件总线。授粉结论：**「脑（agent）与皮（桌宠）分离，脑走协议、皮只管渲染」是桌宠伴�的收敛解**。Meuxe 的 ACP 客户端实现（Tauri Rust 侧）是 NEKO 接入多 agent 的现成参考。

### 3.2 `<<expression>>` 流式情感标签

Meuxe 实时解析 agent 回复里的 `<<expression>>` 标签，驱动 Live2D 表情。**协议级**约定：LLM 输出文本里夹标签，前端解析后剥离。

**共鸣点**：NEKO 桌宠的「表情/动作驱动」需要一个 LLM→渲染的桥。两种方案：① 结构化输出（LLM 返回 JSON，前端解析）② 内联标签（LLM 流式文本夹 `<<expression>>`，前端正则剥离）。Meuxe 选了 ②，因为**流式**场景下内联标签能随文本一起到，不用等整段 JSON 解析完。这个取舍对 NEKO 的表情驱动是关键决策，直接抄 ②。

### 3.3 关系状态随时间演化

trust / affection / mood / energy 四个状态随时间演化——这是「桌宠不只是聊天 UI，是有长期关系记忆的实体」的关键。跟陆墨的 `summer_memory` + 关系记忆是同类，但 Meuxe 把它做成了显式的四元状态。

---

## 四、难度 × 收益

| 授粉项 | 难度 | 收益 | 建议 |
|---|---|---|---|
| ACP-backed 脑分离架构 | **低**（验证同构） | **高**（NEKO 接多 agent 蓝图） | **授粉到 NEKO 脑接口** |
| `<<expression>>` 内联标签 | **低**（正则剥离，~20 行） | **高**（NEKO 表情驱动） | **立即授粉** |
| 分层角色（soul/style/rules） | 低（YAML/MD 拆分） | 中（陆墨角色卡结构化） | 参考 |
| 关系状态四元演化 | 中（需状态持久化） | 中（长期关系记忆） | 参考 |
| 平行 TTS | 中（并发管理） | 中 | 观望 |

**总评**：Meuxe 是 4 个 P2 项目里**与我们架构最同构**的一个——它是「ACP agent 脑 + Live2D/VRM 皮」，我们是「Hermes/Naga 脑 + NEKO 皮」。它的 `<<expression>>` 表情协议和 ACP 脑分离，是 NEKO 桌宠下一步「接脑 + 表情驱动」的两块现成拼图。注意它 998KB 体积主要是 Live2D/VRM 资产，不是垃圾。

---

## 五、可执行验收

```bash
grep -c "ACP" docs/Meuxe-授粉报告.md               # ≥4
grep -c "expression" docs/Meuxe-授粉报告.md         # ≥3
grep -c "脑皮分离\|脑.*皮" docs/Meuxe-授粉报告.md     # ≥2
grep -c "MIT" docs/Meuxe-授粉报告.md                # ≥1
grep -c "难度 × 收益" docs/Meuxe-授粉报告.md         # ≥1
git diff --stat -- NEKO apiserver | wc -l           # 0
```

*授权：MIT → 主仓 AGPL v3 允许直接吞。只授粉架构与协议设计，不抄代码（Rust/Tauri 栈）。源码归档在 github_haul/fusion/Meuxe/。*
