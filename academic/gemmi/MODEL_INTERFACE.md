# MODEL_INTERFACE: gemmi

- 上游仓库: https://github.com/project-gemmi/gemmi
- 许可证: MPLv2 或（选择）LGPLv3 —— 与白名单措辞不同，使用前复核，见 ../LICENSES.md
- 安装: `pip install gemmi`（C++14 核心 + Python 绑定 + 命令行工具）
- Python 模块名: `gemmi`

## 算法定位

晶体学文件与对称性瑞士军刀（CCP4/Global Phasing 出品）：大分子模型
（mmCIF/PDB/mmJSON）、精修约束（CIF）、小分子模型、晶体学反射数据
（MTZ）、密度图（MRC/CCP4）、晶体学对称操作、CIF/STAR 读写。

## 核心 API

```python
import gemmi
st = gemmi.read_structure('1ake.cif')      # mmCIF/PDB 均可
st[0]                                      # 第一个模型
for chain in st[0]: ...                    # 链/残基/原子遍历

cif = gemmi.cif.read_file('data.cif')      # CIF/STAR 解析
block = cif.sole_block()
block.find(['_cell_length_a', '_cell_angle_alpha'])

grp = gemmi.find_spacegroup_by_name('P212121')  # 空间群查询
gemmi.read_ccp4_map('map.mrc')             # 电子密度图
gemmi.read_mtz_file('refl.mtz')            # 反射数据
```

## 数据格式

- 输入: CIF/mmCIF/PDB/MTZ/MRC 等晶体学标准格式文件
- 输出: Python 对象（Structure/Block/UnitCell/SpaceGroup）
- 命令行: `gemmi` 提供 convert/validate 等批处理子命令

## Lumo 工作台用途

- CIF 批量解析与单元格参数提取（材料卡片自动化）
- 空间群/对称操作查询，配合 PyXtal 做结构分析

## 引用

Wojdyr, M. GEMMI. Journal of Open Source Software (2022).
doi:10.21105/joss.04200
