# WO-278 附属修复：`lifecycle.py` memory_server 降级 patch 复原（2026-10-26）

## 0. 结论

上游同步把 `main_logic/core/lifecycle.py` 里 4 处 `[local-patch] 陆墨融合` 全洗掉了，
`scripts/neko_launcher_wrapper.py` 的 fail-fast 门（`_verify_lifecycle_patch`）因此拦下启动：
源码链路的 NEKO 后端**起不来**。本提交只复原 `/new_dialog` 取数的两处异常降级，
与 wrapper 早已执行的 `_request_memory_server_*` no-op 语义对齐；真跑验收 + 破坏对照都做了。

单文件改动，与 Electron 隔离装配（`wo/278-assembly-2026-10-25`）不同子系统，单独开分支。

## 1. 现象与判定

- `scripts/neko_launcher_wrapper.py:259 _verify_lifecycle_patch()` 要求
  `inspect.getsource(lifecycle)` 中 `[local-patch] 陆墨融合` ≥ 4 处；
- 仓库 `main@bd27fd62f080` 的该文件标记数 **0**，wrapper 直接
  `FATAL: lifecycle.py local-patch missing (0/4 expected).` 并 `exit 1`；
- 去掉门也起不来：陆墨部署不启 memory_server，`session` 启动要取 `/new_dialog`，
  `httpx.ConnectError` 冒泡 → 整段启动失败（此前实测：后端十几秒后自行退出）。

## 2. 改动内容

只动两处取数，不碰其他失败面：

| 位置 | 原行为 | 现行为 |
|---|---|---|
| `_start_session_fetch_new_dialog`（~1601） | `ConnectError`/`TimeoutException` 冒泡 | `logger.warning` + `return ""`（跳过记忆对话注入） |
| 热切换段（~2726） | 同上，且 `resp` 无判空 | 两类异常 → `resp = None`；后续 `if resp is not None and not resp.is_success`、`(resp.text if resp is not None else "")` |

语义边界（刻意不做的事）：

- **只降级「服务不在 / 超时」**；非 2xx 仍按原语义抛 `ConnectionError`，不掩盖服务端故障；
- 不扩大 `except`（其他异常照旧冒泡）；
- 与上游 `lifecycle.py:733` 的 `MEMORY_SERVER_NOT_RUNNING` 分流、wrapper 对
  `_request_memory_server_*` 的 no-op patch 保持一致：memory_server 缺席在陆墨部署里是常态。

## 3. 验收（全部实跑）

起 wrapper 的正确姿势（绕开上游 `bootstrap` 的 execv 路径 bug）：

```bash
cd <repo>/NEKO/N.E.K.O
env -u NODE_OPTIONS -u ELECTRON_RUN_AS_NODE \
  LUMO_PROXY_TOKEN=<set-by-caller> LUMO_PROXY_BASE_URL=http://127.0.0.1:8000 \
  NO_PROXY=127.0.0.1,localhost,::1 \
  ./.venv/Scripts/python.exe <repo>/scripts/neko_launcher_wrapper.py
```

| 项 | 观测 | 结果 |
|---|---|---|
| 标记数 | wrapper 打印 `[wrapper] lifecycle.py local-patch verified (4/4)` | 通过 |
| 服务起来 | `GET /health` → 48911 **200**、48915 **200** | 通过 |
| 破坏对照（装回 main 版文件） | `FATAL: lifecycle.py local-patch missing (0/4 expected).`，`exit_code=1` | 按预期红 |
| 还原自证 | 还原后 `sha256 = 84bba957d707351a587b53cefa7685bd020dfad6a74cafbfd51b9dac4318cc17`，与修复版一致 | 通过 |
| 语法 | `py_compile` | 通过 |

破坏对照的做法：从 `main` 取原版 `lifecycle.py`（250653 字节，标记数 0）覆盖后跑 wrapper；
跑完立即拷回备份并用 sha256 比对，确认工作区回到修复版。

## 4. 未验 / 遗留

- **未改上游 execv 路径 bug**：用 `C:/Users/ASUS/python-sdk/.../python.exe` 起 wrapper 会走
  `launcher_core/bootstrap.py:296 _maybe_reexec_into_project_venv` 的 `os.execv`，
  在 uv trampoline 下把 `.venv\Scripts\python.exe` 当脚本参数并丢掉 `D:\my ` 前缀 → `Errno 2`。
  当前绕法是用项目 venv 解释器起 wrapper；
- 未跑完整业务回归：记忆对话注入缺失本身即预期降级，本轮只验「能起、能活」；
- 未验长跑（>90s 稳定已由装配记录的冒烟覆盖）。

## 5. 回滚

单文件，`git revert` 本提交即可；回滚后 wrapper 会重新 fail-fast（除非上游补回 patch）。
基线 `main@bd27fd62f080`，本分支只新增提交，不写 main。
