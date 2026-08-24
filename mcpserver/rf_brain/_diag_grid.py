"""诊断：MUSIC RMSE 低于 CRB 的根因——网格吸引子假说验证。

场景 A：θ=30.00°（恰在 0.1° 网格上）
场景 B：θ=30.04°（不在网格上）
各 2000 次 MC，SNR=30dB, K=256, M=8, refine=True/False 对比。
若场景 B 的 RMSE 回到 CRB 量级，则高 SNR 段"低于 CRB"是网格+插值吸引子所致。
"""
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from mcpserver.rf_brain.doa import estimate_doa, synthesize_snapshots

M, K, SNR_DB = 8, 256, 30.0
CRB_DEG = 0.004542  # coeff=1.0 数值 FIM 结果（与 bench_doa.crb_single_deg 一致）


def run(theta_true, refine, n_mc=2000, seed_base=9000):
    errs = []
    for i in range(n_mc):
        x = synthesize_snapshots([theta_true], n_elements=M, n_snapshot=K,
                                 snr_db=SNR_DB, seed=seed_base + i)
        est = estimate_doa(x, n_sources=1, refine=refine)
        errs.append(float(est.doas_deg[0]) - theta_true)
    errs = np.asarray(errs)
    return float(errs.mean()), float(np.sqrt(np.mean(errs ** 2)))


print(f"CRB(coeff=1.0) = {CRB_DEG:.6f}°  (M=8, K=256, SNR=30dB, θ≈30°)")
for theta_true, tag in ((30.00, "A:θ=30.00° 网格上"), (30.04, "B:θ=30.04° 网格间")):
    for refine in (True, False):
        bias, rmse = run(theta_true, refine)
        flag = " <CRB!" if rmse < CRB_DEG else ""
        print(f"{tag}  refine={refine!s:<5}  bias={bias:+.6f}°  RMSE={rmse:.6f}°{flag}")
