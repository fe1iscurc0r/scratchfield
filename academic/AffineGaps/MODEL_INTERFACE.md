# MODEL_INTERFACE: AffineGaps

- 上游仓库: https://github.com/ashvardanian/affine-gaps
- 许可证: Apache-2.0（仓库 LICENSE；引用须保留，见 ../LICENSES.md）
- 安装: `pip install affine-gaps`（可选 `affine-gaps[numba]` 启用 JIT）
- Python 模块名: `affine_gaps`

## 算法定位

"更少错"的 Gotoh 仿射空位罚分序列比对（单文件、Numba 加速）：修正了
1982 年 Gotoh 论文及常见教科书实现中的初始化错误，提供正确的
Needleman-Wunsch（全局）与 Smith-Waterman（局部）比对。

## 核心 API

```python
from affine_gaps import needleman_wunsch_gotoh_alignment, needleman_wunsch_gotoh_score

seq1 = "GIVEQCCTSICSLYQLENYCN"
seq2 = "HSQGTFTSDYSKYLDSRAEQDFV"
a1, a2, score = needleman_wunsch_gotoh_alignment(seq1, seq2)  # 默认 BLOSUM62
score_only = needleman_wunsch_gotoh_score(seq1, seq2)         # 省内存

# 自定义替换矩阵与空位罚分
needleman_wunsch_gotoh_alignment(
    seq1, seq2,
    substitution_alphabet=alphabet, substitution_matrix=matrix,
    gap_opening=-2, gap_extension=-1)
```

命令行: `affine-gaps SEQ1 SEQ2 [--local]`。

## 数据格式

- 输入: 两个字符串序列（蛋白质默认；核苷酸/自定义字母表可换矩阵）
- 输出: (对齐串1, 对齐串2, 得分) 或仅得分（int）
- CLI 输出: FASTA 风格文本块

## Lumo 工作台用途

- 生物基材料相关的蛋白/多肽序列比对（丝素/纤维素合酶片段等）
- 字符串相似度基线工具（配方代号序列比对）

## 引用

Vardanian, A. Affine Gaps: less-wrong Gotoh affine gap penalty implementation.
GitHub: ashvardanian/affine-gaps. 算法勘误背景: Flouri et al., biorXiv
10.1101/031500.
