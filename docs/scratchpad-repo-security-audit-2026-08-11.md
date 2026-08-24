# scratchpad 仓库只读代码审查报告

**审查范围**：`tools/` 下 14 个 PE/反汇编分析脚本 + 仓库根目录 11 个散落脚本（均为存量已提交代码，本次未做任何修改）

---

## Critical（致命）

未发现致命问题（无 subprocess 注入、无即时崩溃级缺陷，与此前 tools/ 安全审查结论一致）。

---

## High（高危）

### 1. route_map.py 硬编码 Bearer Token（已提交进 git）

**位置**：`route_map.py` L30-L33

**问题**：第 32 行硬编码了一个 43 字符的 access_token：

```python
token = "Nncpb125Lobq2BvAfqezCQZCk6yt6UA2l07HwZio0BA"
```

该文件已被 git 跟踪（`git ls-files` 确认）。这是全仓库范围内唯一一处真实形态的硬编码凭据（与 `.lumo_token` 当前值不同，疑似历史登录态导出的 token）。即使已过期，凭据进入版本历史本身就是泄露，且无法确认服务端是否已吊销。

**修复**：
- 从文件中删除该 token，改为从环境变量读取（参考 `import_from_starowner.py` 的 `SCRATCHPAD_TOKEN` 写法）
- 同时确认服务端已吊销该 token
- 若仓库曾推送到远端，需考虑清理历史

### 2. main.py 自动更新/重启路径存在确定性缺陷

**位置**：`main.py` L628-L693

**问题**：`check_and_update_if_needed()` 有多个叠加缺陷，在"距上次检测 ≥5 天且 passed=True"时必然触发：

- **update.py 不存在**：仓库根目录没有 `update.py`（全仓 glob 仅 vendor 内有一个同名无关文件）。代码走到 L674 打印"跳过更新"后，L676-687 仍会无条件执行：重置 `passed=False` → 重写配置 → `os.execv` 重启。即打包用户每 5 天会被无意义重启一次并强制重跑环境检测。

- **更新失败也照样重启**：`result.returncode != 0` 的分支（L671-672）只打印警告，随后同样落入重置+重启逻辑。

- **打包环境下重启必然失败**：L687 `os.execv(sys.executable, [sys.executable] + sys.argv)`。PyInstaller 冻结环境中 `sys.argv[0]` 就是 exe 路径，导致子进程 argv 中出现重复的 exe 路径作为多余位置参数，argparse（L768-774 未定义任何位置参数）会报 "unrecognized arguments" 直接退出——"重启"实际变成"启动失败"。开发环境（`sys.argv[0]="main.py"`）反而能正常工作，问题被掩盖。

- **附带损伤**：L641-642 用 json5 读入，L679-681 用 json.dump 写回，config.json 中的注释会被静默丢弃。

**修复方向**：

```python
if not os.path.exists(update_script):
    print("⚠️ update.py 不存在，跳过更新")
    return False          # 不重置 passed、不重启
# ...
if result.returncode != 0:
    return False          # 更新失败时保留状态，不重启
# 重启改用：
os.execv(sys.executable, [sys.executable] + sys.argv[1:] if IS_PACKAGED else [sys.executable] + sys.argv)
```

（冻结环境应传 `[sys.executable] + sys.argv[1:]`；写回配置建议保留 json5 序列化或仅改动最小字段。）

---

## Medium（中等）

### 3. build.py tar 解压无路径穿越防护

**位置**：`build.py` L345-L369

**问题**：`_extract_prefixed_tarball` 只校验 `member.name.startswith(prefix)`，随后 `target = target_root / rel` 直接写文件。若归档中存在 `python/../../evil` 这类成员（前缀校验可通过），rel 含 `..` 会写出 target_root 之外。下载源是 nodejs.org / astral-sh 官方 HTTPS 地址，被投毒概率低，故定 Medium 而非 Critical；`extract_uv_runtime`（L1504-1511）因先取 basename 再 extract，反而安全。

