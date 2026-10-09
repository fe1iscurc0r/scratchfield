# LLM 降级 Playbook（工单210 任务二）

> 日期：2026-10-08 ｜ 配套工具 `tools/switch_llm_provider.py`（已实跑验证）
> ⚠️ **工单预设的 `~/.hermes/config.yaml` 在本机不存在**（实测 2026-10-08）。
> 真实生效配置 = `system.config.get_config_path()` → `D:\my git\scratchpad\config.json`，
> 字段在 `api.{base_url, model, provider, api_key}` + `api.use_gateway`。

---

## 0. 实测现状（决策树的起点）

```
api.base_url    = https://tokenrhythm.studio/v1     ← 网关
api.model       = deepseek-v4-pro-0813
api.provider    = openai
api.use_gateway = True
api.api_key     = sk_tr_…（49 字符）
computer_control.model     = deepseek-v4-flash-0731
computer_control.model_url = https://tokenrhythm.studio/v1
```

**连接性实测**：`GET https://tokenrhythm.studio/v1/models` → **HTTP 200 OK**（真实验证，非推断）。
`GET https://open.bigmodel.cn/api/paas/v4/models`（用现有 key）→ **HTTP 401**（不是 GLM 的 key）。

⭐ **因此：GLM 订阅到期对本机现行链路无影响**（详见 `glm-expiry-audit-2026-10.md`）。

---

## 1. 决策树

```
【现状】tokenrhythm 网关 + deepseek-v4-pro（已实测 200）
   │
   ├─ 网关正常 ──────────────────────────────► 无需动作
   │
   ├─ 网关不可用（401/超时/DNS）
   │     │
   │     ├─ 有 DeepSeek 官方 key ──► 切 deepseek 直连
   │     │      python tools/switch_llm_provider.py deepseek --probe
   │     │
   │     ├─ 无 DeepSeek key，有 MiniMax key ──► 切 minimax
   │     │      python tools/switch_llm_provider.py minimax --probe
   │     │
   │     ├─ 有 GLM key 且订阅仍有效 ──► 切 zhipu（兜底回原路）
   │     │      python tools/switch_llm_provider.py zhipu --model glm-4.7-flash --probe
   │     │
   │     └─ 都不可用 ──► 降级"纯列表模式"
   │            · 关闭 proactive（config.bus.scheduler 停订阅 5m 档）
   │            · agent 循环不发起 LLM 调用，只做工具直调 + 结果罗列
   │            · 影响面：见 §3 能力敏感点
   │
   └─ 回滚：任意时刻
          python tools/switch_llm_provider.py --list-backups
          python tools/switch_llm_provider.py --restore <备份文件名>
```

---

## 2. 命令速查（全部实跑验证过）

| 目的 | 命令 |
|---|---|
| 看当前配置 | `python tools/switch_llm_provider.py --show` |
| 看有哪些预设 | `python tools/switch_llm_provider.py --list` |
| 预演（不落盘） | `python tools/switch_llm_provider.py deepseek --dry-run` |
| 切换（自动备份 + 原子写） | `python tools/switch_llm_provider.py deepseek` |
| 切换并探测连通性 | `python tools/switch_llm_provider.py deepseek --probe` |
| 换 key（从环境变量） | `DEEPSEEK_API_KEY=sk-… python tools/switch_llm_provider.py deepseek --set-key-from-env` |
| 列备份 / 回滚 | `--list-backups` / `--restore <bak>` |

**工具行为**：只改 `api.{base_url, model, provider}`（**默认不动 api_key**）；改前备份
`config.json.bak.<UTC>`；写盘复用 `system.config.atomic_write_json`（原子 + 失败显式抛出）；
探测失败 → 打印 `FAIL` 并 **exit 1**（已验证）；参数错 exit 2；配置不可读 exit 3。

**实跑证据（在临时副本上做的往返，未动你的运行配置）**：

```
tokenrhythm → deepseek：base_url/model 已改，备份 .bak.20261008T070105Z
deepseek    → zhipu(glm-4.7-flash)：备份 .bak.20261008T070106Z
探测 tokenrhythm → OK (HTTP 200)    ｜ 探测 zhipu 端点 → FAIL (HTTP 401)，exit=1
--restore 最早备份 → 回到 tokenrhythm ✓
```

> ⚠️ **我没有改你的运行配置**：现行配置走网关（实测 200），把它切到 zhipu 是**降级**且订阅将到期。
> 需要真切换时跑上面那条命令即可（会自动备份）。

---

## 3. 能力敏感点（降级后哪些会降质）

### 3.1 ⭐ **原生 function calling 是最大风险面**

`apiserver/llm_service.py` 走**原生 tool calling**（`tool_calls` 增量拼接、`parallel_tool_calls`，
见 :144 / :323 / :462 / :466-493）。不同 provider 的 function-calling **方言不同**
（有的要 `extra_body` 修方言 —— NEKO 上游就有专门的方言表）。**切 provider 后必须实测工具调用**，
否则会静默退化成"模型只会说不会调工具"。

→ 冒烟：切完跑一次带工具的对话（如 `analyze_signal` / 论文检索），确认 `tool_calls` 有回。

### 3.2 定时/流水线任务

| 任务 | 位置 | 降级影响 |
|---|---|---|
| 调度心跳（5m / 1h 档） | `config.bus.scheduler.ticks`（默认 `["5m","1h"]`），`apiserver/event_bus/scheduler.py` | 本身不需 LLM；但 proactive 订阅 5m 档 → **纯列表模式下应停订阅**，否则空转 |
| proactive（主动搭话） | `lumo_proactive.on_scheduler_tick` | 依赖 LLM 生成 → 降级后关掉 |
| 论文授粉流水线（周频） | `docs/pollination/plans/weekly_pollination.md` | 依赖**长上下文**（读多篇摘要）+ 结构化输出 → **换 provider 需核对上下文窗口** |
| computer_control（屏幕理解） | `ComputerControlConfig`（现 deepseek-v4-flash） | 依赖**多模态/视觉** → 换 provider 必须确认有 vision 能力 |

### 3.3 ⚠️ 未验证的交互点（必须说清）

- **`api.use_gateway = True` 与 `base_url` 的关系我没实测**：切到直连 provider 时是否需要同时关掉它？
  本工具**默认不动** `use_gateway`（不发明语义）。**若切换后发现不生效，先查这个字段**。
- 各 provider 的**实际可用模型名**未逐个验证（预设里的名字取自 NEKO 上游 `api_profiles.py` 与工单；
  切完用 `--probe` 只能验端点连通，**不能验模型名有效**）。
- **未测端到端**：切换后跑一次真实对话/工具调用（需要你确认可切生产）。

---

## 4. 一页摘要（贴墙版）

1. **先看**：`--show`（现行是 tokenrhythm 网关 + deepseek）。
2. **GLM 到期 ≠ 出事**：运行时不走 GLM（实测）。
3. **唯一真风险**：`openclaw/installer.py` 默认模板写死 `zai/glm-4.7` → **新装实例**会拿到失效模型。
4. **要换 provider**：`switch_llm_provider.py <name> --probe`，失败会 exit 1；回滚 `--restore`。
5. **换完必须测**：① 工具调用（function calling）② 若用电脑控制则测视觉 ③ 论文流水线的上下文够不够。
6. **没验证的**：`use_gateway` 语义、模型名有效性、端到端质量 → 别当成已验证。
