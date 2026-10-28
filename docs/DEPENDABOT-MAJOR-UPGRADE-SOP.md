# dependabot 主版本升级预审 SOP

> 工单 228 任务二产出 · 2026-10-13
> 适用：dependabot 抛出的**主版本跳跃** PR（如 `pillow 11 → 12`、`pandas 2.3 → 3.0`）。
> 目的：把"4 个主版本 PR 一起卡在 review"变成一条**可复用的预审流水线**。

---

## 0. 为什么需要这条 SOP

patch / minor 升级基本可以「CI 绿了就合」。**主版本跳跃不行** —— 它会引入破坏性变更，
而本仓的 CI 闸门默认是 **skipped**（`ENABLE_*` 未开，见 `.github/workflows/ci.yml`），
也就是说**没有自动信号**告诉你"这个升级把哪条链路打断了"。

所以主版本 PR 的预审必须**人工 + 工具**走一遍，产出可核对的落点清单与试跑记录。
缺了这一步，代价是在某次发版时才炸——归因成本高一个数量级。

---

## S1 · 落点扫描（先知道"这个库在本仓哪里被用"）

工具：`tools/deps_audit.py`（本工单新建）。它优先调 ripgrep，**rg 缺失时回退纯 Python 扫描** ——
两条路径产出同一份数据结构（本机实测：无 rg，回退生效）。

```bash
python tools/deps_audit.py pandas
python tools/deps_audit.py anthropic --roots apiserver tests
python tools/deps_audit.py pillow --no-write          # 只打印
python tools/deps_audit.py numpy --no-rg              # 强制纯 Python
```

产物：`docs/audit/<lib>-<YYYY-MM-DD>.md` + 同名 `.json`（双格式）。

**扫描口径**与仓库 CI 对齐：跳过 `NEKO / vendor / build / dist / frontend / research / HamLog`
（与 `pyproject.toml` 的 ruff `exclude`、pytest `norecursedirs` 同源）。
这很重要 —— **上游 NEKO 的 import 不算本仓落点**，否则数量会失真。

同时会列出 `tests/` 中「提到该库 + 含 mock/patch」的行：**这些是升级时最容易炸的地方**
（mock 的返回值形状通常绑定旧版 API）。

---

## S2 · 行为差异表（把"破坏性变更"对齐到本仓交集）

从**官方迁移指南**抽 3-5 条**与本仓交集最大**的破坏性变更，写成 `before → after`。

### 模板

| # | 变更 | before（旧版写法） | after（新版要求） | 本仓是否踩 |
|---|---|---|---|---|
| 1 | … | `…` | `…` | 是/否（S1 落点 N 处） |

### 本轮 4 个待审 PR 的候选条目

> ⚠️ 下表是**预审候选**，不是结论。条目须在 S3 试跑时以**实际报错**为准逐条确认/划掉 ——
> 凭指南臆断"会踩"和"不会踩"都不可信。

**PR#257 pillow 11 → 12**

| # | 变更 | before | after |
|---|---|---|---|
| 1 | 废弃的图像常量/模式别名移除 | `Image.ANTIALIAS` 等 | 用 `Image.Resampling.*` |
| 2 | `ImageDraw` 文本尺寸接口 | `draw.textsize()` | `draw.textbbox()` / `textlength()` |
| 3 | 插件加载更严格 | 宽松导入插件 | 需显式注册/路径合法 |

**PR#260 fastapi 0.115 → 0.142**

| # | 变更 | before | after |
|---|---|---|---|
| 1 | 启动/关闭钩子 | `@app.on_event("startup")` | `lifespan=` 上下文 |
| 2 | pydantic v1 兼容层 | `pydantic.v1` shim | v2 原生模型 |
| 3 | `Response` 参数签名微调 | 位置参数 | 关键字参数 |

**PR#262 pandas 2.3 → 3.0**

| # | 变更 | before | after |
|---|---|---|---|
| 1 | Copy-on-Write 默认开启 | `df[...] = …` 就地改 | 显式 `.copy()` / 链式赋值失效 |
| 2 | 默认字符串 dtype | `object` | `str`（PyArrow-backed） |
| 3 | 废弃 API 移除 | `DataFrame.append` / `inplace=` 部分 | `pd.concat` / 重新赋值 |

