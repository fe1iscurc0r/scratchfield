"""三头估计器（对应实现草稿 §3.3）。

- ``PerPathPositionGMMHead``：per-path 位置 GMM —— 每条路径各自对 UE 位置输出
  一个高斯混合（各向同性分量）。
- ``GainRegressionHead``：相对增益回归 —— 每条路径回归相对增益 ḡ (dB)。
- ``PerChannelPositionGMMHead``：per-channel 位置 GMM —— 把同一信道的路径 token
  聚合后，对该信道的 UE 位置输出高斯混合。

GMM 采用各向同性分量（单一方差），分量权重经 softmax；位置为 3D (x,y,z)。
"""

from __future__ import annotations

import torch
import torch.nn as nn


class GMMHead(nn.Module):
    """各向同性高斯混合头，输出 means / log_scales / logits。"""

    def __init__(self, d_model: int, out_dim: int = 3, n_components: int = 4) -> None:
        super().__init__()
        self.out_dim = out_dim
        self.n_components = n_components
        self.mean = nn.Linear(d_model, n_components * out_dim)
        self.log_scale = nn.Linear(d_model, n_components)  # 各向同性：每分量一个 log 标准差
        self.logits = nn.Linear(d_model, n_components)

    def forward(self, x: torch.Tensor) -> dict[str, torch.Tensor]:
        """x: (..., Dm) → means (..., C, D)、log_scales (..., C)、logits (..., C)。"""
        means = self.mean(x).view(*x.shape[:-1], self.n_components, self.out_dim)
        log_scales = self.log_scale(x)
        logits = self.logits(x)
        return {"means": means, "log_scales": log_scales, "logits": logits}


class PerPathPositionGMMHead(GMMHead):
    """per-path 位置 GMM：每条路径独立预测 UE 位置分布。"""

    def __init__(self, d_model: int, out_dim: int = 3, n_components: int = 4) -> None:
        super().__init__(d_model, out_dim=out_dim, n_components=n_components)


class GainRegressionHead(nn.Module):
    """相对增益回归：每条路径回归 ḡ (dB)。"""

    def __init__(self, d_model: int) -> None:
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(d_model, d_model),
            nn.GELU(),
            nn.Linear(d_model, 1),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """x: (..., Dm) → (..., 1)。"""
        return self.net(x)


class PerChannelPositionGMMHead(GMMHead):
    """per-channel 位置 GMM：路径 token 按信道聚合（均值池化）后输出位置分布。"""

    def __init__(self, d_model: int, out_dim: int = 3, n_components: int = 4) -> None:
        super().__init__(d_model, out_dim=out_dim, n_components=n_components)

    def forward(
        self,
        x: torch.Tensor,
        channel_index: torch.Tensor,
        mask: torch.Tensor | None = None,
    ) -> dict[str, torch.Tensor]:
        """x: (B, M, Dm)；channel_index: (B, M) long ∈ [0, Nch)；mask: (B, M) bool。

        对每个 batch 逐信道做带掩码的均值池化 → (B, Nch, Dm)，再走 GMM 头。
        """
        b, m, d = x.shape
        if mask is not None:
            x = x * mask.unsqueeze(-1).to(x.dtype)
        nch = int(channel_index.max().item()) + 1

        ch_feat = torch.zeros(b, nch, d, device=x.device, dtype=x.dtype)
        cnt = torch.zeros(b, nch, device=x.device, dtype=x.dtype)
        idx = channel_index.unsqueeze(-1).expand(-1, -1, d)
        ch_feat.scatter_add_(1, idx, x)
        ones = torch.ones_like(channel_index, dtype=x.dtype)
        if mask is not None:
            ones = ones * mask.to(x.dtype)
        cnt.scatter_add_(1, channel_index, ones)
        ch_feat = ch_feat / cnt.clamp(min=1.0).unsqueeze(-1)
        return super().forward(ch_feat)  # (B, Nch, C, D) 等
