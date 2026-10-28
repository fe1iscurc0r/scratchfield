# 修复 `tests/` **收集被中断**（`test_import_starowner_utils.py` 陈旧路径假设）

> 执行：Trae（GitHub 线）｜ 日期：**2026-10-16** ｜ 基线：main `3c2fb1931d`
> 性质：**测试基建缺陷修复**（1 个文件；不加功能、不改产品代码）
> 影响面：**CI 的 smoke job 一旦打开闸门就会红** —— 且它在**收集阶段**就中断，与代码质量无关

## §0 · 一句话

一个测试文件把「**仓库根**」加进 `sys.path`，但它要导入的脚本 **12 天前已被搬到 `scripts/experiments/gitee/`**
⇒ 每次收集 tests/ 都 `ModuleNotFoundError` ⇒ **`Interrupted: 1 error during collection`**。
现已按真实落点定位，并让"以后再被搬走"退化成**跳过带原因**，而不是能中断全局的收集错误。

## §1 · 症状（可复现）

```
$ pytest -m smoke -q                    # ← 与 CI 的 smoke job 完全同一条命令
=========================== short test summary info ===========================
ERROR tests/test_import_starowner_utils.py
!!!!!!!!!!!!!!!!!!! Interrupted: 1 error during collection !!!!!!!!!!!!!!!!!!!!
1 skipped, 1571 deselected, 2 warnings, 1 error in 6.08s
```

⚠️ 注意这是 **collection error（收集期异常）**，不是"某个用例失败"：
pytest 直接**中断整轮**，所以 `-m smoke` 连一条 smoke 用例都没跑到。

## §2 · 根因（有提交史支撑，不是推测）

| 时间 | 事件 | 依据 |
|---|---|---|
| 2026-09-29 | 新增 `tests/test_import_starowner_utils.py`。**当时 `import_from_starowner.py` 就在仓库根**，所以 `_SCRIPT_DIR = dirname(dirname(__file__))` = 仓库根，**是对的** | `4b02eeee75 test(ci): 卷173-A 测试分层…` |
| **2026-10-04** | `288a4bfcc2`「**根目录工程化整理——一次性脚本归位(43py→4)**」把该脚本搬到 `scripts/experiments/gitee/` | 该文件自身的提交史（仅此一次变更） |
| 2026-10-04 → 10-16 | 测试的 `sys.path.insert(0, 仓库根)` 从此指错；`import import_from_starowner` 一直失败 | — |

**为什么失败没被吞掉**：文件里那段 `try/except ImportError` **只放过含 `"requests"` 的错误**，其余 `raise`：

```python
try:
    import import_from_starowner as S
except ImportError as e:
    if "requests" in str(e):     # 依依赖缺失 ⇒ 允许降级为 skip
        S = None
    else:
        raise                    # ← "No module named 'import_from_starowner'" 走这里 ⇒ 收集期炸
```

**为什么 12 天没人发现**：
1. **CI 的 smoke job 被闸门关着**（`if: vars.ENABLE_CI_TEST == 'true'`）⇒ 从来没真跑过；
2. 本机跑测试通常**带 `-k`/具体文件**，而 pytests 的收集错误只在**收全目录**时才暴露；
3. 244d 那次记录的是**另一件事**（见 §4）——它跑的是 9 个指定文件，没碰到这个文件。

## §3 · 改法（`tests/test_import_starowner_utils.py`）

```python
_SCRIPT_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "scripts", "experiments", "gitee")
if not os.path.isfile(os.path.join(_SCRIPT_DIR, "import_from_starowner.py")):
    pytest.skip(
        "import_from_starowner.py 不在 scripts/experiments/gitee/（可能又被搬过）"
        "⇒ 跳过 starowner utils 测试（不让它变成 collection error）",
        allow_module_level=True)
if _SCRIPT_DIR not in sys.path:
    sys.path.insert(0, _SCRIPT_DIR)
```

两处设计：
1. **指向真实落点**（并留注释写明"写于 09-29 / 搬于 10-04"这段历史，免得后人又改回去）；
2. **降级路径**：再被搬走 ⇒ `pytest.skip(allow_module_level=True)` ⇒ 该文件**跳过并打印原因**，
   而不是再制造一次全局 abort。**"判不出/找不到" 不应该等于"炸全局"**。

## §4 · 验证（改前 / 改后）

| 项 | 改前 | 改后 |
|---|---|---|
| `pytest -m smoke -q`（**CI 原命令**） | ❌ `Interrupted: 1 error during collection`；`1 skipped, 1571 deselected` | ✅ **`44 passed, 1 skipped, 1584 deselected, 6 subtests passed`**（无 error） |
| `pytest tests/test_import_starowner_utils.py -q` | ❌ 收集期就炸（0 用例） | ✅ **13 passed**（本机有 `requests 2.34.2` ⇒ 用例**真的执行**，此前连收集都到不了） |
| 行尾 | CRLF 199/199 | **CRLF 215/215、裸 LF = 0**（该文件是 CRLF，改完逐字节复核） |

> `deselected` 1571 → 1584 正是"这 13 个用例终于可被收集"的体现。

**顺带关掉一条历史遗留**：244d 报告里记的「两边都失败的 1 个既有失败」
`test_voice_realtime_import_does_not_require_qwen_optional_dependency`
在本机（`python-sdk/python3.13.2`）**是过的**（`1 passed`）⇒ 它是**环境相关**（缺可选依赖），
**不是代码缺陷**。⇒ 该项可从"待处理"里划掉。

## §5 · 对「要不要打开 CI 闸门」的影响（本单顺带纠正一条结论）

打开闸门有两个**互相独立**的拦截：

| # | 拦截 | 状态 |
|---|---|---|
| ① | **hosted runner 计费/限额未解封** ⇒ 就算代码全绿，job 也只会"未启动"地红退 | 未解决（仓库/账单侧） |
| ② | **smoke job 会在收集阶段中断**（本单修的） | ✅ **本单已修** |

⇒ 本单之前，"打开 `ENABLE_CI_TEST`" 会得到 **①+②** 双红；现在只剩 ①。
⚠️ 结论仍然不变：**别据此去打开闸门** —— ① 没解决前打开只会多一个"未启动"的红 job。

## §6 · 复现

```bash
cd frontend  # （无关，仅提示依赖无关）
python -m pytest -m smoke -q                     # 应 44 passed / 0 error
python -m pytest tests/test_import_starowner_utils.py -q   # 应 13 passed
```

> ⚠️ 判据纪律（本单实测）：`grep -c $'\r'` 在本机出现过对纯 LF 文件报满行数的假阳性，
> **行尾一律用逐字节统计**（`read_bytes()` + `count(b"\r\n")`）。
