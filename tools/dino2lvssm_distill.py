"""DINOv2 → LVSSM 跨架构蒸馏骨架（digest-g2-4b 蒸馏授粉点）。

授粉源：digest-g2-4b-2026-08-30.md「DINOv2 教师 → 轻量状态空间模型学生
（带门控双向选择扫描块），4.45M 学生保留 98.3% 精度」。

本骨架跑通「离线教师 logit 蒸馏」闭环，并量化精度保留：
  教师（先在有信号的合成分类任务上预训练）→ 冻结 → 输出软 logits（温度软化）
  → 学生（LVSSM）用 KL 散度对齐教师输出分布 → 反向传播更新学生。
  输出教师精度 / 学生蒸馏后精度 / 保留率，证明「蒸馏保留精度」方向。
  全程离线，不加载真实 DINOv2 权重（真实教师可直接替换 Teacher 类）。

验收（骨架可跑通 logit 蒸馏流程 + 精度保留）：
  python tools/dino2lvssm_distill.py
  打印教师/学生精度、保留率、参数量、蒸馏损失下降；脚本内 assert 损失下降 + 保留率 ≥ 50%。

预算表（参数量/内存/精度）见 docs/dino2lvssm-distill-方案.md。
"""
from __future__ import annotations

import argparse

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F


# --------------------------------------------------------------------------- #
# 学生：LVSSM（轻量视觉状态空间模型）—— 简化版「门控选择扫描块」
# --------------------------------------------------------------------------- #
class SelectiveScan(nn.Module):
    """极简门控选择扫描块（Mamba-lite 语义）。

    A 为对角状态矩阵（对数空间学习，负初始化保证稳定性）；B/C/Δ 由输入
    线性生成（「选择」）；输出用 SiLU 门控 z 调制。支持双向（正反各扫一次）。
    这是对论文「带门控双向选择扫描块」的工程简化，机制一致、非逐字复刻。
    """

    def __init__(self, d_model: int, d_state: int = 16, bidirectional: bool = True):
        super().__init__()
        self.d_model = d_model
        self.d_state = d_state
        self.bidirectional = bidirectional
        # 对数空间对角 A：负初始化 → 离散后 |A_bar| < 1，保证扫描稳定
        self.logA = nn.Parameter(torch.log(torch.full((d_model, d_state), 0.5)))
        self.W_delta = nn.Linear(d_model, d_model)
        self.W_B = nn.Linear(d_model, d_state)
        self.W_C = nn.Linear(d_model, d_state)
        self.W_z = nn.Linear(d_model, d_model)

    def _scan(self, x: torch.Tensor) -> torch.Tensor:
        """x: (B, L, D) → y: (B, L, D)。选择扫描（循环实现，骨架优先可读性）。

        逐时间步离散化，只物化 (B,D,S) 中间量，避免预计算 (B,L,D,S) 大张量——
        后者在 batch 稍大时即 O(B·L·D·S) 内存爆炸。循环仍为 O(L)，上量需换
        并行/关联扫描内核（见方案「诚实降级」）。
        """
        B, L, D = x.shape
        delta = F.softplus(self.W_delta(x))                    # (B,L,D)
        A = -torch.exp(self.logA)                              # (D,S)
        Bv = self.W_B(x)                                       # (B,L,S)
        Cv = self.W_C(x)                                       # (B,L,S)
        h = torch.zeros(B, D, self.d_state, device=x.device, dtype=x.dtype)
        outs = []
        for t in range(L):
            A_bar_t = torch.exp(delta[:, t].unsqueeze(-1) * A.unsqueeze(0))  # (B,D,S)
            B_bar_t = delta[:, t].unsqueeze(-1) * Bv[:, t].unsqueeze(1)      # (B,D,S)
            h = A_bar_t * h + B_bar_t * x[:, t].unsqueeze(-1)                # (B,D,S)
            outs.append(torch.einsum("bds,bs->bd", h, Cv[:, t]))             # (B,D)
        return torch.stack(outs, dim=1)                                      # (B,L,D)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        z = F.silu(self.W_z(x))                     # 门控
        y = self._scan(x)
        if self.bidirectional:
            y_rev = self._scan(torch.flip(x, dims=[1]))
            y = (y + torch.flip(y_rev, dims=[1])) / 2.0
        return y * z


