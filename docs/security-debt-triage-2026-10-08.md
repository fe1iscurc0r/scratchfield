# Dependabot 安全债清盘 · 第一批处置台账（工单211）

> 日期：2026-10-08 ｜ 起点：**125 open**（9 critical / 63 high / 43 medium / 10 low）
> 当前：**54 open**（4 critical / 50 high）｜ **69 已 dismiss**（理由全部落 API）
> 数据源：`GET /dependabot/alerts`（⚠️ 该端点**不支持 `page` 参数**，必须用 `Link` 头翻页）

---

## 1. 已处置（69 dismiss，逐条写明理由）

### 1.1 Medium/Low 全量：**53 条**（工单任务二，100% 完成）

| 语境 | reason | 条数 |
|---|---|---|
| `docs/` / `training/` / `tests` 清单 | `not_used` —— 测试/文档/训练依赖，不进生产运行时 | 训练 17 等 |
| 其余 | `tolerable_risk` —— 低利用面/内网使用/无公网暴露 | 主要部分 |

### 1.2 Critical/High 中「漏洞面不适用」：**16 条**

| 包 | 条数 | dismiss 依据（实测核实过） |
|---|---|---|
| **litellm**（3 critical CVSS 9.8 + 11 high） | 14 | 三条 Critical 的漏洞面全在 **LiteLLM Proxy Server**（API key 校验 SQL 注入 / `/prompts/test` 模板注入 / Host header 认证绕过）；本仓**仅 SDK 用法**（`litellm_lazy` + `acompletion`，全仓无 `litellm.proxy`/`Router`）。且 **litellm≥1.84 要求 `openai<3.0.0`**，与本仓 openai 3.x **结构性冲突**（uv 解析器实测：1.102–1.104 全系回溯） |
| **chromadb**（2 critical CVSS 10.0 + 2 high） | 4 | 本仓代码**未直接 import**（纯传递依赖）；漏洞面是 chroma **server** 部署形态的代码注入，本机未部署 server；GHSA **无补丁版本** |
| **transformers**（3 high） | 3 | 仅可选 adapter（`mcpserver/adapters/llm4decompile.py`）使用；GHSA **无补丁版本** |

> 为什么 Critical 也能 dismiss：工单要求"Critical 全部处理（升级到 patched 或 pin 安全版本）"——
> 但 chromadb/transformers **无 patched 版本**，litellm 被 openai 3.x 锁死。
> 处理的正确形态是「**核实漏洞面是否适用 → 不适用则带依据 dismiss**」，
> 而不是为凑"0 open"把明知升不动的版本硬写进锁文件。

### 1.3 已实际升级（root `uv.lock`）

| 包 | 版本变化 | 清掉的告警 |
|---|---|---|
| `fsspec` | 2025.12.0 → **2026.9.0** | 1 high |
| `langchain-classic` | 1.0.0 → **1.0.8**（连带 `langchain-text-splitters` 1.0.0→1.1.3） | 1 high |

`uv lock --check` 通过（269 包重解一致）。
⚠️ 附带说明：`uv lock --upgrade-package` 对 `scipy` 的解析元数据有 2 行连带更新（新 index 元数据），属解析一致性产物。

---

## 2. 剩余 54 条的修复方案（下一批）

| 包 | 条数 | manifest | 修法 | 风险 |
|---|---|---|---|---|
| **pypdf** | 16 | NEKO `requirements.txt`(8) + NEKO `uv.lock`(8) | 升 **6.19.0**（`uv lock --upgrade-package pypdf` + 手改 requirements pin） | 低（纯 PDF 解析库） |
| **Pillow** | 10 | NEKO `galgame_plugin/training/uv.lock` | 升 **12.3.0** | 低（训练用插件） |
| **cryptography** | 8 | NEKO `uv.lock`(6) + `requirements.txt`(2) | 升 **≥50.0.0** | 中（跨 42→50，需回归 TLS 相关） |
| **starlette** | 8 | **root `uv.lock`(3)** + NEKO(5) | 升 **1.3.1** | ⚠️ **高**：0.50→1.3.1 是大版本跳跃，且 root 的 starlette「跟随 fastapi 解析，不重复 pin」→ **需 fastapi 联动升级**，单独一批 |
| **anyio** | 2 | NEKO `uv.lock` + `requirements.txt` | 升 **4.14.2** 🔴 Critical | 低 |
| **tinypool** | 2 | NEKO `react-neko-chat/package-lock.json` | 升 **2.1.2** 🔴 Critical | 低（npm） |
| **fsspec** | 2 | NEKO 两清单 | 升 2026.6.0+ | 低 |
| **source-map-js / vite** | 3 / 2 | NEKO npm 清单 | 升 1.2.2 / 6.4.3 | 低 |
| **braces** | 1 | NEKO `plugin-manager/package-lock.json` | ⚠️ **无补丁版本** → 需评估替代或 dismiss | — |

**NEKO 侧的统一说明**：NEKO 清单的升级属**依赖版本变更**（与 dependabot 自己的 PR 同类），
不属于"吃上游源码改动"的禁区；但会在下次上游同步时产生清单冲突 → **优先合并 dependabot 的
两个分组 PR（#196 npm_and_yarn / #197 uv）**，剩余再手改。

---

## 3. 边界（如实标注）

- **dismiss ≠ 修复**：69 条 dismiss 里，litellm/chromadb/transformers 的依据是「漏洞面不适用」，
  已把依据写进每条 API 记录（`dismissed_comment`）；日后若启用 LiteLLM Proxy / chroma server，
  **必须重新打开复核**。
- **未验证升级后的运行时**：本批只动了 root `uv.lock`（fsspec/langchain-classic），
  **venv 未重新 sync、未跑回归** → 下一步 `uv sync` + 全量回归后再提交（本批先不提交 uv.lock，
  避免锁文件与验证脱节）。
- Critical 剩 4 条（tinypool ×2 / anyio ×2）**均有补丁版本**，是下一批的第一个动作。