**修复**：写入前校验规范化后的路径仍在目标目录下：

```python
target = (target_root / rel).resolve()
if not target.is_relative_to(target_root.resolve()):
    continue
```

### 4. importknowledge.py 后端不可达时以退出码 0 退出

**位置**：`_import_knowledge.py` L260-L265

**问题**：健康检查失败时 `sys.exit(0)`，对任何把该脚本纳入自动化/CI 的场景都会误判为成功。

**修复**：改为 `sys.exit(1)`。

---

## Low（低 / 建议清理项）

| # | 位置 | 问题 |
|---|------|------|
| 5 | 根目录 | **混入多个一次性调试脚本，建议归置**。`debug_api.py`、`check_ports.py`、`check_import.py`、`route_map.py`、`test_m4_speak.py` 这 5 个均为临时探测脚本（硬编码 127.0.0.1:8000/48911、无参数化、无文档头说明保留原因），与正式入口/构建脚本混在根目录。建议移入 `tools/debug/` 或在文件头加"一次性脚本"注释；`debug_api.py`、`check_ports.py` 价值最低，可直接删除。 |
| 6 | `main.py` L753-L761 | **死代码 LumoAdapter**。`LumoAdapter.__init__` 里 `s.lumo = n`，而 `n` 在 `_lazy_init_services` 中被固定赋为 None（L708，conversation_core 删除后的残留）；`respond_stream` 调用 `s.lumo.process()` 必然 AttributeError。全仓 grep 确认无任何调用方——纯遗留死代码。建议连同 L698 的 `global ... n` 一起删除。 |
| 7 | `main.py` L16-L17 | **相对路径 chdir 时机不当**。`if os.path.exists("_internal"): os.chdir("_internal")` 在 frozen 检测之前、以相对路径执行。若打包程序被从非 exe 目录拉起，找不到 `_internal`（静默失败）；若开发目录恰好存在同名文件夹则会错误 chdir。建议改为基于 `os.path.dirname(sys.executable if IS_PACKAGED else __file__)` 拼绝对路径，并移入 IS_PACKAGED 分支内。 |
| 8 | `tools/pe_analyzer.py` L305-L322 | **字符串分类存在不可达分支**。`com_ports` 分支（L321，`re.match(r'^COM\d+')`）永远不可达——前面的 `serial_port` 分支关键字列表含 `'com'`（大小写不敏感），COM1 类字符串会先被其捕获。建议把 com_ports 判断提前到 serial_port 之前，或从 serial_port 关键字中移除 `'com'`。 |
| 9 | `clear.py` | **删除范围安全，但依赖 CWD**。删除目标为 4 个固定名称（py3119/、使用必看说明.txt、启动.cmd、.is_package），无通配、无递归扩散，范围本身安全；但全部是相对路径，从其他目录运行会静默"清理不到"或清理错地方。建议改为相对脚本所在目录或显式参数传入目标目录。 |
| 10 | `tools/` 全部 | **硬编码本机绝对路径**。tools/ 下所有脚本硬编码 `d:\my git\...` 输入/输出路径。作为本机逆向工具可以接受，但换机器/换盘符即全部失效。建议抽一个 `tools/_config.py` 或统一用环境变量/相对仓库根路径。 |

---

## 总体质量结论

根目录散落脚本的质量明显参差：`main.py` 的启动主流程健壮（端口清理、重试、优雅关闭都有兜底），但 5 天自动更新这一冷门路径是确定性坏的（update.py 缺失 + 冻结环境 argv 重复），且 `route_map.py` 中有一处已提交的硬编码 token，这两项应优先处理。

`build.py` 整体工程质量高，仅 tar 解压缺路径穿越防护一处防御性缺口。

`tools/` 的 14 个逆向脚本均为只读静态分析、无注入风险，逻辑上只有 `pe_analyzer.py` 一个不可达分类分支这类小瑕疵，主要债务是硬编码绝对路径和一次性调试脚本未归置。

---

*报告生成时间：2026-08-11 | 审查模式：只读*
