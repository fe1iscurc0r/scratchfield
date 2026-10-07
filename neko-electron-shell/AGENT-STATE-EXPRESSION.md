# agent 状态 → 表情 映射（桌宠壳 + 总线）

工单202 任务四 · `src/agent-state-expression.js`（展示层）+ `apiserver/event_bus/agent_expression.py`（注入层）

## 是什么

把 agent 的真实状态翻译成表情信号，两条链路：

```
                            ┌─ 壳层展示（HUD / 气泡）
agent 事件 ─→ 状态机 ───────┤   motion + label（6 状态各不同，本地用，不受 NEKO 限制）
                            └─ NEKO 注入（Live2D 换表情）
                                emotion（⊆ 5 标准情绪）→ EMOTION_REQUESTED
                                → bridge.py → POST /api/lumo/emotion → NEKO
```

## 状态与映射表

| 状态 | emotion（注入用） | motion（展示用） | label |
|---|---|---|---|
| idle | neutral | idle | 待机 |
| thinking | neutral | think | 思考中 |
| working | neutral | working | 执行中 |
| wait | **surprised** | wait | 等待确认 |
| error | **sad** | error | 出错了 |
| celebrate | **happy** | celebrate | 完成 |

**为什么 emotion 收敛到 5 个标准值**（实测契约，2026-10-06）：
`NEKO/N.E.K.O/main_routers/system_router/emotion.py:401 _normalize_emotion_label`
会把任意标签（165 个别名）归一化到 `angry/happy/neutral/sad/surprised`，
且 `/api/lumo/emotion` 端点在入队前调用它（`lumo_inject_router.py`）。
**自定义标签（如 thinking）不可依赖**——会被 fuzzy 匹配改写或回落。
故状态级区分由 `motion`/`label` 承担（壳层本地展示维度）；
情绪维度上 4 个状态拿到不同情绪（≥4，满足验收）。

## 事件契约

壳层（JS）与总线（Python）共用同一套状态名。总线侧**只声明有真实来源的主题**：

| 主题（apiserver Topics） | 状态 |
|---|---|
| `lumo.user.input.received` | thinking |
| `lumo.tool.pre-execute` / `lumo.tool.guard` | working |
| `lumo.tool.post-execute`（失败判定：`status=error/failed`、`ok:false`、`error` 字段） | thinking / **error** |
| `lumo.tts.start` | thinking |
| `lumo.decision.completed` | **celebrate** |

**无来源的状态（诚实标注）**：`wait` 在 apiserver 侧没有独立主题
（confirm_gate 是 `TOOL_PRE_EXECUTE` 的 waterfall handler，不发主题）；
壳层可用 NEKO 任务态的 `blocked/clarify/confirm_required` 补齐。
`idle` 无主动信号（不注入，避免噪声）。

## 接线用法

**总线侧**（推荐主路径，鉴权 token 在 apiserver，壳层不持有）：
```python
from apiserver.event_bus.agent_expression import AgentExpressionBridge
bridge = AgentExpressionBridge(bus.emit, character_provider=resolve_neko_active_character)
bridge.on_event(topic, payload)      # → EMOTION_REQUESTED → bridge.py → NEKO
```
**开关**：`LUMO_AGENT_EXPRESSION=1` 启用（**默认关**——避免每次工具调用都注入情绪）。

**壳层侧**（本地展示）：
```js
const S = require('./agent-state-expression');
const reg = S.createSessionRegistry();
reg.apply(sessionId, msg);
const view = S.toNekoPayload(reg.dominant());                     // {state, emotion, motion, label}
const req  = S.toNekoEmotionRequest(reg.dominant(), character);   // 无角色名 → null
```

## 三条铁律

1. **不编造进度**：label 只有状态名，无百分比/阶段编号（单测钉住）。
2. **未知事件不改写状态 / 不注入**：返回原状态 + reason，绝不猜。
3. **纯函数零 IO**：可测、可回放；角色名缺失时 fail closed（返回 null 不发送）。

## 多会话聚合优先级

```
wait(5) > error(4) > working(3) > thinking(2) > celebrate(1) > idle(0)
```

## 测试

```bash
node --test src/agent-state-expression.test.js        # 15 passed
.venv/Scripts/python.exe -m pytest apiserver/event_bus/tests/test_agent_expression.py -q   # 11 passed
```

## 边界

- 只动包装层（壳层 + apiserver 总线侧）：**NEKO 上游零改动**，只消费其既有
  `/api/lumo/emotion` 契约与 `_normalize_emotion_label` 行为。
- AAAAGENT（NC 许可）未参考、未并入；设计参照 `Andersen216/dsh-whale-girl-live2d`（★24 MIT）公开状态机思路。
