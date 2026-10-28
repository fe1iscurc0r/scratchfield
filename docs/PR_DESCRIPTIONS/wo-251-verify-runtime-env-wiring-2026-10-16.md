# WO-251 · Lumo 运行时接线 —— verify 脚本闸门（scratchfield 仓 PR）

## 目标
为 WO-251（Trae 改 `backend.ts` + `local_apps.py`）提供可脚本化验收闸门，替代人工逐条 grep / 跑。

## 本 PR 改了什么
- `scripts/verify-runtime-env-wiring.py`（新文件，~240 行）
- `scripts/verify-runtime-env-wiring.README.md`（用法文档）

**5 项检查与文件位置**（纯只读）：

| # | 项 | 查什么 | 通过条件 |
|---|---|---|---|
| 1 | 包内 runtime | `mcpserver/agent_open_launcher/local_apps.py` | 含 `def _bundled_runtime_bin(name):` |
| 2 | 本机路径硬编码 | `mcpserver/` 全树 | `trae-cn` / `python-sdk` 注释行外 0 命中 |
| 3 | 失败可诊断 | 同上 | `_start_neko_shell` 函数体内无裸 `return False` |
| 4 | 开发模式不回归 | `frontend/electron/modules/backend.ts` | `LUMO_FUSION_*` 被 `app.isPackaged` 守护 |
| 5 | 构建不回归 | `build.py` / `frontend/electron-builder.yml` | 未被本单改动 |

## 基线验证

```bash
$ python3 scripts/verify-runtime-env-wiring.py --no-color
                     陆墨运行时接线验收 · WO-250
  项目根: /home/ubuntu/scratchfield
  平台:   linux (x86_64)

  ~ 1      未在 local_apps.py 找到 _bundled_runtime_bin(name) 实现（Trae 还没改 §3.2）
  ✗ 2      本机路径硬编码仍存在 2 处: mcpserver/agent_open_launcher/local_apps.py:85: ...
  ✗ 3      _start_neko_shell 仍存在裸 return False（上下文无 reason/raise）: ...
  ~ 4      backend.ts 尚未注入 LUMO_FUSION_*（Trae 还没改 §3.1）
  ✓ 5      build.py / electron-builder.yml 未被本单改动（按 SPEC §四 边界）

FAIL  2 失败 / 2 警告 / 5 总
```

2 失败 + 2 警告 = 与 WO-251 待改项精确对齐（项 1/4 警告 = Trae 还没改；项 2/3 失败 = Trae 还没改）。

## 理想态 mock 反向验证

为了证明 verify 自身正确，我在临时 mock 脚本里：
- 注入 `_bundled_runtime_bin(name)` 函数
- 删两条本机路径硬编码
- `_start_neko_shell` 失败改 `raise RuntimeError(f'NEKO 启动失败: ...')`
- `backend.ts` 加 `if (app.isPackaged) { env.LUMO_FUSION_NODE = 'MOCK' }`

然后跑 `verify --no-color`：

```
  ✓ 1      _bundled_runtime_bin(name) 已实现（见 local_apps.py）
  ✓ 2      mcpserver/ 全树 grep trae-cn / python-sdk 0 命中（注释行不计）
  ✓ 3      _start_neko_shell 已无 return False（失败走 raise / 显式 reason 路径）
  ✓ 4      backend.ts 已注入 LUMO_FUSION_* 并被 app.isPackaged 守护
  ✓ 5      build.py / electron-builder.yml 未被本单改动（按 SPEC §四 边界）

PASS  0 失败 / 0 警告 / 5 总
```

5/5 PASS 走通，**证明 verify 脚本没有误报**。

mock 过程回滚（subprocess.run 后 finally 块回写 .orig），`git status --short` 干净。

## 下一步

- 合并本 PR → 251 工单 Trae 在 `fix/runtime-env-wiring-2026-10-16` 分支续推
- 改完后 `python3 scripts/verify-runtime-env-wiring.py --ci` 必须 5/5 PASS
- 251 改码 PR 描述里**粘贴 verify --ci 完整输出**作为证据

## 风险与回滚

- 新文件，不改任何已有代码
- 唯一风险：脚本里 regex 在生产代码重构后失效 → 维护者需要在重构时同步更新脚本
- 已经在 README §五 写明扩展约定

## 分支

`fix/runtime-env-wiring-2026-10-16` (本地 + 远端同名分支)
本地 SHA: 1b144e2153ff0f55268bb03ba08be7e0e62f343c
