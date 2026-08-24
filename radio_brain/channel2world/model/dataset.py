"""HDF5 → PyTorch DataLoader（对应实现草稿 §3.5 的 context/query 不相交采样）。

把 T1 生成的 HDF5 多径信道数据读入，构造「信道-位置对」。每条路径编码为一个
9 维 token：

    0        τ̄ 相对时延（ns，除以 100）
    1..4     sin/cos(aoa_theta)、sin/cos(aoa_phi)
    5        ḡ 相对增益（dB，除以 30）
    6..8     UE 位置 x/y/z（米，除以 100）

context 信道为「完全观测」（含增益 + 位置），query 信道为「部分观测」
（增益与位置置零，由模型预测）。误差注入开关（§3.5）向观测特征与位置标签
注入高斯噪声：στ=1ns、σθ=σφ=1°、σξ=3dB、σpos=0.1m。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import torch
from torch.utils.data import Dataset

FEATURE_DIM = 9


@dataclass
class DatasetConfig:
    """T1 数据 → DataLoader 的采样与误差注入配置（对齐 §3.5）。"""

    hdf5_path: str
    context_size: int = 128  # 上下文信道数
    query_size: int = 32  # query 信道数
    max_paths: int = 12  # 每信道最多路径数
    num_splits: int = 32  # 每 epoch 采样 (context, query) 组合数
    error_injection: bool = False  # 误差注入开关
    sigma_pos: float = 0.1  # 位置标签噪声 (m)
    sigma_tau_ns: float = 1.0  # 时延噪声 (ns)
    sigma_angle_deg: float = 1.0  # 角度噪声 (度)
    sigma_gain_db: float = 3.0  # 增益噪声 (dB)
    seed: int = 0


class Channel2WorldDataset(Dataset):
    """把 HDF5 工厂信道数据打包为 (context 集合, query 集合) 训练样本。"""

    def __init__(self, config: DatasetConfig | None = None, **kwargs) -> None:
        if config is None:
            config = DatasetConfig(**kwargs)
        self.cfg = config
        self.rng = np.random.default_rng(config.seed)
        self.channels = self._load(Path(config.hdf5_path))
        self.n_channels = len(self.channels)
        need = config.context_size + config.query_size
        if need > self.n_channels:
            raise ValueError(
                f"数据仅 {self.n_channels} 信道，不足以采样 context({config.context_size})+query({config.query_size})={need}"
            )

    def _load(self, path: Path) -> list[dict]:
        import h5py

        channels: list[dict] = []
        with h5py.File(path, "r") as f:
            for key in sorted(f.keys()):
                if not key.startswith("scene_"):
                    continue
                g = f[key]
                bs = g["bs_position"][:]
                ue = g["ue_position"][:]  # (n_bs, n_ue, 3)
                num_paths = np.asarray(g["num_paths"])  # (n_bs, n_ue)
                tau = g["tau_rel"][:]
                th = g["aoa_theta"][:]
                ph = g["aoa_phi"][:]
                gain = g["gain_rel"][:]
                n_bs, n_ue, _ = ue.shape
                for i in range(n_bs):
                    for j in range(n_ue):
                        np_ = int(num_paths[i, j])
                        channels.append(
                            {
                                "tau": np.asarray(tau[i, j, :np_], dtype=np.float32),
                                "theta": np.asarray(th[i, j, :np_], dtype=np.float32),
                                "phi": np.asarray(ph[i, j, :np_], dtype=np.float32),
                                "gain": np.asarray(gain[i, j, :np_], dtype=np.float32),
                                "ue_pos": np.asarray(ue[i, j], dtype=np.float32),
                                "bs_pos": np.asarray(bs[i], dtype=np.float32),
                            }
                        )
        return channels

    def _features(self, ch: dict, is_context: bool) -> np.ndarray:
        """单信道 → (P, 9) 路径特征张量（P 为该信道路径数，未填充）。"""
        p = ch["tau"].shape[0]
        tau = ch["tau"] * 1e9 / 100.0  # ns → /100
        theta = ch["theta"]
        phi = ch["phi"]
        gain = ch["gain"] / 30.0
        ue = ch["ue_pos"] / 100.0

        if self.cfg.error_injection:
            tau += self.rng.normal(0.0, self.cfg.sigma_tau_ns / 100.0, size=p)
            theta = theta + self.rng.normal(0.0, np.deg2rad(self.cfg.sigma_angle_deg), size=p)
            phi = phi + self.rng.normal(0.0, np.deg2rad(self.cfg.sigma_angle_deg), size=p)
            if is_context:
                gain = gain + self.rng.normal(0.0, self.cfg.sigma_gain_db / 30.0, size=p)

        feat = np.stack(
            [
                tau,
                np.sin(theta),
                np.cos(theta),
                np.sin(phi),
                np.cos(phi),
                gain,
                np.full(p, ue[0], dtype=np.float32),
                np.full(p, ue[1], dtype=np.float32),
                np.full(p, ue[2], dtype=np.float32),
            ],
            axis=-1,
        ).astype(np.float32)

        if not is_context:
            # query：部分观测，增益与位置置零，由模型预测
            feat[:, 5] = 0.0
            feat[:, 6:9] = 0.0
        return feat

    def _pad_channel(self, ch: dict, is_context: bool) -> tuple[np.ndarray, np.ndarray]:
        """单信道 → (max_paths, 9) 特征 + (max_paths,) 掩码（NaN/多余路径置 False）。"""
        feat = self._features(ch, is_context)
        p = feat.shape[0]
        m = self.cfg.max_paths
        out = np.zeros((m, FEATURE_DIM), dtype=np.float32)
        mask = np.zeros((m,), dtype=bool)
        out[:p] = feat
        mask[:p] = True
        return out, mask

    def __len__(self) -> int:
        return self.cfg.num_splits

    def __getitem__(self, idx: int) -> dict[str, torch.Tensor]:
        cfg = self.cfg
        n = self.n_channels
        need = cfg.context_size + cfg.query_size
        idxs = self.rng.choice(n, size=need, replace=False)
        ctx_idx = idxs[: cfg.context_size]
        q_idx = idxs[cfg.context_size :]

        # context：完全观测
        ctx_feats, ctx_masks = [], []
        for i in ctx_idx:
            f, m = self._pad_channel(self.channels[i], is_context=True)
            ctx_feats.append(f)
            ctx_masks.append(m)
        context_x = np.concatenate(ctx_feats, axis=0)  # (context_size*max_paths, 9)
        context_mask = np.concatenate(ctx_masks, axis=0)

        # query：部分观测
        q_feats, q_masks, q_gain, q_pos, ch_pos, ch_index = [], [], [], [], [], []
        for c, i in enumerate(q_idx):
            ch = self.channels[i]
            f, m = self._pad_channel(ch, is_context=False)
            p = int(np.sum(m))
            q_feats.append(f)
            q_masks.append(m)
            q_gain.append(np.pad(ch["gain"].reshape(-1, 1), ((0, cfg.max_paths - p), (0, 0)), constant_values=np.nan))
            ue_pos = ch["ue_pos"]
            if cfg.error_injection:
                ue_pos = ue_pos + self.rng.normal(0.0, cfg.sigma_pos, size=3)
            q_pos.append(np.tile(ue_pos.reshape(1, 3), (cfg.max_paths, 1)))
            ch_pos.append(ue_pos.reshape(1, 3))
            ch_index.append(np.full(cfg.max_paths, c, dtype=np.int64))
        query_x = np.concatenate(q_feats, axis=0)  # (query_size*max_paths, 9)
        query_mask = np.concatenate(q_masks, axis=0)
        gain_target = np.concatenate(q_gain, axis=0)  # (query_size*max_paths, 1)
        path_pos_target = np.concatenate(q_pos, axis=0)  # (query_size*max_paths, 3)
        ch_pos_target = np.concatenate(ch_pos, axis=0)  # (query_size, 3)
        channel_index = np.concatenate(ch_index, axis=0)  # (query_size*max_paths,)

        return {
            "context_x": torch.from_numpy(context_x),
            "context_mask": torch.from_numpy(context_mask),
            "query_x": torch.from_numpy(query_x),
            "query_mask": torch.from_numpy(query_mask),
            "channel_index": torch.from_numpy(channel_index),
            "path_pos_target": torch.from_numpy(path_pos_target),
            "gain_target": torch.from_numpy(gain_target),
            "ch_pos_target": torch.from_numpy(ch_pos_target),
        }


def collate(batch: list[dict[str, torch.Tensor]]) -> dict[str, torch.Tensor]:
    """把 batch 个样本按第 0 维堆叠（batch 维度在前）。"""
    keys = batch[0].keys()
    return {k: torch.stack([b[k] for b in batch], dim=0) for k in keys}
