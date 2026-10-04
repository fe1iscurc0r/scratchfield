# MODEL_INTERFACE: SLICES

- 上游仓库: https://github.com/xiaohang007/SLICES
- 许可证: MIT（README 标注；上游 LICENSE 复核保留，见 ../LICENSES.md）
- 安装: 重量级，建议独立 conda 环境（python 3.9 + torch + tensorflow-cpu + pymatgen 等，见下）
- Python 模块名: `slices`

## 算法定位

首个可逆、不变的晶体字符串表示（Simplified Line-Input Crystal-Encoding System）：
晶体 ↔ SLICES 字符串无损互转（Text2Crystal），配 MatterGPT 做多性质逆向设计
（Nature Communications 2023 / arXiv 2408.07608 / SLICES-PLUS arXiv 2410.22828）。

## 核心 API

```python
from slices.core import SLICES
from pymatgen.core.structure import Structure

structure = Structure.from_file('NdSiRu.cif')
backend = SLICES()
s = backend.structure2SLICES(structure)                      # 晶体→字符串
recon, energy_per_atom = backend.SLICES2structure(s)         # 字符串→晶体 + 能量/原子 [eV]

# 数据增广与规范化
backend = SLICES(graph_method='econnn')
aug = backend.structure2SLICESAug_atom_order(structure=structure, num=50)
canon = {backend.get_canonical_SLICES(x) for x in aug}
```

## 安装要点（环境隔离）

```bash
conda create --name slices python=3.9
pip install tensorflow-cpu==2.13.0
pip install --no-deps m3gnet
pip install smact==2.5.5 ase==3.22.1 pymatgen==2024.8.9
pip install scipy==1.13.0 scikit-learn==1.3.1 numpy==1.26.4
pip install slices --no-deps
```

MatterGPT 需 torch + 可选 flash-attn（Linux/GPU）；GUI: `python MatterGPT/app.py`。

## 数据格式

- 输入: pymatgen Structure / CIF 文件；SLICES 字符串
- 输出: SLICES 字符串；重建的 Structure + 能量/原子
- 在线转换: huggingface spaces xiaohang07/SLICES（CIF↔SLICES）

## Lumo 工作台用途

- 候选晶体结构的字符串化存储/检索/去重
- 按目标性质（如带隙）逆向设计候选材料（需 GPU 环境）

## 引用

Xiao, H. et al. An invertible, invariant crystal representation for inverse
design of solid-state materials using generative deep learning. Nature
Communications 14, 7027 (2023).