**PR#263 anthropic 0.94 → 1.11**

| # | 变更 | before | after |
|---|---|---|---|
| 1 | client 初始化收紧 | `Anthropic(api_key=…)` | `Anthropic()`（env-only）；sync/async 分离 |
| 2 | `max_tokens` 必填 | 可省略 | **必填** |
| 3 | `system` 提顶层 | 塞在 `messages` 列表内 | 顶层 `system=` 参数 |
| 4 | `messages[].content` 类型 | 仅 `str` | `str` 或 list-of-blocks |

> 第 4 项与本工单任务三直接相关：`mcpserver/llm_gateway/anthropic_compat.py` 就是为它写的
> 兼容层 PoC（**不替换现有调用点**）。

---

## S3 · 试跑（唯一可信的一步）

```bash
# 落点双验证：版本 + 全量测试
python -c "import <pkg>; print(<pkg>.__version__)"
PYTHONPATH=<仓根> python -m pytest tests/ -q
```

记录 **rc + 首次报错的完整原文**。只有这一步能回答"到底踩没踩 S2 的哪几条"。

⚠️ **本仓试跑注意**：

- `pytest` 必须从**仓根**跑（`conftest.py` 依赖 cwd 进 `sys.path`；CI 干净环境另有 `_spec_missing`
  兜底，见 `tests/conftest.py` 头注）。
- 本机若为长期脏工作区，试跑失败**未必**归因于本次升级 —— 先在干净检出上复现基线。
- 主版本升级 PR 常需要 `uv.lock` 同步（本仓用 uv），锁文件不同步会得到与升级无关的报错。

---

## S4 · 决策矩阵

| 落点数 | 试跑结果 | 动作 |
|---|---|---|
| < 5 | 全绿 | ✅ **直合** |
| ≥ 5 或 ≥ 1 个测试红 | — | ⚠️ **留评论给 Trae 拆迁移 PR**（不要硬合） |
| ≥ 20 | 任意 | 🛑 **走 `v5.x.0` 升级路线**（当发版级变更处理，配迁移文档） |

阈值来源：`tools/deps_audit.py` 的 `THRESHOLD_DIRECT=5` / `THRESHOLD_SPLIT=20`，
markdown 报告里会直接打印本库落在哪一档。

---

## 本轮实例（工单 228 任务二 · 2026-10-13）

本轮 4 个主版本 PR：**#257 pillow / #260 fastapi / #262 pandas / #263 anthropic**。

处理顺序建议：**先 anthropic**（已有任务三的兼容层 PoC 打底，最可能一次过），
再 pillow → fastapi → pandas（落点通常递增，pandas 3.0 的 CoW 变更面最大）。

每个 PR 的 PR 描述里按下面模板贴实录：

```markdown
### 预审实录
- S1 落点：`python tools/deps_audit.py <lib>` → N 处（详见 docs/audit/<lib>-<date>.md）
- S2 交集条目：第 X / Y 条（其余判为不踩，理由：…）
- S3 试跑：`pytest tests/ -q` → rc=0，耗时 Xs（或首次报错原文 …）
- S4 结论：<✅ 直合 / ⚠️ 拆迁移 PR / 🛑 走 v5.x.0>
```

---

## 附：常见坑

1. **把上游 NEKO 的 import 算成本仓落点** —— 会导致落点数虚高、误判进 ⚠️ 档。
   `deps_audit.py` 已默认跳过，手工 rg 时务必带同样的 exclude。
2. **只看 `import X` 不看 `from X import y`** —— 后者才是破坏性变更最容易命中的形式。
   `deps_audit.py` 两种都扫，且做了 `pandasaurus` 这类**前缀相似**的负例测试。
3. **mock 未同步** —— 测试绿是因为 mock 替掉了真实调用；升级后 mock 形状过期，
   测试仍绿但线上炸。这就是 S1 要单独列 mock 点的原因。
4. **rg 与纯 Python 扫描结果不一致** —— rg 默认尊重 `.gitignore`，会漏掉被 ignore 的文件。
   `deps_audit.py` 加了 `--no-ignore` 保证与 Python 路径一致（有测试守着这条不变量）。
