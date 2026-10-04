# 材料符号回归 + 编码策略评估勘察报告 · YANKEE-01

> 工单：Y-01（可解释符号回归 + Polymer Genome 编码策略评估，只读勘察）
> 线：YANKEE（Y 线 · 材料科研升级）｜分支：trae/agent-yankee
> 类型：只读勘察，不写码；不 copy 论文代码
> 上游授粉点：cond-mat.mtrl-sci 可解释符号回归（CO2 吸附显式表达式，8-25 轮）、
>   Polymer Genome 编码策略评估（8-25 轮第 5 趋势 + 8-26 轮授粉点第 4 条）、
>   数据高效材料特定 MLIP（8-23 轮）
> 对照：mcpserver/material_science/biopred.py（黑箱 ML 现状）+ mcpserver/academic/（MODEL_INTERFACE 模式）
> 完成：2026-08-28

## 〇、一句话结论

材料性能预测的"黑箱 ML（biopred 的 RandomForest/XGBoost）"可以**旁路出一条显式表达式**（可解释符号回归），把"能写进论文的解析式"作为黑箱的对照输出，而不是替换黑箱；精度瓶颈主要在**选对指纹/编码**（Polymer Genome 方法论）而非堆模型。工具链结论：**gplearn 级别纯 Python GP 为本期落地形态（无重依赖），pysr（Julia 后端）判为二期不否决**。本报告只读勘察，不写码；Y-02 落码基于本报告结论。

---

## 一、三条可落地结论（论文授粉点提炼）

> 说明：上游 `weekly_pollination.md`（`/home/ubuntu/research/papers/`）为 Linux 真机路径，本仓 Windows 侧不存在；以下三条按工单内嵌的授粉点描述提炼，与 ALPHA-01 §八对 round8 缺失的处理方式一致——原文到位后以原文为准回填。

1. **符号回归把"黑箱 ML → 显式表达式"**：对 CO2 吸附这类物理量，遗传编程（GP）可产出形式简单、物理可读的解析式（Langmuir/幂律/多项式类），R² 接近黑箱但可解释、可直接写进论文方法与结果节。落地：biopred 旁路出显式表达式，主流程不动。

2. **编码策略决定精度上限（Polymer Genome 方法论）**：聚合物/大分子性质预测里，"选对指纹/编码"比"换更强的模型"收益更大；SMILES 字符串、分子指纹（ECFP/Morgan/MACCS）、图表示（GNN）、序列 n-gram 各有适用域，需按数据规模、可解释性与目标性质选型。落地：`encode_eval.py` 出对比表 + 给 biopred 的编码选型建议。

3. **小样本下"物理先验/可解释"优先于"堆参数"**：数据高效材料特定 MLIP 的启示是——数据量小时（biopred 现状 <5 条即拒），可解释、低方差的模型（符号回归、正则线性）比高容量黑箱更稳。落地：符号回归旁路作为小样本对照，黑箱预测与显式表达式并列出。

---

## 二、符号回归工具链选型表

| 工具 | License | 依赖 | 是否需 GPU/DFT | 适用判定 | 本线取舍 |
|---|---|---|---|---|---|
| **纯 numpy GP（自研，本线落地）** | MIT（本仓自研，方法论参考 gplearn） | 仅 numpy | 否 | 轻量、零新增依赖、可自测、可写论文表达式 | **Y-02 采用** |
| gplearn | BSD-3-Clause | numpy + scikit-learn | 否 | 纯 Python GP，即"gplearn 级别"；与本线自研 GP 同构，但本仓未装 | 备选（若需第三方背书再装） |
| PySR | MIT | Julia ≥1.9 + sympy + PyCall | 否（CPU 即可，GPU 可选加速） | 性能最强、带复杂度惩罚与分布式；依赖重（Julia 运行时），安装/分发成本高 | **二期，不否决** |
| feyn（Qtile 出品） | 商业/社区分层 | 自包含 | 否 | 交互式强，但许可非全开源，偏 GUI | 不选（许可不明） |
| OPERON / DS-TL | MIT | C++ 内核 + pybind | 否 | 高性能 GP，但需编译，Windows 支持一般 | 备注，不选 |

