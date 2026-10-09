# NEKO 上游 GLM 依赖盘存（工单210 任务三）

> 日期：2026-10-08 ｜ 复现：
> `CODEBUDDY_SAFE_DELETE_ENABLED=0 .venv/Scripts/python.exe tools/scan_llm_providers.py --root NEKO/N.E.K.O --json neko.json`
> 铁律：**只盘存，不改上游**（NEKO 桥不吃上游改动）。

---

## 0. 一句话结论

**NEKO 对 GLM 是「结构性依赖」（provider 表 + 方言表，设计如此），不是「硬编码绕过配置」** →
按工单口径，**没有需要标"待上游修复"的项**。工单点名担心的 `config/prompts/prompts_prologue.py` 一类
**prompt 硬编码：实测 0 命中**。

---

## 1. 总量

| 口径 | 命中 |
|---|---|
| NEKO 全部 `.py` | **536 处** |
| 其中非测试文件 | **241 处** |
| **`config/prompts/` 目录** | **0 处** ✅（无 prompt 硬编码模型名） |

## 2. 命中分布（非测试文件 Top 14）

| 文件 | 处数 | 类型分布 | 判定 |
|---|---|---|---|
| `main_logic/asr_client/workers/glm.py` | 34 | other 33 / url 1 | ⚪ 上游 **ASR provider 实现**（GLM 语音） |
| `main_logic/omni_realtime_client/_transport.py` | 32 | other 19 / comment 13 | ⚪ 实时传输层（GLM realtime 方言） |
| `utils/config_manager/voice_storage.py` | 25 | other 19 / key 4 / comment 2 | ⚪ 语音配置存储（provider 选项） |
| `main_routers/characters_router/voice_preview.py` | 22 | other 14 / key 6 / comment 2 | ⚪ 试听接口（provider 枚举） |
| **`config/providers.py`** | 17 | other 12 / url 2 / comment 3 | ⚪ **模型→extra_body 方言表**（GLM 系列 7 条） |
| `main_logic/tts_client/__init__.py` | 16 | other 9 / comment 6 / url 1 | ⚪ TTS provider 注册 |
| **`config/api_profiles.py`** | 13 | other 10 / url 2 / key 1 | ⚪ **GLM profile 定义**（URL + 各用途模型名） |
| `main_logic/omni_realtime_client/_client.py` | 10 | comment 6 / other 4 | ⚪ 客户端（方言注释） |
| `utils/voice_management/providers/glm.py` | 10 | other 8 / key 2 | ⚪ 上游 provider 实现 |
| `main_logic/omni_realtime_client/_tools.py` | 8 | other 6 / comment 2 | ⚪ 工具声明 |
| `main_logic/asr_client/__init__.py` | 6 | other 5 / comment 1 | ⚪ provider 注册表 |
| `main_logic/asr_client/_registry_meta.py` | 5 | other 4 / comment 1 | ⚪ 注册元数据 |
| `scripts/asr_realtime_smoke.py` | 5 | key 1 / other 4 | ⚪ 冒烟脚本 |
| `main_logic/tool_calling.py` | 4 | other 4 | ⚪ 工具调用方言 |

## 3. 关键条目（判"是否 prompt / 模型名 / URL"）

**`config/api_profiles.py`** —— GLM 作为**一等 provider** 的 profile：

| 行 | 内容 | 类型 |
|---|---|---|
| 77-79 | `'glm': { 'CORE_URL': "wss://open.bigmodel.cn/api/paas/v4/realtime", 'CORE_MODEL': "glm-realtime-plus" }` | URL + 模型名 |
| 144-151 | `'glm': { 'OPENROUTER_URL': "https://open.bigmodel.cn/api/paas/v4", 'CONVERSATION_MODEL': "glm-4.7-flash", 'SUMMARY_MODEL'/'CORRECTION_MODEL'/'EMOTION_MODEL': "glm-4.7-flash", 'VISION_MODEL': "glm-4.6v-flash", 'AGENT_MODEL': "glm-5v-turbo" }` | URL + 模型名 |
| 168 | `'VISION_MODEL': "zai-org/GLM-4.6V"` | 模型名 |
| 273 | `'glm': 'ASSIST_API_KEY_GLM'` | **key 环境变量名**（凭证走环境，不硬编码 key） |

**`config/providers.py:128-135`** —— GLM 系列方言映射（**模型名 → `EXTRA_BODY_CLAUDE`**）：
`glm-4.5-air` / `glm-4.6v-flash` / `glm-4.7-flash` / `glm-4.6v` / `glm-5v-turbo` / `glm-5.1` / `glm-5.2`；
另 `:147` `zai-org/GLM-4.6V → EXTRA_BODY_OPENAI`。

**其余**：`*.py` 里的 `GLM` 字样多为注释/docstring（如 `brain/openclaw_adapter.py:906`、
`config/memory_settings.py:816`、`config/providers.py:61`），**零运行时影响**。

## 4. 判定与处置

| 判定 | 数量 | 处置 |
|---|---|---|
| prompt 硬编码模型名 | **0** | — |
| provider 表 / 方言表（结构性） | 2 个文件（`api_profiles.py` / `providers.py`） | ⚪ **不处置**：上游设计；换模型时改上游配置即可 |
| provider 实现（ASR/TTS/realtime） | `asr_client/workers/glm.py` 等 | ⚪ **不处置**：可选 provider，非默认链路 |
| 注释 / docstring | 余下 | ⚪ 无影响 |
| **"待上游修复"** | **0** | — |

**为什么不标"待上游修复"**：工单的原意是"模型名字符串硬编码、没走配置" → 实测 NEKO 把 GLM 模型名
**集中放在 `config/api_profiles.py` / `config/providers.py` 两张表里**（这**就是**它的配置层），
其余散落的都是注释。**因此不存在"应该走配置而没走"的情形。**

## 5. 边界

- 只扫 `.py`；未扫 NEKO 的前端（`NEKO/N.E.K.O/**/*.ts`）与文档。
- 静态正则 + AST 分类：**未做数据流分析**，也未验证 NEKO 运行时实际选用哪个 provider
  （那是 NEKO 自己的配置，属上游）。
- **未修改任何上游文件**（符合铁律）。
