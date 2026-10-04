# MODEL_INTERFACE: FEMcy

- 上游仓库: 中转库 academic 镜像（基于 Taichi 的 FEM 求解器）
- 许可证: 上游许可随仓库（引用须保留，见 ../LICENSES.md）
- 安装: `pip install taichi numpy scipy`，git clone 后 `python main.py`
- 运行方式: 交互式命令行指定 .inp 文件

## 算法定位

基于 Taichi 的连续介质结构有限元求解器：CPU/GPU 并行，支持小变形与
大变形（几何非线性，Newton 法 + 自适应时间步/松弛因子），材料非线性
可自定义本构，Python 可读 + Taichi 高性能两全。

## 单元与边界条件

- 单元: CPE3/CPS3（线性三角）、CPE6/CPS6（二次三角）、CPE4/CPS4
  （线性四边形）、CPE8/CPS8（二次四边形）、C3D4（线性四面体）、
  C3D10（二次四面体，编译约 5 分钟）
- 边界: Dirichlet（节点位移）、Neumann（表面牵引力）

## 核心用法

```bash
python main.py
# 提示输入 .inp 路径（Abaqus 输入文件格式：几何/网格/材料/边界条件）
# 例: tests/beam_deflection/load800_freeEnd_largeDef/beamDeflec_quadPSE_largeD_load800.inp
# 收敛后按 Mises 应力着色显示变形体
```

## 数据格式

- 输入: Abaqus .inp 文件（可直接由 Abaqus 前处理 GUI 导出）
- 输出: 窗口渲染变形体（Mises 应力）；代码内可改写导出
- 基准验证: 椭圆膜问题 σyy 与 Abaqus 误差 ≤ 0.12%；悬臂梁大变形
  载荷-挠度曲线与 Abaqus 高度一致

## Lumo 工作台用途

- 材料试样受力/大变形的数值仿真（配合实验数据做对照）
- GPU 并行仿真教学演示

## 引用

FEMcy: a finite element solver based on Taichi. 基准问题参见
CoFEA benchmark 004-eliptic-membrane。
