"""损失函数（对应实现草稿 §3.5）。

总损失：``L = L_path_pos + 0.1·L_gain + 0.5·L_ch_pos``

- ``L_path_pos``：per-path 位置 GMM 的负对数似然（各向同性分量）。
- ``L_gain``：相对增益回归 MSE。
- ``L_ch_pos``：per-channel 位置 GMM 的负对数似然。

权重对齐 §3.5：λg=0.1（增益）、λch=0.5（信道位置），路径位置权重 1.0。
"""

from __future__ import annotations

import math

import torch
import torch.nn.functional as F

_LAMBDA_GAIN = 0.1  # λg
_LAMBDA_CH_POS = 0.5  # λch


def gaussian_mixture_nll(
    means: torch.Tensor,
    log_scales: torch.Tensor,
    logits: torch.Tensor,
    target: torch.Tensor,
    mask: torch.Tensor | None = None,
) -> torch.Tensor:
    """各向同性高斯混合的负对数似然（NLL）。

    means: (..., C, D)；log_scales: (..., C)；logits: (..., C)；target: (..., D)。
    mask: (...,) bool，仅对保留位置求均值。返回标量。
    """
    d = means.shape[-1]
    log_w = torch.log_softmax(logits, dim=-1)  # (..., C)
    scales = torch.exp(log_scales).clamp(min=1e-4)  # (..., C)
    diff = target.unsqueeze(-2) - means  # (..., C, D)
    maha = (diff * diff).sum(-1) / (2.0 * scales * scales + 1e-8)  # (..., C)
    const = 0.5 * d * math.log(2.0 * math.pi)
    log_prob = log_w - const - d * torch.log(scales) - maha  # (..., C)
    nll = -torch.logsumexp(log_prob, dim=-1)  # (...)
    if mask is not None:
        return (nll * mask.to(nll.dtype)).sum() / mask.sum().clamp(min=1)
    return nll.mean()


def compute_losses(
    outputs: dict,
    path_pos_target: torch.Tensor,
    gain_target: torch.Tensor,
    ch_pos_target: torch.Tensor,
    path_mask: torch.Tensor | None = None,
    ch_mask: torch.Tensor | None = None,
    lambda_gain: float = _LAMBDA_GAIN,
    lambda_ch_pos: float = _LAMBDA_CH_POS,
) -> tuple[torch.Tensor, dict[str, torch.Tensor]]:
    """汇总三头损失，返回 (总损失, 各分量字典)。"""
    path_gmm = outputs["path_gmm"]
    l_path_pos = gaussian_mixture_nll(
        path_gmm["means"], path_gmm["log_scales"], path_gmm["logits"], path_pos_target, path_mask
    )

    gain = outputs["gain"].squeeze(-1)  # (B, M)
    if path_mask is not None:
        gain = gain[path_mask]
        gain_target = gain_target.squeeze(-1)[path_mask]
    else:
        gain_target = gain_target.squeeze(-1)
    l_gain = F.mse_loss(gain, gain_target)

    ch_gmm = outputs["ch_gmm"]
    l_ch_pos = gaussian_mixture_nll(
        ch_gmm["means"], ch_gmm["log_scales"], ch_gmm["logits"], ch_pos_target, ch_mask
    )

    total = l_path_pos + lambda_gain * l_gain + lambda_ch_pos * l_ch_pos
    return total, {"path_pos": l_path_pos, "gain": l_gain, "ch_pos": l_ch_pos}


def total_loss(
    outputs: dict,
    path_pos_target: torch.Tensor,
    gain_target: torch.Tensor,
    ch_pos_target: torch.Tensor,
    path_mask: torch.Tensor | None = None,
    ch_mask: torch.Tensor | None = None,
) -> torch.Tensor:
    """L = L_path_pos + 0.1·L_gain + 0.5·L_ch_pos。"""
    total, _ = compute_losses(outputs, path_pos_target, gain_target, ch_pos_target, path_mask, ch_mask)
    return total