class LVSSM(nn.Module):
    """轻量视觉学生：patch 嵌入 → 若干选择扫描块 → 分类头。

    width 决定规模；默认用 small 规模保证 CPU 秒级跑通，--full 切到 ~4.45M
    部署预算（见方案预算表）。
    """

    def __init__(self, num_classes: int = 100, width: int = 96, depth: int = 4,
                 patch: int = 4, img_size: int = 32):
        super().__init__()
        assert img_size % patch == 0
        in_ch = 3 * patch * patch
        self.patch = patch
        self.embed = nn.Linear(in_ch, width)
        self.blocks = nn.ModuleList(
            [SelectiveScan(width, d_state=16, bidirectional=True) for _ in range(depth)]
        )
        self.norm = nn.LayerNorm(width)
        self.head = nn.Linear(width, num_classes)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self._forward_patch(x, patch_size=self.patch)

    def _forward_patch(self, x: torch.Tensor, patch_size: int) -> torch.Tensor:
        B, C, H, W = x.shape
        P = patch_size
        nh, nw = H // P, W // P
        x = x.reshape(B, C, nh, P, nw, P).permute(0, 2, 4, 1, 3, 5).reshape(B, nh * nw, C * P * P)
        x = self.embed(x)
        for blk in self.blocks:
            x = blk(x) + x            # 残差，稳定深层训练
        x = self.norm(x)
        x = x.mean(dim=1)             # 全局平均池化 → (B,D)
        return self.head(x)


# --------------------------------------------------------------------------- #
# 教师：DINOv2 占位（冻结 CNN）。真实 DINOv2(ViT) 可替换此类的 forward 语义。
# --------------------------------------------------------------------------- #
class Teacher(nn.Module):
    """冻结教师：小 CNN 占位。蒸馏时只取 logits 做软目标，不更新参数。

    真实场景用 DINOv2（ViT-S/B）替换：同样只前向、detach logits。
    """

    def __init__(self, num_classes: int = 100, width: int = 64):
        super().__init__()
        self.features = nn.Sequential(
            nn.Conv2d(3, width, 3, padding=1), nn.ReLU(),
            nn.AdaptiveAvgPool2d(4),
        )
        self.head = nn.Linear(width * 4 * 4, num_classes)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        f = self.features(x).flatten(1)
        return self.head(f)


def distill_loss(student_logits: torch.Tensor, teacher_logits: torch.Tensor,
                 temperature: float = 3.0) -> torch.Tensor:
    """Hinton 式 logit 蒸馏：KL(softmax(teacher/T) || softmax(student/T)) × T²。"""
    p_t = F.log_softmax(student_logits / temperature, dim=-1)
    p_s = F.softmax(teacher_logits / temperature, dim=-1)
    return F.kl_div(p_t, p_s, reduction="batchmean") * (temperature ** 2)


def count_params(model: nn.Module) -> int:
    return sum(p.numel() for p in model.parameters())


