# `create_agent_instance` 的错误处理器加固 —— 别让"报错的代码"自己先崩

> 执行：Trae（GitHub 线）｜ 日期：**2026-10-16** ｜ 基线：main `c9658686bf`
> 性质：**健壮性修复**（1 行逻辑 + 注释；1 个新回归测试文件）
> ⚠️ 如实定位：这是**公共 API 的健壮性瑕疵，不是活 bug** —— 生产路径已查证**不可达**（见 §2）

## §0 · 一句话

`mcpserver/mcp_registry.py::create_agent_instance` 的 `except` 处理器里写了
``manifest.get('displayName', 'unknown')`` —— 当 `manifest is None` 时**处理器自身会再抛
AttributeError**，把真实异常掩盖成 `'NoneType' object has no attribute 'get'`。
修法一行：`(manifest or {}).get(...)`。

## §1 · 发现过程（不是拍脑袋，是真踩到）

给 `tests/test_import_starowner_utils.py`（另一单）排查时，为了测 `create_agent_instance`
对一个手拼的 manifest 路径的行为，传了一个 `load_manifest_file()` 返回 `None` 的入参 ⇒

```
File "mcpserver/mcp_registry.py", line 295, in create_agent_instance
    logger.warning("创建agent实例失败 %s: %s", manifest.get('displayName', 'unknown'), e)
AttributeError: 'NoneType' object has no attribute 'get'
```

真实异常（`_resolve_entrypoint` 里的）被**掩盖**了 —— 排查者看到的是处理器自己崩的栈。

## §2 · 可达性查证（这一步决定它是不是"活 bug"）

| 调用路 | 守卫 | 结论 |
|---|---|---|
| `ensure_hot`（冷表转热，L71） | `manifest = cold.get("manifest") or MANIFEST_CACHE.get(...) or {}` —— **已有 `or {}`** | 不可达 |
| `scan_and_register_mcp_agents`（L422） | `if not manifest: continue` | 不可达 |
| `_COLD_TABLE` 的写入点（L414 / L462） | 只由上述两条路写入，manifest 必为真 | 不可达 |

⇒ **生产不可达**。但该函数在 `__all__` 里是**公共 API**（第 806 行），任何直接调用方
（工具 / 排查脚本 / 未来代码）都可能踩到 —— 本单就是活例。
⇒ 定性为**健壮性修复**，不是行为变更：对**真值** manifest，`(manifest or {})` 与
`manifest` 完全等价，日志输出一个字都不变。

## §3 · 改法（1 行逻辑）

```python
     except Exception as e:
-        logger.warning("创建agent实例失败 %s: %s", manifest.get('displayName', 'unknown'), e)
+        logger.warning("创建agent实例失败 %s: %s", (manifest or {}).get('displayName', 'unknown'), e)
         return None
```

**对账证明**（补丁脚本自动断言）：全文件 **730 行可执行行，只有 1 行变化**（即上面这行），
其余逐行相同；文件保持全 LF（41134 B、CRLF=0）。

## §4 · 回归测试（新增 `tests/test_mcp_registry_none_guard.py`，3 用例）

| 用例 | 断言 |
|---|---|
| `manifest=None` | 返回 `None`（修复前：**AttributeError** —— 已实测 `_resolve_entrypoint(None)` 抛的就是它） |
| `manifest={}` | 返回 `None`（走 Format D 推导 → 导入不存在 → 错误路径） |
| 真值 manifest 但入口模块不存在 | 返回 `None`（**处理器没被改坏**：真实异常仍被正常记录） |

测试文件自带"可达性说明"，免得后人把它误读成"这里曾有活 bug"。

## §5 · 验证

| 项 | 结果 |
|---|---|
| 新回归测试 | **3 passed** |
| 注册表相邻测试（`test_mcporter_lazy.py` + `test_code_review_adapter.py`） | **21 passed** |
| `pytest -m smoke -q` | **44 passed, 1 skipped**（deselected 1584 → 1587 = 新用例被正常收集） |
| `ruff check`（两个改动文件） | **All checks passed** |
| 行尾 | `mcp_registry.py` main 真 blob 为 **LF**（本地 full/ 副本已被 archive 污染成 CRLF ⇒ **在真 blob 副本上打补丁**），落盘全 LF |

## §6 · 复现

```bash
python -c "from mcpserver.mcp_registry import create_agent_instance as f; print(f(None, 'x'))"   # ⇒ None（修复前 AttributeError）
python -m pytest tests/test_mcp_registry_none_guard.py -q    # 3 passed
python -m pytest -m smoke -q                                 # 44 passed
```
