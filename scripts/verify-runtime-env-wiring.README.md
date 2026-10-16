# scripts/verify-runtime-env-wiring.py · WO-250 验收用法

> 出单：沈遥 · 日期：2026-10-16 · 关联工单：scratchpad `TRAE_WORKORDER_PROMPT_AGENT_251.md`

## 一、这是什么

`scripts/verify-runtime-env-wiring.py` 是 **WO-250 验收硬线的可脚本化自检**。把 SPEC §四 的 5 条验收标准
从「人工逐条 grep / 跑」改成一键原子操作，谁改完谁跑，谁跑谁负责。

**只读不改**。CI 闸门：传 `--ci` 失败即 exit 1。

## 二、用法

```bash
# 全跑（基线：WO-250 还没落时会有 2 失败 + 2 警告 + 1 通过）
python3 scripts/verify-runtime-env-wiring.py

# CI 模式（失败即 exit 1，给 GitHub Actions 用）
python3 scripts/verify-runtime-env-wiring.py --ci

# 单项
python3 scripts/verify-runtime-env-wiring.py --only leak

# 取消彩色（CI 日志、纯文本粘贴用）
python3 scripts/verify-runtime-env-wiring.py --no-color
```

## 三、5 项验收与文件位置对齐

| 项 | 验收线 | 检查文件 | 通过条件 |
|---|---|---|---|
| 1 | 包内路径命中 | `mcpserver/agent_open_launcher/local_apps.py` | 含 `def _bundled_runtime_bin(name):` 实现 |
| 2 | 本机路径硬编码清零 | `mcpserver/` 全树 | `trae-cn` / `python-sdk` 在非注释行 0 命中 |
| 3 | 失败可诊断 | 同上 | `_start_neko_shell` 函数体内无裸 `return False`（有 reason/raise 守护） |
| 4 | 开发模式不回归 | `frontend/electron/modules/backend.ts` | `LUMO_FUSION_*` 注入被 `app.isPackaged` 守护 |
| 5 | 构建不回归 | `build.py` / `frontend/electron-builder.yml` | 未被本单改动（按 SPEC §四 边界） |

## 四、为什么是这份

写于 2026-10-16，是给 251 工单（Trae 改 `backend.ts` + `local_apps.py`）配套的验收闸门。
原本想用单元测试，但 WO-250 的本质是「包内路径 + 失败可诊断」这种**结构约束**，grep + 上下文分析
比 mock 整个打包态便宜得多。

## 五、扩展约定

未来若 WO-251 之后又加新约束（如「禁止后端模块写绝对 Windows 路径」），**继续往这个脚本里加项**，
不要另开验证脚本——单一入口便于 CI 接入和人类记忆。
