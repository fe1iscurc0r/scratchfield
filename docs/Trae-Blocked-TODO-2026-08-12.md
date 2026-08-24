# Trae 自主执行 — TODO 扫描结果 & 阻塞清单

> 来源：工单4（Trae 批量工单 2026-08-12）
> 执行人：林楠（Trae IDE）
> 日期：2026-08-12
> 原则：能做的直接做；不能做的（架构级 / 需外部需求 / 需网络）汇总到本清单。

---

## 一、扫描范围

对 `scratchpad/` 全库做了 `TODO | FIXME | HACK | XXX | 待办 | 待做` 扫描，覆盖 `*.py / *.md / *.js / *.ts`。

---

## 二、可独立完成 ✅（本次已做 / 已归入他项工单）

> 扫描结果中绝大多数 TODO 位于 **NEKO 子仓库、`vendor/`、`skills/` 模板**，是模板占位或注释性说明，**不属于可独立执行的代码缺陷**，且工单明确「不要删文件、不要改架构」，故不在此列。

无独立可执行项（功能性 TODO 均归入下方阻塞清单）。

---

## 三、留给沈遥的阻塞清单 🔴

| # | 位置 | 类型 | 说明 | 阻塞原因 |
|---|------|------|------|---------|
| 1 | `voice/input/voice_realtime/adapters/openai_adapter.py:50` | 功能 stub | OpenAI 实时语音适配器是 stub，未实现底层客户端（`connect()`/`disconnect()`/`is_active()` 均返回默认值） | 需真实 OpenAI Realtime API 对接 + 需求确认 |
| 2 | `apiserver/routes/lumo_event.py:164,207` | 架构级 | `[TODO M3.1]` 投递到陆墨决策回路，当前仅审计日志 | 架构变更（M3.1 决策回路），工单禁止改架构 |
| 3 | `NEKO/main_routers/workshop_router/publish.py:184` | 临时阻止 | 临时阻止重复上传，等待创意工坊作者验证机制 | 需作者验证机制实现，属 NEKO 子仓库 |
| 4 | `NEKO/main_routers/workshop_router/items.py:601` | 功能 TODO | wrapper 待实现 `GetQueryUGCPreviewURL` 后填充 preview_url | 需上游 wrapper 能力 |
| 5 | `NEKO/main_routers/vrm_router.py:767` | 注释 | `model_name` 参数未使用，模型相关表情待实现 | 属 NEKO 子仓库功能 |
| 6 | `NEKO/brain/computer_use.py:744` | 功能 | 光圈暂未实现 | CUA 功能增强，非本次范围 |
| 7 | `NEKO/utils/config_manager/core_config.py:1348,1731` | 架构级 | `api_type='local'` TODO 未实现本地推理 | 架构变更 |
| 8 | `NEKO/plugin/plugins/galgame_plugin/models/config.py:166` | 重构 | `rapidocr_model_cache_root` 待重命名 | 重构项，留待统一处理 |
| 9 | `NEKO/plugin/plugins/galgame_plugin/textractor_support.py:32` | 功能 | Textractor 镜像安装待验证 | 需网络 + 镜像源确认 |
| 10 | `NEKO/main_logic/omni_realtime_client/*` (多处) | 功能 | 更多型号覆盖 / 双向通道延后 | 属 NEKO 实时链路增强 |

---

## 四、结论

- 本次扫描**未发现可独立完成的代码缺陷修复**。
- 10 项功能/架构 TODO 全部归入阻塞清单，等待沈遥裁决。
- 主干 Scratchpad 代码（`apiserver/mcpserver/agentserver/voice/rag` 等）**无功能性 TODO**，代码质量良好。

<!-- 完成后由沈遥逐项裁决，打勾或关闭 -->