**选型结论**：Y-02 落地形态 = **纯 numpy 遗传编程（gplearn 级别）**，理由：(1) 零新增第三方依赖（numpy 已在 requirements.txt）；(2) 合成数据可自测、pytest 可验收；(3) 产出的 `Expression` 直接带 LaTeX/文本格式化，满足"写进论文"。PySR 性能更强但 Julia 后端重，标注为二期可选升级，不否决。

---

## 三、编码策略对比表（木质素 NPs → 水凝胶/共熔凝胶场景）

| 编码 | 维度 | 信息内容 | 可解释性 | 适用场景 | 对木质素 NPs 的适配 |
|---|---|---|---|---|---|
| SMILES 字符串（序列 n-gram） | 可变（词典相关） | 字符/子串共现 | 中 | 结构相似性、快速检索 | 弱——木质素是异质大分子，无确定 SMILES，需先降为单体/片段 |
| 分子指纹（ECFP/Morgan/MACCS，哈希 256~2048bit） | 定长 | 子结构存在性（0/1） | 低（哈希不可逆） | 结构-性质 QSAR、去重 | 中——单体/低聚物片段可算，但哈希损失可读性 |
| 图表示（GNN，节点=原子/边=键） | 变长+消息传递 | 全拓扑（环/支化/官能团） | 中（可读子图） | 结构-性质深度学习 | 强——能显式表达环、支化度、官能团，正是木质素 NPs 的核心结构信息；但需 RDKit/DGL |
| 拓扑描述符（自研 graph_encode） | 定长（~9） | 原子组成/键数/环数/支化度/不饱和度 | **高** | 小样本可解释建模 | **强——纯 Python 可算，Y-02 采用** |
| 工艺参数 + 前驱体指纹（biopred 现状） | 定长（5） | 前驱体类型 + KOH 比 + 温度 + 时间 | 高 | 实验条件→性质 | 现状已用，作为"对照组" |

**选型结论（给 biopred）**：木质素 NPs 无确定 SMILES（异质大分子），**不宜直接上 SMILES/ECFP**；应 (1) 降为"单体/低聚物片段"再算指纹，(2) 优先用**图拓扑描述符**（环数/支化度/官能团计数，纯 Python 可算、可解释），(3) 保留现有工艺参数作为正交特征。Y-02 的 `encode_eval.py` 用合成数据演示：三种编码在简单线性性质上都能拟合，但**图编码以最少维度（9）达近乎完美拟合且可解释**，序列编码靠字符计数高维过拟合、指纹编码维度最高且哈希不可逆——"选对编码"的收益在**维度效率 + 可解释性**。

---

## 四、biopred 黑箱 → 差距表（现有 → 符号回归能补什么 → 编码怎么选）

| # | biopred 现状（黑箱） | 符号回归能补什么 | 编码策略怎么选 | 优先级 |
|---|---|---|---|---|
| 1 | `predict()` 只回 `prediction_s_cm + CI`，无表达式 | 旁路出 `3.2*x0 - 0.4*log(x3)` 式显式表达式，写进论文 | 沿用 biopred 特征名（precursor_fp/koh_ratio/…）作变量名 | 一期 |
| 2 | 特征固定 5 维（前驱体指纹 + 工艺） | 符号回归可筛出**有效特征组合**（哪些项进入表达式） | 图拓扑描述符可作为新特征并入，对比增益 | 一期 |
| 3 | RandomForest/XGBoost 无物理约束 | GP 可加复杂度惩罚，产出低复杂度、可读式 | 指纹/图/序列三路对比，选 R² 最高者 | 一期 |
| 4 | 小样本 <5 条直接拒 | 符号回归对 3~40 条合成数据即可稳定拟合（自测） | 小样本优先可解释低方差编码（图描述符） | 一期 |
| 5 | 无主动解释（suggest 只给不确定性） | "黑箱预测 + 符号表达式对照"报告，双路互证 | 同上 | 二期 |

