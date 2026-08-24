# 任务：阶段五 A档 · 材料底座施工

你是 scratchpad 项目的融合工程师。scratchpad 是个人 AI 助手 monorepo（AGPL v3），当前在给陆墨（AI 助手）补"确定性材料计算"能力。

## 背景（为什么做）

陆墨现有知识底座是 GRAG（对话抽五元组 → RDF 推理），但**没有确定性化学计算能力**——问"木质素的分子量是多少"，LLM 靠记忆猜，不可靠。阶段五 A档装两个轻量库：ChemFormula（分子式/分子量）和 AffineGaps（序列比对），让陆墨的材料/生化问题有确定性算法支撑。

## 输入

1. **SPEC**：`scratchpad/docs/MATERIAL-STAGE5A-SPEC-v1.md`（先读，接口和施工顺序都定死了）
2. **ChemFormula 源码**：`scratchpad-knowledge/academic/ChemFormula/src/chemformula/`（elements.py / chemformula.py / config.py / __init__.py）
3. **AffineGaps 源码**：`scratchpad-knowledge/academic/AffineGaps/affine_gaps.py`（单文件 41KB）
4. **参考模板（同类旁路接入模式）**：`mcpserver/adapters/semantic_web/bridge.py` 和 `apiserver/routes/lumo_proxy.py` 的 `_query_semantic` 函数——阶段五 A档的 `_query_chem` 照这套模板走

## 你的任务

严格按 SPEC 第五节的 Phase A1 → A2 → A3 顺序走，A1/A2 先测后接，不能跳。

### Phase A1：ChemAdapter
- 创建 `mcpserver/adapters/chem_adapter/`
- 目录结构：
  ```
  chem_adapter/
    __init__.py         ← 导出 ChemFormula, ChemFormulaString, ChemFormulaDict
    core.py             ← chemformula.py 原样复制（零修改）
    config.py           ← config.py 原样复制
    data/
      elements.py       ← elements.py 原样复制（原子量数据）
  ```
- **核心验证**（必须跑通）：
  ```bash
  python -c "from mcpserver.adapters.chem_adapter import ChemFormula; print(ChemFormula('H2SO4').formula_weight)"
  # 预期输出：98.0xx（围绕 98）
  python -c "from mcpserver.adapters.chem_adapter import ChemFormula; print(ChemFormula('C6H12O6').hill_formula)"
  # 预期：C6H12O6（希尔排序 CHNO 优先）
  ```

### Phase A2：BioAdapter
- 创建 `mcpserver/adapters/bio_adapter/`
- 目录结构：
  ```
  bio_adapter/
    __init__.py   ← 导出 needleman_wunsch_gotoh_alignment / smith_waterman_gotoh_alignment / levenshtein_distance
    align.py      ← affine_gaps.py 原样复制（零修改）
  ```
- **核心验证**（必须跑通）：
  ```bash
  python -c "from mcpserver.adapters.bio_adapter import needleman_wunsch_gotoh_alignment; a,b,s=needleman_wunsch_gotoh_alignment('GATTACA','GCATGCU'); print(s)"
  # 预期输出：3
  ```

### Phase A3：陆墨接入
- 在 `apiserver/routes/lumo_proxy.py` 的 `_query_rag_standalone()` 函数内，仿照 `_query_semantic` 的写法，加 `_query_chem` 旁路
- 逻辑：正则抽化学式 → ChemFormula 计算 → 格式化文本并入 RAG 召回
- **降级铁律**：任何异常返回空字符串，不影响 GRAG 主链路
- **参考代码模板**（照此抄）：
  ```python
  async def _query_chem(question: str) -> str:
      import re
      from mcpserver.adapters.chem_adapter import ChemFormula
      try:
          formulas = re.findall(r'[A-Z][a-z]?(?:\d+)?', question)
          results = []
          for f in formulas:
              try:
                  cf = ChemFormula(f)
                  results.append(f"{f}: 分子量={cf.formula_weight:.3f}, 组成={dict(cf.element)}")
              except Exception:
                  pass
          return "\n".join(results) if results else ""
      except Exception:
          return ""
  ```

## 依赖

- `numpy`（必须，用于 BioAdapter 的 DP 矩阵）
- `casregnum`（可选，ChemFormula 的 CAS 号解析增强）
- `numba`（可选，有则 JIT 加速，无则纯 Python 回退）
- 其余全部 stdlib

## 硬约束

1. **零修改原则**：`elements.py` / `chemformula.py` / `affine_gaps.py` 原样复制进目标目录，文件名可以改，内容一个字都不许动
2. **先测后接**：A1 和 A2 必须分别跑通验证命令，再进 A3
3. **旁路降级**：`_query_chem` 必须 try/except 全包裹，挂了不影响主链路
4. **不碰现有写路径**：只读 ChemFormula/BioAdapter 输出，不改任何存图/写文件逻辑
5. **中文注释 + 务实**：不吹，Python 用 ruff 风格

## 输出

- ChemAdapter → `scratchpad/mcpserver/adapters/chem_adapter/`
- BioAdapter → `scratchpad/mcpserver/adapters/bio_adapter/`
- lumu_proxy 改动（`_query_chem` 新增）
- 每个 Phase 完成后，报告：改了哪些文件 + 测试结果
- 全部完成后跑一遍 A1 + A2 的验证命令，贴输出
