# Prompt Architecture README

本文件用于理清 NagaAgent 当前提示词体系的真实边界，避免把“固定提示词”“角色模板”“干员后天发展”三类内容混在一起。

这不是某个单一引擎的说明书，而是整个项目的提示词组织约定。

## 当前结论

当前项目不是“一个 prompt 目录 + 若干 patch”，而是三处存储：

1. `system/prompts`
2. `characters`
3. `.naga`（或等价的干员实例目录）

它们各自承担不同职责。

## 三处存储的职责

### 1. `system/prompts`

这里存放：
- 固定提示词
- 工具提示词
- 调度提示词
- 压缩提示词
- 平台共通纪律
- 与角色弱相关或无关的稳定模板

这里不应该存放：
- 某个具体角色的完整人格模板
- 某个具体干员的后天成长
- 某个实例私有的灵魂变化

一句话概括：
`system/prompts` 是平台固定层和工具层。

## 标准层级模板目录

为了避免后续继续把“运行时最终 prompt”和“源模板层级”混在一起，`system/prompts` 下新增标准模板目录：

1. `system/prompts/tier1`
2. `system/prompts/tier2`
3. `system/prompts/tier3`
4. `system/prompts/tier4`

说明：
- 这些目录是前四层 system prompt 的模板位与装配顺序声明，也是当前运行时真实读取的装配入口
- 文件名前缀数字表示同层内的装配顺序
- 即使真实内容来自 `characters` 或 `.naga`，这里也要保留引用槽模板
- 顶层的 `tool_dispatch_prompt.txt`、`agentic_tool_prompt.txt`、`context_compress_prompt.txt` 是 tier 装配时使用的包裹模板或成品片段

## 注入入口总览

- `tier1/*`：
  `system.config._build_tier1_variables()` 组装变量，
  `system.config.build_system_prompt()` 按顺序装配
- `tier2/*`：
  `system.config.build_context_supplement()` 装配，
  其中 `tier2/1` 的正文来自 `system/prompts/agentic_tool_prompt.txt`
- `tier3/*`：
  `system.config.build_instance_prompt_section()` 接收实例变量，
  上游主要来自 `apiserver.routes.chat._build_agent_prompt_context()`
- `tier4/*`：
  `system.config.build_context_supplement()` 注入时间、技能、MCP、通讯录、搜索、RAG、激活技能
- `tool_dispatch_prompt.txt`：
  `system.config.build_context_supplement()` 作为最外层包裹模板读取
- `context_compress_prompt.txt`：
  `apiserver.context_compressor._load_summarize_prompt()` 读取
- `characters/*/conversation_style_prompt.txt`：
  `system.character_bundle.load_character_prompt_text()` 读取，
  再进入 `system.config._build_tier1_variables()`
- `characters/*/skills/*/SKILL.md`：
  `system.character_bundle.load_character_skill_sections()` 读取，
  再进入 `system.config._build_tier1_variables()`
- `.naga/agents/*/IDENTITY.md|SOUL.md|notes/CLAUDE.md|memory/*`：
  `apiserver.routes.chat._build_agent_prompt_context()` 读取，
  再进入 `build_system_prompt()` / `build_context_supplement()`

## 注释语法

- 注释前缀：`//`
- 过滤入口：`system.config.strip_prompt_comment_lines()`
- 当前已接入该规则的主要文本源包括：
  `system/prompts/*.txt|md`、`characters/*/conversation_style_prompt.txt`、
  `characters/*/skills/*/SKILL.md`、`.naga/agents/*/IDENTITY.md|SOUL.md|notes/CLAUDE.md`

### 2. `characters`

这里存放：
- 角色人设
- 角色外显性格
- 角色语言风格
- 角色自带技能
- 角色资源绑定信息

典型例子：
- `characters/娜杰日达/conversation_style_prompt.txt`
- `characters/娜杰日达/skills/live2d_controller/SKILL.md`
- `characters/娜杰日达/娜杰日达.json`

这里不应该存放：
- 某个干员独有的长期偏好
- 某个端、某个实例自己的灵魂成长
- 随项目推进积累的私有工作记忆

一句话概括：
`characters` 是角色模板层，也就是先天人设与角色自带能力包。

### 3. `.naga`

这里存放：
- 每个干员自己的后天发展
- 每个端自己的灵魂
- 每个实例自己的长期偏好
- 每个实例绑定的项目连续性

这里的内容不是“角色共有”，而是“实例私有”。

一句话概括：
`.naga` 是干员/端/实例级的成长层，也就是后天灵魂。

## 五层结构如何映射到三处存储

你当前认可的五层结构是合理的，但它不是五个目录，而是五个逻辑层。

### 第一层：基础系统提示层

含义：
- 基础人格
- 不轻易变化的角色身份
- 稳定的表达原则

来源：
- 平台共通部分来自 `system/prompts`
- 角色部分来自 `characters`
- 角色自带技能也随 `characters` 一起进入第一层

结论：
- 第一层不是只放在一个地方，而是由 `system/prompts + characters` 共同组成。

### 第二层：基础工具层

含义：
- 工具定义
- 工具纪律
- 工具调度格式
- 工具 schema 相关约束

来源：
- 主要来自 `system/prompts`
- 若某个引擎需要额外工具适配，则由引擎装配器生成

结论：
- 第二层主要属于 `system/prompts`
- 切换引擎时这一层需要替换或重建

### 第三层：记忆层

含义：
- 记忆
- 灵魂
- 记事本
- 持续状态

