"""环境编码器（Set-Transformer/Perceiver 混合）+ query 解码器 + 顶层模型。

对应实现草稿 §3.2 / §3.3：

- **编码器**（§3.2）：context tokens → 共享投影 ``Dm=128`` → ``Kz=16`` 个可学习
  latent → 6 层交替 cross/self-attention → 产出「无线世界嵌入」（固定 16×128）。
  cross-attention 以 latent 为 query、context 为 key/value，输出是 context 的
  加权和，故对 context 顺序**置换不变**（Set-Transformer 诱导点 / Perceiver
  潜变量机制）。
- **query 解码器**（§3.3）：query tokens 先对 latent 做 8 层 cross-attention，
  再 2 层 self-attention，输出接入三头估计器（见 ``heads.py``）。

超参对齐 §3.5：Dm=128, Kz=16, heads=4, FFN×4, context=128, query=32。
"""

from __future__ import annotations

import math

import torch
import torch.nn as nn


class MultiHeadAttention(nn.Module):
    """标准缩放点积多头注意力，支持 self-attention 与 cross-attention。"""

    def __init__(self, d_model: int, heads: int = 4, dropout: float = 0.0) -> None:
        super().__init__()
        assert d_model % heads == 0, "d_model 必须被 heads 整除"
        self.d_model = d_model
        self.heads = heads
        self.d_head = d_model // heads
        self.q_proj = nn.Linear(d_model, d_model)
        self.k_proj = nn.Linear(d_model, d_model)
        self.v_proj = nn.Linear(d_model, d_model)
        self.out_proj = nn.Linear(d_model, d_model)
        self.dropout = nn.Dropout(dropout)
        self.scale = self.d_head ** -0.5

    def forward(self, q: torch.Tensor, kv: torch.Tensor, kv_mask: torch.Tensor | None = None) -> torch.Tensor:
        """q: (B, Nq, Dm)，kv: (B, Nkv, Dm)，kv_mask: (B, Nkv) bool（True=保留）。"""
        b, nq, _ = q.shape
        nkv = kv.shape[1]
        qq = self.q_proj(q).view(b, nq, self.heads, self.d_head).transpose(1, 2)  # (B,H,Nq,dh)
        kk = self.k_proj(kv).view(b, nkv, self.heads, self.d_head).transpose(1, 2)  # (B,H,Nkv,dh)
        vv = self.v_proj(kv).view(b, nkv, self.heads, self.d_head).transpose(1, 2)  # (B,H,Nkv,dh)

        attn = torch.matmul(qq, kk.transpose(-1, -2)) * self.scale  # (B,H,Nq,Nkv)
        if kv_mask is not None:
            attn = attn.masked_fill(~kv_mask[:, None, None, :], float("-inf"))
        attn = torch.softmax(attn, dim=-1)
        attn = self.dropout(attn)

        out = torch.matmul(attn, vv)  # (B,H,Nq,dh)
        out = out.transpose(1, 2).contiguous().view(b, nq, self.d_model)
        return self.out_proj(out)


class Block(nn.Module):
    """Pre-LN 的注意力 + FFN 残差块；kv=None 时为 self-attention，否则为 cross-attention。"""

    def __init__(self, d_model: int, heads: int = 4, ff_mult: int = 4) -> None:
        super().__init__()
        self.norm1 = nn.LayerNorm(d_model)
        self.attn = MultiHeadAttention(d_model, heads)
        self.norm2 = nn.LayerNorm(d_model)
        self.ffn = nn.Sequential(
            nn.Linear(d_model, d_model * ff_mult),
            nn.GELU(),
            nn.Linear(d_model * ff_mult, d_model),
        )

    def forward(self, x: torch.Tensor, kv: torch.Tensor | None = None, kv_mask: torch.Tensor | None = None) -> torch.Tensor:
        if kv is None:
            kv = x
            q = self.norm1(x)
            k_v = q
        else:
            q = self.norm1(x)
            k_v = self.norm1(kv)
        x = x + self.attn(q, k_v, kv_mask)
        x = x + self.ffn(self.norm2(x))
        return x


