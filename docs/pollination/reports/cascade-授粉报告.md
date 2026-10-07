# cascade 授粉报告 · 生产级 VAD → 语音层映射

> 来源：xucailiang/cascade（84★，MIT，Python）
> 审查：沈遥（Hermes）｜日期：2026-08-16
> 定位：融合参考层——不直接接入，提取核心数据结构与状态机逻辑，授粉到 scratchpad 语音层与对话状态机。

---

## 一、这是什么

cascade 是一个「高性能异步流式 VAD 处理库」，核心架构一句话：**1:1:1:1 无锁隔离**——1 个 `StreamProcessor` = 1 个独立 silero-vad 模型 + 1 个 VADIterator + 1 个 `FrameAlignedBuffer` + 1 个 `VADStateMachine`。每个 WebSocket 连接拿一个完全独立的实例，无锁无竞争。

它不是语音识别（STT），也不是合成（TTS），是夹在中间的**语音活动检测 + 段切分 + 打断判定**。

---

## 二、源领域 → 目标域 映射

| 源（cascade） | 目标（scratchpad） | 授粉方式 | 收益 |
|---|---|---|---|
| `SystemState`（IDLE/COLLECTING/PROCESSING/RESPONDING） | 陆墨对话状态机（NEKO 说话时用户能否插嘴） | 直接抄状态枚举 + 转移规则 | 高 |
| `InterruptionManager`（打断判定 + 状态生命周期） | NEKO 桌宠 TTS 播放时的语音打断 | 抄 `on_speech_start/end` 逻辑 | 高 |
| 「物理事实优先」状态卫兵 | M3 反向事件通道（`M3.1a-reverse-event-state-SPEC-v1.md`）的状态同步 | 抄 Gatekeeper 模式 | 高 |
| `VADStateMachine` + `SpeechCollector`（帧→语音段） | 端侧语音采集（若未来做本地 VAD） | 参考状态机，暂不落地 | 中 |
| `FrameAlignedBuffer`（512 样本帧对齐） | rf_brain 的 IQ 帧对齐（同构：定长帧 + 时间戳） | 参考帧对齐策略 | 中 |
| 1:1:1:1 实例隔离 | rf_brain 的频谱实例隔离（`max_instances`） | 参考无锁并发模型 | 中 |

---

## 三、核心数据结构共鸣（三处最值钱的）

### 3.1 `SystemState` 四态 —— 与陆墨对话状态机同构

```python
class SystemState(Enum):
    IDLE = "idle"            # 空闲，等输入
    COLLECTING = "collecting" # 用户正在说话（VAD 检测到语音）
    PROCESSING = "processing" # 后端处理中（外部设置）
    RESPONDING = "responding" # 正在回复（外部设置）
```

**共鸣点**：NEKO 桌宠「听 → 想 → 说」天然就是这四个态。当前 scratchpad 的对话状态没有显式建模，是散在事件里的隐状态。授粉后可用一个 `SystemState` 单点管理「能不能打断 / 该不该切态」。

### 3.2 「物理事实优先」卫兵 —— 防状态劫持

```python
# interruption.py:126 附近
def set_state(self, state):
    # 物理事实优先：用户正在说话时，拒绝外部强制切换状态
    if self.current_state == SystemState.COLLECTING:
        logger.warning(f"拒绝状态切换 {self.current_state.value} -> {state.value}: 用户正在说话")
        return
    self._transition_to(state)
```

**共鸣点**：这是整份报告里最值钱的一行。cascade 明确：外部服务（ASR 完成→PROCESSING、开始回复→RESPONDING）可以设状态，但**用户正在说话（COLLECTING）时拒绝一切外部切换**。这直接授粉到 M3 反向事件通道——我们的反向事件状态机同样存在「外部事件 vs 物理事实」的优先级问题，cascade 给了判据：**物理事实 > 外部指令**。防的是「状态分裂（Zombie State）」——VAD 状态机与外部管理器各自维护状态导致不同步。

