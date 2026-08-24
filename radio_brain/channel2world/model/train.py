"""预训练脚本：上下文 128 信道 → 无线世界嵌入 → 预测 query 32 信道。

用法::

    python -m radio_brain.channel2world.model.train \
        --data radio_brain/channel2world/data/factory_channels.h5 \
        --context 128 --query 32 --batch 32 --steps 100 --out-dir logs/smoke

小规模冒烟（CPU、batch 减半或更小）::

    python -m radio_brain.channel2world.model.train \
        --data radio_brain/channel2world/data/factory_channels.h5 \
        --context 32 --query 8 --batch 8 --steps 60 --out-dir logs/smoke

产出：checkpoint（model.pt）+ 收敛日志（train_log.jsonl，含位置 NLL / 增益 RMSE）。
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import torch
from torch.utils.data import DataLoader

from .dataset import Channel2WorldDataset, DatasetConfig, collate
from .encoder import Channel2WorldModel
from .losses import compute_losses


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Channel2World T2 预训练")
    p.add_argument("--data", type=str, required=True, help="HDF5 数据路径")
    p.add_argument("--context", type=int, default=128, help="上下文信道数")
    p.add_argument("--query", type=int, default=32, help="query 信道数")
    p.add_argument("--batch", type=int, default=32, help="batch size")
    p.add_argument("--steps", type=int, default=200, help="训练步数")
    p.add_argument("--lr", type=float, default=3e-4)
    p.add_argument("--d-model", type=int, default=128)
    p.add_argument("--kz", type=int, default=16)
    p.add_argument("--heads", type=int, default=4)
    p.add_argument("--n-components", type=int, default=4)
    p.add_argument("--num-splits", type=int, default=64)
    p.add_argument("--error-injection", action="store_true", help="误差注入开关")
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--log-steps", type=int, default=10)
    p.add_argument("--out-dir", type=str, default=None)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    torch.manual_seed(args.seed)

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    out_dir = Path(args.out_dir) if args.out_dir else Path("radio_brain/channel2world/logs")
    out_dir.mkdir(parents=True, exist_ok=True)

    cfg = DatasetConfig(
        hdf5_path=args.data,
        context_size=args.context,
        query_size=args.query,
        num_splits=args.num_splits,
        error_injection=args.error_injection,
        seed=args.seed,
    )
    dataset = Channel2WorldDataset(cfg)
    loader = DataLoader(dataset, batch_size=args.batch, shuffle=True, collate_fn=collate)

    model = Channel2WorldModel(
        d_in=9,
        d_model=args.d_model,
        kz=args.kz,
        heads=args.heads,
        n_components=args.n_components,
    ).to(device)
    n_params = model.num_parameters()
    optimizer = torch.optim.AdamW(model.parameters(), lr=args.lr)

    print(f"[T2] device={device} params={n_params:,} context={args.context} query={args.query} batch={args.batch}")
    log_path = out_dir / "train_log.jsonl"
    log_path.unlink(missing_ok=True)

    step = 0
    epoch = 0
    while step < args.steps:
        for batch in loader:
            if step >= args.steps:
                break
            b = {k: v.to(device) for k, v in batch.items()}
            out = model(
                b["context_x"], b["context_mask"], b["query_x"], b["query_mask"], b["channel_index"]
            )
            loss, comps = compute_losses(
                out,
                b["path_pos_target"],
                b["gain_target"],
                b["ch_pos_target"],
                path_mask=b["query_mask"],
            )
            optimizer.zero_grad(set_to_none=True)
            loss.backward()
            optimizer.step()

            if step % args.log_steps == 0 or step == args.steps - 1:
                gain_rmse = math.sqrt(float(comps["gain"].item()))
                rec = {
                    "epoch": epoch,
                    "step": step,
                    "total_loss": float(loss.item()),
                    "path_pos_nll": float(comps["path_pos"].item()),
                    "gain_rmse_db": gain_rmse,
                    "ch_pos_nll": float(comps["ch_pos"].item()),
                }
                with log_path.open("a", encoding="utf-8") as fh:
                    fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
                print(
                    f"step {step:4d} loss {loss.item():8.4f} | "
                    f"path_nll {comps['path_pos'].item():7.3f} "
                    f"gain_rmse {gain_rmse:6.3f} "
                    f"ch_nll {comps['ch_pos'].item():7.3f}"
                )
            step += 1
        epoch += 1

    ckpt_path = out_dir / "model.pt"
    torch.save({"model_state": model.state_dict(), "args": vars(args), "n_params": n_params}, ckpt_path)
    print(f"[T2] checkpoint -> {ckpt_path}")
    print(f"[T2] log       -> {log_path}")
    print(f"[T2] params    -> {n_params:,} (~9.2M 参考，不强制精确)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
