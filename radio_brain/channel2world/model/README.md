# Channel2World T2 — 环境编码器 + 三头估计器模型骨架

按实现草稿 §3.2/§3.3/§3.5 用纯 PyTorch 实现（不引 transformers，注意力手写）。

## 模块

| 文件 | 职责 |
|------|------|
| `encoder.py` | Perceiver/Set-Transformer 混合环境编码器 + query 解码器 + 顶层 `Channel2WorldModel` |
| `heads.py` | 三头估计器：per-path 位置 GMM / 相对增益回归 / per-channel 位置 GMM |
| `losses.py` | `L = L_path_pos + 0.1·L_gain + 0.5·L_ch_pos` |
| `dataset.py` | HDF5 → DataLoader，context/query 不相交采样 + 误差注入开关 |
| `train.py` | 预训练脚本（checkpoint + 收敛日志） |

## 架构

- **编码器**：context tokens → 共享投影 `Dm=128` → `Kz=16` 可学习 latent →
  6 层交替 cross/self-attention → 固定 `16×128` 无线世界嵌入（置换不变）。
- **query 解码器**：query tokens 对 latent 做 8 层 cross-attention → 2 层
  self-attention → 三头。
- **三头**：per-path 位置 GMM（各向同性分量）、相对增益回归、per-channel 位置
  GMM（路径按信道均值池化）。

## 超参（§3.5）

Dm=128, Kz=16, heads=4, FFN×4, context=128, query=32, batch=32,
λg=0.1, λch=0.5；误差注入 στ=1ns、σθ=σφ=1°、σξ=3dB、σpos=0.1m。

## 运行

```bash
# 单测（9 用例）
python -m pytest radio_brain/channel2world/tests/ -q

# 冒烟训练（CPU 小规模）
python -m radio_brain.channel2world.model.train \
    --data radio_brain/channel2world/data/factory_channels.h5 \
    --context 32 --query 8 --batch 8 --steps 60 --out-dir radio_brain/channel2world/logs/smoke
```

## 参数量报告

默认配置（Dm=128/Kz=16/heads=4，encoder 6 层 + query 8+2 层）参数量
**4,387,369**（约 4.4M）。论文参考 ~9.2M 不强制精确——本骨架 FFN/头维度较精简，
T3 补齐下游评估时可按需扩到参考量级。