class PerceiverEncoder(nn.Module):
    """环境编码器：变长 context 集合 → 固定 Kz×Dm 的「无线世界嵌入」。

    以 Kz 个可学习 latent token 作为 query，对 context token 做 cross-attention
    （对 context 顺序置换不变），再对 latent 之间做 self-attention，交替 layers 层。
    """

    def __init__(self, d_model: int = 128, kz: int = 16, heads: int = 4, layers: int = 6, ff_mult: int = 4) -> None:
        super().__init__()
        self.d_model = d_model
        self.kz = kz
        self.latents = nn.Parameter(torch.randn(kz, d_model) * 0.02)
        self.cross_layers = nn.ModuleList([Block(d_model, heads, ff_mult) for _ in range(layers)])
        self.self_layers = nn.ModuleList([Block(d_model, heads, ff_mult) for _ in range(layers)])
        self.norm = nn.LayerNorm(d_model)

    def forward(self, x: torch.Tensor, mask: torch.Tensor | None = None) -> torch.Tensor:
        """x: (B, N, Dm) 已投影的 context tokens；mask: (B, N) bool（True=保留）。"""
        b = x.shape[0]
        z = self.latents.unsqueeze(0).expand(b, -1, -1)  # (B, Kz, Dm)
        for cross_blk, self_blk in zip(self.cross_layers, self.self_layers):
            z = cross_blk(z, kv=x, kv_mask=mask)  # latent 注意 context
            z = self_blk(z)  # latent 之间 self-attention
        return self.norm(z)  # (B, Kz, Dm)


class QueryDecoder(nn.Module):
    """query 解码器：query tokens 对 latent 做 8 层 cross-attention，再 2 层 self-attention。"""

    def __init__(self, d_model: int = 128, heads: int = 4, cross_layers: int = 8, self_layers: int = 2, ff_mult: int = 4) -> None:
        super().__init__()
        self.cross_layers = nn.ModuleList([Block(d_model, heads, ff_mult) for _ in range(cross_layers)])
        self.self_layers = nn.ModuleList([Block(d_model, heads, ff_mult) for _ in range(self_layers)])

    def forward(self, q: torch.Tensor, latent: torch.Tensor, latent_mask: torch.Tensor | None = None) -> torch.Tensor:
        """q: (B, M, Dm) 已投影的 query tokens；latent: (B, Kz, Dm)。"""
        for blk in self.cross_layers:
            q = blk(q, kv=latent, kv_mask=latent_mask)
        for blk in self.self_layers:
            q = blk(q)
        return q  # (B, M, Dm)


class Channel2WorldModel(nn.Module):
    """Channel2World 顶层模型：环境编码器 + query 解码器 + 三头估计器。"""

    def __init__(
        self,
        d_in: int = 9,
        d_model: int = 128,
        kz: int = 16,
        heads: int = 4,
        encoder_layers: int = 6,
        query_cross_layers: int = 8,
        query_self_layers: int = 2,
        n_components: int = 4,
        ff_mult: int = 4,
    ) -> None:
        super().__init__()
        from .heads import GainRegressionHead, PerChannelPositionGMMHead, PerPathPositionGMMHead

        self.d_model = d_model
        self.kz = kz
        self.shared_proj = nn.Linear(d_in, d_model)  # §3.2 共享投影 Dm=128
        self.encoder = PerceiverEncoder(d_model, kz, heads, encoder_layers, ff_mult)
        self.decoder = QueryDecoder(d_model, heads, query_cross_layers, query_self_layers, ff_mult)
        self.path_pos_head = PerPathPositionGMMHead(d_model, n_components=n_components)
        self.gain_head = GainRegressionHead(d_model)
        self.ch_pos_head = PerChannelPositionGMMHead(d_model, n_components=n_components)

    def forward(
        self,
        context_x: torch.Tensor,
        context_mask: torch.Tensor | None,
        query_x: torch.Tensor,
        query_mask: torch.Tensor | None,
        channel_index: torch.Tensor,
    ) -> dict[str, torch.Tensor | dict]:
        """前向。

        context_x/query_x: (B, N, d_in) 原始路径特征（模型内部做共享投影）。
        channel_index: (B, M) long，每个 query 路径 token 所属的信道编号。
        返回 dict：latent / path_gmm / gain / ch_gmm（见 heads.py）。
        """
        latent = self.encoder(self.shared_proj(context_x), context_mask)  # (B, Kz, Dm)
        q = self.decoder(self.shared_proj(query_x), latent)  # (B, M, Dm)
        path_gmm = self.path_pos_head(q)
        gain = self.gain_head(q)
        ch_gmm = self.ch_pos_head(q, channel_index, query_mask)
        return {"latent": latent, "path_gmm": path_gmm, "gain": gain, "ch_gmm": ch_gmm}

    def num_parameters(self) -> int:
        return sum(p.numel() for p in self.parameters())