### 3.3 `VADStateMachine` 的状态同步卫兵（Gatekeeper）

```python
# processor.py:302 附近
interruption_event = self.interruption_manager.on_speech_start(frame.timestamp_ms)
# 状态同步卫兵：管理器拒绝进入收集状态（间隔太短/策略限制）→ 状态机也忽略这次语音
if self.interruption_manager.get_state() != SystemState.COLLECTING:
    return None  # 防止状态分裂
```

**共鸣点**：两个状态机（VAD 状态机 + InterruptionManager）之间用「读回管理器状态」做二次确认，而不是各管各的。这跟我们 rf_brain 里「决策层 vs 执行层」的状态对齐是同一类问题——授粉结论：**跨层状态同步用「读回确认」，不用「广播信任」**。

---

## 四、打断逻辑（可直接抄的判定序列）

cascade 的打断触发条件，摘自 `interruption.py:on_speech_start`：

1. 当前 `IDLE` → 切 `COLLECTING`，不打断（首次说话）
2. 否则检查 `interval = 当前时间戳 - last_speech_end_time`，`interval < min_interval_ms(默认500ms)` → 不触发（防连续误判）
3. `should_interrupt()`：仅当当前态在 `{PROCESSING, RESPONDING}` 且 `enable_interruption=True` 才允许
4. 触发 `InterruptionEvent`（`confidence=1.0`，基于 start 事件固定），切 `COLLECTING`

**授粉到 NEKO**：NEKO 在播 TTS 时（对应 RESPONDING），用户插嘴（VAD start + interval 达标）→ 立即停 TTS、切到听。这个序列不用改，直接抄。唯一要补的是「停 TTS」这个动作——cascade 只管判定，不管停流（它把停流交给上层）。

---

## 五、难度 × 收益

| 授粉项 | 难度 | 收益 | 建议 |
|---|---|---|---|
| `SystemState` + `InterruptionManager` 逻辑 | **低**（纯 Python，无硬件依赖，~200 行） | **高**（补齐对话状态机 + 打断能力） | **立即授粉**，抄进 M3 状态管理 |
| 「物理事实优先」卫兵 | **低**（一个 if 判断） | **高**（防状态劫持，零成本） | **立即授粉** |
| `VADStateMachine` + `SpeechCollector` | 中（依赖 silero-vad + torch） | 中（端侧 VAD，云服无 mic 场景用不上） | 暂缓，记架构 |
| 1:1:1:1 无锁架构 | 中（需重构并发模型） | 中（rf_brain 实例隔离已部分实现） | 参考，不照搬 |

**总评**：cascade 的 84★ 值在「打断状态机的判据」和「物理事实优先的卫兵」，这两处是纯逻辑、零依赖、可直接抄，是本次低星扫货里「性价比最高」的授粉点。VAD 模型本身（silero-vad）反而不是重点——云服场景没有麦克风，端侧 VAD 是手机/K40 的事。

---

## 六、可执行验收（可 grep / assert）

```bash
# 1. 本报告含三大件（工单验收）
grep -c "源领域" docs/cascade-授粉报告.md        # ≥1
grep -c "数据结构共鸣" docs/cascade-授粉报告.md   # ≥1
grep -c "难度 × 收益" docs/cascade-授粉报告.md    # ≥1

# 2. 授粉引用到真实源码文件
grep -c "interruption.py" docs/cascade-授粉报告.md    # ≥2
grep -c "processor.py" docs/cascade-授粉报告.md       # ≥1

# 3. 不碰主流程（本报告只落 docs，无代码改动）
git diff --stat -- NEKO apiserver | wc -l              # 0
```

---

*授权：MIT → 主仓 AGPL v3 允许直接吞。本报告仅授粉，不拉源码进主仓（源码归档在 github_haul/fusion/cascade/）。*
