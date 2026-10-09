# GLM 到期影响审计（工单210 任务一）

> 日期：2026-10-08 ｜ 复现：
> `CODEBUDDY_SAFE_DELETE_ENABLED=0 .venv/Scripts/python.exe tools/scan_llm_providers.py --json out.json`
> 匹配模式：`open.bigmodel.cn` / `bigmodel` / `zhipu` / `glm[-_]` / `\bGLM\b`（大小写不敏感，排除 NEKO/frontend/.venv/第三方）

---

## 0. ⚠️ 首要结论：**本机现行运行时根本不是 GLM**

工单前提是"GLM coding 订阅约 10-10 到期 → 做应对手册"。**实测该前提在本机不成立**：

```
get_config_path() = D:\my git\scratchpad\config.json        ← 实测生效配置
api.base_url      = https://tokenrhythm.studio/v1           ← 网关，不是 bigmodel
api.model         = deepseek-v4-pro-0813                     ← 不是 glm-*
api.provider      = openai
api.use_gateway   = True
computer_control  = enabled=True model='deepseek-v4-flash-0731'
                    model_url='https://tokenrhythm.studio/v1'
```

**含义**：GLM 订阅到期 → **对现行运行时零影响**（对话链路 + computer_control 都已走 tokenrhythm 网关 + deepseek）。
`bigmodel.cn` 在本仓只作为**代码默认值**存在，被 config.json 覆盖。

---

## 1. 全调用点表（自家代码 17 处；第三方 vendored 另列）

| # | 文件:行 | 类型 | 所在函数 | 经 config? | 判定 |
|---|---|---|---|---|---|
| 1 | `agentserver/openclaw/installer.py:87` | 模型名 | `OpenClawInstaller` | Y | 🔴 **默认模板写死 `"primary": "zai/glm-4.7"`** |
| 2 | `agentserver/openclaw/installer.py:90` | 模型名 | 同上 | Y | 🔴 同段：`"zai/glm-4.7": {` 模型回落表 |
| 3 | `agentserver/openclaw/installer.py:91` | 别名 | 同上 | Y | 🟡 `"alias": "GLM"`（展示名） |
| 4 | `agentserver/openclaw/installer.py:82` | 注释 | 同上 | Y | ⚪ `# 默认配置模板（使用免费的 GLM 模型作为兜底）` |
| 5 | `system/config.py:728` | URL | `ComputerControlConfig` | Y | 🟡 `model_url` 默认 `https://open.bigmodel.cn/api/paas/v4` |
| 6 | `system/config.py:731` | URL | `ComputerControlConfig` | Y | 🟡 `grounding_url` 默认同上 |
| 7 | `agentserver/openclaw/llm_config_bridge.py:381` | 代码 | `inject_naga_llm_config` | Y | ⚪ `elif "glm" in model_id_lower:`（模型名→provider 推导，正常设计） |
| 8 | `agentserver/openclaw/llm_config_bridge.py:382` | 代码 | 同上 | Y | ⚪ `provider_name = "zhipu"`（推导结果） |
| 9 | `apiserver/routes/voice_eln.py:144` | 代码 | `transcribe_audio` | Y | ⚪ `os.environ.get("ASR_MODEL", "koboldcpp/GLM-ASR-Nano-…")`（**本地 koboldcpp 模型，非云订阅**） |
| 10 | `voice/input/voice_realtime/adapters/local.py:31` | 模型名 | `LocalVoiceClientAdapter` | N | ⚪ 同上（本地 ASR 默认模型） |
| 11 | `apiserver/llm_service.py:316` | docstring | `stream_chat_with_context` | Y | ⚪ 文档示例 `"model": "glm-4.5v"` |
| 12 | `apiserver/routes/voice_eln.py:17` | docstring | `<module>` | Y | ⚪ 文档 |
| 13 | `agentserver/agent_server_parts/openclaw.py:558` | docstring | `openclaw_set_model` | N | ⚪ 文档示例 `"zai/glm-4.7"` |
| 14 | `agentserver/openclaw/config_manager.py:279` | docstring | `set_primary_model` | N | ⚪ 文档示例 |
| 15 | `agentserver/openclaw/instance_manager.py:1085` | 注释 | `InstanceManager` | Y | ⚪ `# …（Qwen/GLM 等）` |
| 16 | `agentserver/openclaw/instance_manager.py:1108` | 注释 | `_detect_tool_invocation` | Y | ⚪ 注释 |
| 17 | `tools/scan_llm_providers.py` | — | — | — | 扫描器自身（已排除计数） |

**第三方 vendored（单列，非本仓代码）**：`mod/sources/packages/extracted/browser-use/*`(13)、
`vendor/top5/VulnClaw/*`(9)、`vendor/top5/headroom/*`(1)、`github_haul/CLI-Anything/*`(2)。

---

## 2. 红标 / 黄标

### 🔴 硬编码绕过 config.py 的直接调用：**1 处**

**`agentserver/openclaw/installer.py:87`** —— openclaw **首次安装时的默认配置模板**写死 `"primary": "zai/glm-4.7"`：

```
82: # 默认配置模板（使用免费的 GLM 模型作为兜底）
87:     "primary": "zai/glm-4.7"
90:     "zai/glm-4.7": {
91:         "alias": "GLM"
```

**风险**：GLM 订阅到期后，**新装/重装 openclaw 实例**会把 `zai/glm-4.7` 写成主模型 →
该实例首次调用即失败（且是"兜底"位置，等于兜底本身失效）。
**已装好的实例不受影响**（配置已落盘为当时的实际值）。
**处置建议**：属**配置默认值**而非运行时硬编码 → 建议另立小单改成读 `system.config` 的 provider 表，
**本单不改**（工单要求"只做列出的改动"）。

### 🟡 走 config 但默认值是 GLM：**2 处**（低风险）

`system/config.py:728/731` 的 `ComputerControlConfig.model_url/grounding_url` 默认 `bigmodel.cn`。
**实测被 config.json 覆盖**（现为 tokenrhythm）→ 仅当删掉这两个字段时才会回落到 GLM。

### ⚪ 判定为非风险（不计入处置）

- **本地 ASR 模型**（第 9/10 条）：`koboldcpp/GLM-ASR-Nano-…` 是**本地 koboldcpp 托管的模型**，
  与 GLM 云订阅无关（且可用 `ASR_MODEL` 环境变量覆盖）。
- **注释 / docstring**（第 4/11/12/13/14/15/16 条）：零运行时影响。
- **模型名→provider 推导**（第 7/8 条）：正常设计（按模型名推 provider），不是硬编码绕过。

---

## 3. 边界（如实标注）

- 本审计是**静态扫描 + 生效配置实测**：未验证"GLM 端点此刻是否真的可用"（无 GLM 凭证，
  探测 `open.bigmodel.cn/api/paas/v4/models` 用现有 key → **HTTP 401**，见 playbook）。
- **未覆盖 NEKO / frontend / 第三方 vendored**（NEKO 单独出报告；vendored 属上游副本）。
- 扫描是**正则 + AST 分类**，不做数据流分析 → "是否经 config 间接调用"按文件级 `import system.config` 判定
  （文件级近似，不是精确的数据流追踪）。
