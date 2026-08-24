# 项目长期记忆 — scratchpad (Hermes/Lumo 生态)

## 项目性质
AI 角色系统生态（Hermes/Lumo/陆墨）。核心目录：agentserver / apiserver / mcpserver / frontend / characters / guide_engine / carpet / rag / vault / vendor/top5。

## MCP 适配层模式（mcpserver/adapters/）
- 薄封装，不做业务逻辑：凭证 fail-fast + sys.path 注入 + 暴露工具
- 每个 adapter 三要素：`CAPABILITY` dict / `healthcheck()` / `register()`
- 注册：`__init__.py` 的 `_ADAPTERS` 字典加一行
- 6 步门禁：ENABLE 开关 → import → validate_adapter 契约校验 → CAPABILITY name 冲突 → healthcheck → register(带回滚)
- 公共函数：`inject_vendor_path` / `merge_tools` / `register_capability_safe`（在 `_common.py`）
- headroom.py 是最完整范本（双路径 + 退化模式）
- 现有 adapter：vulnclaw / headroom / memclaw / agent_reach

## 关键现有资产
- `mcpserver/material_science/`：完整 agent，11 工具（literature_search / property_calc含conductivity / matchat_search 28万篇论文 / formula_query / phase_diagram / crystal_info / thermal_analysis / material_compare 等）
- `skills/markitdown/`：完整 skill v2.1 + batch_convert.py + convert_literature.py
- `vendor/top5/`：VulnClaw / headroom / caura-memclaw 三大源项目
- `mcpserver/agent_llm_decompile/` + `agent_decompile/`：空壳（仅 __pycache__），待填空

## 运行时
- Python 3.13.14（managed: C:/Users/ASUS/.workbuddy/binaries/python/versions/3.13.12/）
- Node 22.22.2（managed）
- **Ollama 未安装**（截至 2026-08-09）— VLM/LLM 本地推理靶子的共同卡点

## 用户工作习惯
- 个人规划文档放桌面管理（如 Old-Target-New-Model-Plan-v1.md → v2.md 迭代）
- 项目技术规划文档放 `docs/`（如 RS-BA1-Adapter-Plan-v1.md）
- 偏好先用可视化/图给执行方向，确认后再产出完整文档