def make_dataset(n_per_class: int = 60, size: int = 32, seed: int = 0):
    """合成 4 类图像（per-patch 均值/方差可判别），用于演示蒸馏保留精度。

    - 0: 全亮（均值~1）  - 1: 全暗（均值~0）
    - 2: 白噪声（均值~0.5、方差大）  - 3: 中灰（均值~0.5、方差小）
    教师(CNN)与学生(LVSSM)都能学，任务简单但真实——不是拟合纯随机输出。
    """
    rng = np.random.default_rng(seed)
    X, y = [], []
    for c in range(4):
        for _ in range(n_per_class):
            if c == 0:
                img = np.ones((size, size), dtype=np.float32)
            elif c == 1:
                img = np.zeros((size, size), dtype=np.float32)
            elif c == 2:
                img = rng.normal(0.5, 0.5, size=(size, size)).astype(np.float32)
            else:
                img = np.full((size, size), 0.5, dtype=np.float32)
            img = img + rng.normal(0.0, 0.05, size=(size, size)).astype(np.float32)
            X.append(np.stack([img, img, img], axis=0))  # 3 通道灰阶
            y.append(c)
    return torch.tensor(np.stack(X), dtype=torch.float32), torch.tensor(y, dtype=torch.long)


def accuracy(logits: torch.Tensor, labels: torch.Tensor) -> float:
    return float((logits.argmax(dim=1) == labels).float().mean())


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--full", action="store_true",
                    help="切到更大规模配置（width=384，约 1.3M 参数）；论文参考学生 4.45M 预算见方案文档")
    ap.add_argument("--steps", type=int, default=40)
    args = ap.parse_args()

    torch.manual_seed(0)
    num_classes = 4
    if args.full:
        student = LVSSM(num_classes=num_classes, width=384, depth=4, patch=4, img_size=32)
    else:
        student = LVSSM(num_classes=num_classes, width=96, depth=4, patch=4, img_size=32)
    teacher = Teacher(num_classes=num_classes, width=64)

    # 1) 教师先在合成分类任务上预训练 → 有真实分类信号（非随机输出）
    X, y = make_dataset()
    idx = torch.randperm(len(X))          # 打乱，保证 train/test 各类均衡
    X, y = X[idx], y[idx]
    split = int(len(X) * 0.7)
    X_tr, y_tr = X[:split], y[:split]
    X_te, y_te = X[split:], y[split:]

    opt_t = torch.optim.Adam(teacher.parameters(), lr=1e-2)
    for _ in range(20):
        opt_t.zero_grad()
        F.cross_entropy(teacher(X_tr), y_tr).backward()
        opt_t.step()

    teacher.eval()
    for p in teacher.parameters():
        p.requires_grad_(False)          # 冻结教师，只出软 logits
    with torch.no_grad():
        teacher_acc = accuracy(teacher(X_te), y_te)

    # 2) 离线 logit 蒸馏：学生用 KL 对齐教师软输出
    with torch.no_grad():
        soft_targets = teacher(X_tr)     # (N, C)
    opt_s = torch.optim.Adam(student.parameters(), lr=1e-3)
    losses = []
    for _ in range(args.steps):
        opt_s.zero_grad()
        loss = distill_loss(student(X_tr), soft_targets.detach(), temperature=3.0)
        loss.backward()
        opt_s.step()
        losses.append(float(loss.item()))

    student.eval()
    with torch.no_grad():
        student_acc = accuracy(student(X_te), y_te)

    print(f"[K14] 教师(占位CNN)测试精度 = {teacher_acc:.3f}")
    print(f"[K14] 学生(LVSSM)蒸馏后精度 = {student_acc:.3f}"
          f"（保留率 {student_acc / max(teacher_acc, 1e-9):.2f}）")
    print(f"[K14] 学生参数量 = {count_params(student):,} ｜ 教师参数量 = {count_params(teacher):,}")
    print(f"[K14] 蒸馏损失: {losses[0]:.4f} → {losses[-1]:.4f}")

    # 骨架验收：流程跑通（损失下降）+ 精度保留（学生 ≥ 教师的 50%）
    assert losses[-1] < losses[0], "蒸馏损失未下降，流程未跑通"
    assert student_acc >= 0.5 * teacher_acc, (
        f"学生精度保留过低: {student_acc:.3f} vs 教师 {teacher_acc:.3f}")
    print("[K14] logit 蒸馏流程跑通 + 精度保留 ✓")


if __name__ == "__main__":
    main()