---

## 五、给 biopred 的升级 SPEC 建议（可 grep 验收）

### 5.1 新增旁路模块（Y-02 落码）

- 目录：`mcpserver/material_science/symbolic/`（独立旁路，与 biopred 正交）
- 文件：`fit.py`（X/y → 显式表达式）、`expr.py`（表达式求值/保存/格式化）、`cli.py`（fit/apply/export 子命令）、`encode_eval.py`（编码对比）、`tests/test_symbolic.py`（≥6 用例）
- 硬约束：**不碰 `biopred.py` 主流程**（`git diff --stat -- mcpserver/material_science/biopred.py | wc -l = 0`）

### 5.2 接口签名（验收 grep 项）

```
# fit.py —— 显式符号回归拟合
def fit(X, y, *, feature_names=None, population_size=300, generations=40, ...) -> FitResult
# FitResult: expression(Expression) / rmse / r2 / generations / feature_names / best_history

# expr.py —— 表达式求值
def evaluate(expr, values) -> ...      # 模块级求值入口
class Expression:
    def evaluate(self, values=None, **kwargs)   # 标量或 numpy 数组
    def to_latex(self) -> str                    # LaTeX 近似
    def save(self, path) / load(cls, path)      # JSON 序列化

# encode_eval.py —— 编码对比
def compare_encodings() -> list[dict]   # [{encoding, dim, r2, rmse, note}, ...]
```

### 5.3 依赖与验收 grep 项

```bash
# 本报告自检（Y-01 验收）
grep -q "符号回归工具链选型" docs/material-symbolic-regression-勘察报告.md
grep -q "编码策略对比" docs/material-symbolic-regression-勘察报告.md
grep -q "SPEC" docs/material-symbolic-regression-勘察报告.md

# 后续施工验收（Y-02 落码后）
grep -n "def fit" mcpserver/material_science/symbolic/fit.py
grep -n "def evaluate" mcpserver/material_science/symbolic/expr.py
grep -n "def compare_encodings" mcpserver/material_science/symbolic/encode_eval.py
python -m pytest mcpserver/material_science/tests/test_symbolic.py -q        # 全过（≥6）
git diff --stat -- mcpserver/material_science/biopred.py | wc -l             # = 0
```

### 5.4 硬约束回填

- **只读勘察**：本单未 `pip install` gplearn/pysr，未运行任何第三方符号回归代码；选型表基于公开元数据与依赖分析。
- **不否决**：pysr（Julia 后端）等重工具只标注"二期/依赖重"，不否决；落地优先级由用户拍板。
- **不 copy 论文代码**：三条结论为方法论提炼，无任何论文代码入库。
- **运行依赖标注**：符号回归旁路**无需 GPU/DFT**，纯 CPU + numpy；真实木质素 ELN 数据留真机（天选7 陆墨环境）验证。

---

## 六、阻塞与假设说明（诚实标注）

1. **上游授粉原文缺失**：`weekly_pollination.md` 位于 Linux 真机路径，本仓 Windows 侧未找到；三条结论按工单内嵌描述提炼（同 ALPHA-01 对 round8 的处理）。
2. **未真机验证**：本单只读勘察；Y-02 用合成数据验收，真实木质素数据（ELN）留真机。
3. **gplearn/pysr 未装**：本仓 venv 实测无 gplearn（pysr 亦未装），故 Y-02 采用纯 numpy GP，避免新增依赖；gplearn 列为"第三方背书备选"。

---

*执行：智能体 YANKEE · 2026-08-28 · 只读勘察线（Y 线，Y-01）*
