# omnilimb-face 接入说明

> 状态：已耦合（clone 到 `coupled/omnilimb-face/`，AGPL-3.0 同许可直接吞）

## 这是什么

hermes-agent 的独立插件——给 agent 一张「会说话的脸」：语音免提交互（VAD+STT）、实时打断（barge-in）、Live2D/Live3D 口型同步 + 表情。

## 为什么高价值（与我们架构同构）

它的核心设计跟我们的「脑皮分离」完全一致：

- **从不自己调用 LLM** —— 转写经 `ctx.inject_message` 注入，回复经 `transform_llm_output`/`post_llm_call` 钩子拦截，形象说出的永远是宿主 agent 的真实回答
- **不修改 hermes 任何核心文件** —— 仅通过 `register(ctx)` 扩展面集成
- **复用 stt/tts 配置段** —— 不自带模型配置

对比我们的 N.E.K.O.（陆墨脑 + NEKO 皮），它是「hermes 脑 + face 皮」，同一个范式。它的 `register(ctx)` + 钩子拦截机制，正是我们 M3 反向事件通道的另一种实现——值得授粉。

## 插件契约（plugin.yaml）

- hooks: `on_session_start` / `on_session_end` / `transform_llm_output` / `post_llm_call`
- tools: `vtuber_status` / `vtuber_say`
- kind: standalone，requires_env: []

## 融合方式

**耦合**（完整源码在 `coupled/omnilimb-face/`），不改造。后续若要接陆墨脑，参考它的 `hermes_chat_worker.py` 的 `register(ctx)` 模式，把它当成「NEKO 皮的备选/参照实现」。

## 许可

AGPL-3.0（主 LICENSE）+ COMMERCIAL-LICENSE.md（双许可）。同 AGPL 主仓，直接吞，无冲突。
