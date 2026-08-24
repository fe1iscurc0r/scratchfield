# Channel2World T1 — 工厂场景信道数据生成器

本目录实现论文 Channel2World（arXiv:2608.17544v1）A 线复现的 **T1（P0）数据管线**：
用开源 Sionna RT 替代商业 Wireless InSite，生成工厂场景 ray-tracing 多径信道数据，
输出「多径参数 + UE 位置」，对齐论文 Table I 参数。

## 选型（草稿 §五）

| 项 | 选择 | 说明 |
|----|------|------|
| 主后端 | NVIDIA Sionna RT（Apache-2.0） | 替代 Wireless InSite |
| 降级后端 | 纯 NumPy 镜像源法 | 见下「降级路径」 |
| 数据格式 | HDF5 + parquet | HDF5 供训练，parquet 供检视/分析 |
| 元数据 | 数据卡 JSON | 环境数 / 每环境样本数 / 参数范围 |

## 论文 Table I 参数

- 载波频率：7.0 GHz
- 场景：室内工厂大厅（矩形反射面：四面墙 + 地面 + 天花板）
- BS 高度：15 m；UE 高度：1.5 m
- 每信道最多 12 条路径；最多 3 次反射；衍射关闭

## 安装

```bash
# 降级路径仅需 NumPy（本仓库已在 Python 3.13 验证）
python -m pip install numpy h5py pyarrow pandas

# 主路径（Sionna RT）需要 TensorFlow 与 Mitsuba，官方仅支持 Python 3.10~3.12：
python -m pip install tensorflow sionna
```

> **注意**：Sionna 未提供 Python 3.13 轮子。本仓库复现环境为 Python 3.13.2，
> 因此主路径代码已就绪但未在该环境实测；实际出数据走降级路径。

## 运行

```bash
# M0 里程碑：1 个工厂布局 × 100 BS × 10 UE = 1000 信道-位置对
python -m radio_brain.channel2world.data_gen.sionna_factory_gen \
    --backend specular --scenes 1 --bs-per-scene 100 --ue-per-bs 10 --seed 0

# 多环境 + 自定义参数
python -m radio_brain.channel2world.data_gen.sionna_factory_gen \
    --backend specular --scenes 3 --bs-per-scene 50 --ue-per-bs 20 --seed 42
```

输出（默认目录 `radio_brain/channel2world/data/`）：

- `factory_channels.h5` — HDF5，每环境一个 `scene_NNN` group
- `factory_channels.parquet` — 扁平化路径表（一行一条路径）
- `datacard.json` — 数据卡（环境数 / 样本数 / 参数范围）

## HDF5 输出格式

```
/ (root attrs: backend, num_scenes, frequency_hz, max_paths, ...)
scene_000/
  bs_position   (n_bs, 3)  float32   # [x, y, 15.0]
  ue_position   (n_bs, n_ue, 3) float32  # [x, y, 1.5]
  num_paths     (n_bs, n_ue) int32   # 每信道有效路径数 (1..12)
  tau_rel       (n_bs, n_ue, 12) float32  # 相对时延 (s)，NaN 填充
  aoa_theta     (n_bs, n_ue, 12) float32  # 到达天顶角 (rad)
  aoa_phi       (n_bs, n_ue, 12) float32  # 到达方位角 (rad)
  gain_rel      (n_bs, n_ue, 12) float32  # 相对增益 (dB)，NaN 填充
```

相对时延 `tau_rel`、相对增益 `gain_rel` 均相对 LOS 首径（LOS 为 0）。到达角
`theta` 为天顶角（相对 +z），`phi` 为方位角（相对 +x）。

## 验证脚本

```bash
# 加载 HDF5，打印一条样本结构；断言环境数与配置一致
python -c "import h5py, json, numpy as np; \
  f=h5py.File('radio_brain/channel2world/data/factory_channels.h5','r'); \
  g=f['scene_000']; \
  print('bs_position', g['bs_position'].shape, g['bs_position'][0]); \
  print('ue_position', g['ue_position'].shape); \
  print('num_paths', g['num_paths'][0,0]); \
  print('tau_rel[0,0]', g['tau_rel'][0,0]); \
  print('aoa_theta[0,0]', g['aoa_theta'][0,0]); \
  d=json.load(open('radio_brain/channel2world/data/datacard.json')); \
  assert d['num_scenes']==1, d['num_scenes']; \
  print('datacard num_scenes =', d['num_scenes'])"
```

## 降级路径说明（草稿 §七 风险 1）

Sionna RT 依赖 TensorFlow，且未提供 Python 3.13 轮子。降级方案用**镜像源法**
（image-source method）：

- 工厂场景以矩形反射面为主，镜像源法在这些平面上给出**精确**的路径时延与
  到达角（无需自跑 3D 参数估计，见草稿 §七「关键 hack」）。
- 对 1..3 阶反射的每组反射面序列，把 BS 依次镜像，镜像源到 UE 的直线距离即
  该路径长度，方向即到达方向。
- 反射损耗按 `|Γ| = 0.5 ≈ -6.02 dB/次` 折减；相对增益 = 自由空间路径差 +
  反射损耗。
- 该近似不求解电磁场/衍射，适用于室内矩形反射面为主的工厂场景（衍射关）。
