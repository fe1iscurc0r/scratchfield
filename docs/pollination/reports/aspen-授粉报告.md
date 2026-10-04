# aspen 授粉报告 · 最小可读版语音打断 → 语音层

> 来源：thooton/aspen（18★，CC0-1.0，Python）
> 审查：实验田维护者（Hermes）｜日期：2026-08-16
> 定位：融合参考层——2KB 仓库的「语音打断」极简实现，授粉到 NEKO 语音层。

---

## 一、这是什么

aspen 是一个「$0.01/分钟的实时语音助手」，组件化极简：每个组件（microphone/segmenter/transcriber/responder/synthesizer/speaker）跑独立线程，靠一个输入队列 + 一个输出队列 + 两个 `threading.Event` 串起来。它没有状态机、没有管理器，打断逻辑只用**一个共享 Event** 就解决了。

---

## 二、源领域 → 目标域 映射

| 源（aspen） | 目标（scratchpad） | 授粉方式 | 收益 |
|---|---|---|---|
| `speaking_event`（threading.Event 作「用户正在说话」物理信号） | NEKO 桌宠 TTS 播放打断 | 抄「一处 set，处处轮询」模式 | 高 |
| 逐词时长估计 + 渐进式对话状态 | 陆墨对话状态（打断后上下文只留已说出口的词） | 抄 `speaker.py:50-63` | 高 |
| 多线程组件模型（每组件一线程+队列） | 语音管线解耦 | 参考架构 | 中 |
| `Conversation` 同角色消息合并 | 陆墨消息历史（逐词追加导致的消息碎片） | 抄 `conversation.py:11-30` | 中 |
| 流式句子分段（`segment_text_by_regex`） | TTS 首字延迟优化（按句流式合成） | 参考 `responder.py:28-64` | 中 |

---

## 三、核心共鸣（三处最值钱）

### 3.1 打断 = 一个 `threading.Event`，不是状态机

cascade 用 `InterruptionManager` + `SystemState` 四态机（重）；aspen 用**一个 `speaking_event`**（轻）：

- `segmenter.py`：用户开始说话 → `speaking_event.set()`；静音结束 → `clear()`
- `responder.py:130`：流式生成每吐一个 token 前检查 `is_set()`，用户说话就 `break`
- `speaker.py:57`：逐词播放时 `speaking_event.wait(word_duration)`，用户说话就 `sd.stop()`

**共鸣点**：NEKO 桌宠的打断，本质就是「用户插嘴 → 立即停 TTS」。aspen 证明这件事不需要状态机，一个 Event 就够。这跟 cascade 形成「重/轻」两级参考——cascade 的卫兵防状态劫持，aspen 的 Event 求极简。

### 3.2 逐词时长估计 → 渐进式对话状态

```python
# speaker.py:50-63
word_duration = audio_duration / len(words)   # 每个词的估计时长
for word in words:
    if self.speaking_event.wait(word_duration):  # 播这个词期间被打断？
        sd.stop(); break                          # 停，且不把这个词写进对话
    self.conversation.append("assistant", word)   # 播完才写进上下文
```

**共鸣点**：这是 aspen 最精妙的一行。打断后，对话上下文里 assistant 消息**只包含「已经说出口的词」**，不含被打断截断的半句。陆墨/N.E.K.O. 的对话状态如果逐字流式推进，必须抄这个——否则打断后上下文会出现「assistant 说了没说完的话」，下一轮 LLM 会接错。

### 3.3 `Conversation` 同角色消息合并

```python
# conversation.py:15-29
if self.messages and self.messages[-1]["role"] == role:
    # 合并进上一条，而不是新增一条
    last_message["content"] = f"{last_content}{spacer}{content}"
```

**共鸣点**：因为逐词 append assistant，如果不合并会炸出几百条 assistant 消息。陆墨的消息历史（尤其流式逐段写入时）同理——同角色合并是「流式写入」的必要配套。

---

## 四、难度 × 收益

| 授粉项 | 难度 | 收益 | 建议 |
|---|---|---|---|
| `speaking_event` 打断模式 | **低**（一个 Event + 三处轮询） | **高**（NEKO 打断能力） | **立即授粉** |
| 逐词时长估计 + 渐进式上下文 | **低**（~10 行） | **高**（打断后上下文一致性） | **立即授粉** |
| 同角色消息合并 | **低**（~15 行） | 中（流式写入必备） | **立即授粉** |
| 多线程组件模型 | 中（重构管线） | 中 | 参考，不照搬 |

**总评**：aspen 是「打断逻辑」的最小可读版，18★ 值在**极简**——用三个零依赖技巧（Event 轮询 / 逐词时长 / 同角色合并）完成了 cascade 用整套状态机才做到的事。跟 cascade 配合：cascade 给「判据」，aspen 给「最简实现」。

---

## 五、可执行验收

```bash
grep -c "speaking_event" docs/aspen-授粉报告.md      # ≥4
grep -c "逐词" docs/aspen-授粉报告.md                # ≥2
grep -c "CC0" docs/aspen-授粉报告.md                 # ≥1
grep -c "难度 × 收益" docs/aspen-授粉报告.md          # ≥1
git diff --stat -- NEKO apiserver | wc -l            # 0
```

*授权：CC0-1.0 → 公有领域，无任何限制，可直接吞。本报告仅授粉，源码归档在 github_haul/fusion/aspen/。*