来源：
- 角色共通记忆模板可以来自 `characters`
- 干员/实例自己的灵魂与发展应来自 `.naga`
- 项目工作记事可以来自工作区文件，如 `AGENTS.md`、`CLAUDE.md`

结论：
- 第三层不能再被理解为一个全局统一文件
- 它至少分为“角色模板部分”和“实例成长部分”

### 第四层：输出风格与运行环境层

含义：
- 初始日期
- 会话起始环境
- 通用纪律
- MCP
- SKILL

来源：
- 主要来自 `system/prompts`
- 会话启动时按引擎装配

结论：
- 这层建议在会话起始固定
- 后续新增内容不要回写覆盖这一层，而应作为消息追加

### 第五层：消息层

含义：
- 用户消息
- 助手回复
- 工具调度
- 工具结果
- 历史压缩
- 增量记忆

来源：
- 运行时消息流

结论：
- 所有增量优先进入第五层
- 不要为了加一条新记忆去回写前四层

## 切换引擎时，哪些保留，哪些替换

### 保留的内容

- `system/prompts` 中的平台固定层
- `characters` 中当前角色的人设模板
- 初始环境快照和通用纪律
- 经过规范化后的消息历史摘要

如果是“同一个干员切换引擎”：
- 保留该干员在 `.naga` 中的灵魂与成长数据

### 不默认保留的内容

如果是“同角色但不同干员 / 不同端 / 不同实例”：
- 不默认共享 `.naga` 中的灵魂与成长数据

### 必须替换或重建的内容

- 第二层基础工具层
- 引擎私有 system prompt
- 引擎私有工具纪律
- 引擎私有 bootstrap 结构
- 原始工具轨迹

结论：
- 角色模板跨引擎可复用
- 干员灵魂不一定跨实例复用
- 引擎产物必须重建

## 关于 OpenClaw 与魔改版 OpenClaw

OpenClaw 官方文档说明，它运行时会自动装配系统提示，并支持一组 bootstrap 文件，例如：
- `AGENTS.md`
- `SOUL.md`
- `TOOLS.md`
- `IDENTITY.md`
- `USER.md`
- `HEARTBEAT.md`
- `MEMORY.md` / `memory.md`

这说明：
- OpenClaw 吃到的 prompt 通常是“装配结果”
- 它不是平台唯一真相

对于魔改版 OpenClaw：
- 如果实现仍兼容 OpenClaw 的 prompt builder 和 bootstrap 机制，可以复用 OpenClaw 装配器
- 如果实现改动较大，尤其是换成 Rust 或重写 prompt builder，不应在 OpenClaw 产物上继续打 patch
- 此时应当把它视为一个新的引擎目标，重新定义装配器

结论：
- 魔改版 OpenClaw 不一定是 “OpenClaw + patch”
- 更稳的说法是 “新的引擎装配目标”

## 当前仓库里的 prompt 盘点

### A. 平台固定层：`system/prompts`

当前已发现：
- `system/prompts/tool_dispatch_prompt.txt`
- `system/prompts/agentic_tool_prompt.txt`
- `system/prompts/context_compress_prompt.txt`

当前归类建议：
- `tool_dispatch_prompt.txt`
  属于第四层输出风格与运行环境层里的“附加知识装配模板”
- `agentic_tool_prompt.txt`
  属于第二层基础工具层
- `context_compress_prompt.txt`
  属于第五层消息层的压缩器提示

### B. 角色模板层：`characters`

当前已发现：
- `characters/娜杰日达/conversation_style_prompt.txt`
- `characters/娜杰日达/skills/live2d_controller/SKILL.md`
- `characters/娜杰日达/娜杰日达.json`

当前归类建议：
- `conversation_style_prompt.txt`
  属于第一层基础系统提示层中的角色人格模板
- `characters/娜杰日达/skills/live2d_controller/SKILL.md`
  属于第一层基础系统提示层中的角色自带技能，而不是可选公共技能
- `娜杰日达.json`
  属于角色元数据，不直接作为 prompt 注入，但决定角色资源绑定

### C. 灵魂/成长层：实例级

当前已发现：
- 根目录 `SOUL.md`

当前归类建议：
- 逻辑上它更接近第三层记忆层中的“实例灵魂源数据”
- 它不应再被理解为角色模板本身
- 后续如果要彻底理顺，应迁到 `.naga` 或等价的实例目录中

## 这套结构下的工程约束

1. `system/prompts` 只放固定层、工具层、调度层和压缩层。
2. `characters` 只放角色模板，不放某个干员的私有成长。
3. `.naga` 才是干员后天发展和灵魂沉淀的归宿。
4. 新增记忆和状态，优先作为消息层增量追加，不要频繁重写前四层。
5. 切换引擎时，重建引擎产物，不要直接复用另一个引擎的最终 system prompt。
6. 对 Rust 重写版或非兼容实现，视为新的引擎目标，而不是简单 patch。

## 近期整理建议

接下来建议按这个顺序推进：

1. 先把现有文件按“平台固定层 / 角色模板层 / 实例成长层”标注清楚
2. 再定义引擎装配清单，明确每个引擎会取哪些层
3. 最后再做 `.naga` 层的真正迁移，把灵魂从全局文件抽出来

## 给程序员和产品经理的简化说明

如果只记一句话，请记这个：

- `system/prompts` 是规则和工具
- `characters` 是角色先天人设
- `.naga` 是干员后天灵魂

这三者不能再混着改。
