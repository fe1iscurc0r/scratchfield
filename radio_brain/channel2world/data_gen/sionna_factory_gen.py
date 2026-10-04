"""sionna_factory_gen.py — Channel2World A 线 P0 数据管线（T1）。

主路径：NVIDIA Sionna RT（Apache-2.0）射线追踪，替代商业 Wireless InSite，
生成工厂场景多径信道数据，对齐论文 Table I 参数（7.0 GHz、BS 高 15 m、
UE 高 1.5 m、最多 12 路径、≤3 次反射、衍射关）。Sionna 2.x 已迁移到
DrJit + Mitsuba 后端（不依赖 TensorFlow），可在 Python 3.13 + CPU 上运行。

降级路径（草稿 §七 风险 1）：Sionna 无法安装/运行时，回退到
``specular_tracer.SpecularTracer``（纯 NumPy 镜像源法）。两个后端共享同一
输出 schema（HDF5 + parquet + 数据卡 JSON），T2 无需感知差异。

用法::

    python -m radio_brain.channel2world.data_gen.sionna_factory_gen \
        --backend specular --scenes 1 --bs-per-scene 100 --ue-per-bs 10 --seed 0

数据卡 JSON 校验（环境数 == 配置值）::

    python -c "import json; d=json.load(open('.../datacard.json')); \\
        assert d['num_scenes'] == 1; print(d['num_scenes'], d['num_samples_total'])"
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np

from .specular_tracer import C_LIGHT, FactoryLayout, SpecularTracer

# ---------------------------------------------------------------------------
# 场景几何采样
# ---------------------------------------------------------------------------

_LAYOUT_BASE = FactoryLayout(width=60.0, length=90.0, height=20.0)


def _sample_layout(rng: np.random.Generator, seed_vary: bool) -> FactoryLayout:
    """采样一个工厂布局。seed_vary=True 时按种子微调尺寸以产生多环境差异。"""
    if not seed_vary:
        return _LAYOUT_BASE
    width = rng.uniform(45.0, 75.0)
    length = rng.uniform(70.0, 120.0)
    height = rng.uniform(18.0, 25.0)  # 必须 > BS 高 15 m
    return FactoryLayout(width=float(width), length=float(length), height=float(height))


def _sample_positions(
    rng: np.random.Generator,
    layout: FactoryLayout,
    n_bs: int,
    n_ue_per_bs: int,
    bs_height: float,
    ue_height: float,
    margin: float = 2.0,
) -> tuple[np.ndarray, np.ndarray]:
    """采样 BS 与 UE 位置。

    返回 (bs_positions (n_bs,3), ue_positions (n_bs, n_ue_per_bs, 3))，xy 在
    工厂内部（离墙 margin 米），z 分别为 bs_height / ue_height。
    """
    x_lo, x_hi = margin, layout.width - margin
    y_lo, y_hi = margin, layout.length - margin

    bs = np.empty((n_bs, 3), dtype=np.float32)
    bs[:, 0] = rng.uniform(x_lo, x_hi, size=n_bs)
    bs[:, 1] = rng.uniform(y_lo, y_hi, size=n_bs)
    bs[:, 2] = bs_height

    ue = np.empty((n_bs, n_ue_per_bs, 3), dtype=np.float32)
    ue[:, :, 0] = rng.uniform(x_lo, x_hi, size=(n_bs, n_ue_per_bs))
    ue[:, :, 1] = rng.uniform(y_lo, y_hi, size=(n_bs, n_ue_per_bs))
    ue[:, :, 2] = ue_height
    return bs, ue


# ---------------------------------------------------------------------------
# 后端接口（Sionna 主路径 + 镜面反射降级路径）
# ---------------------------------------------------------------------------


@dataclass
class SceneRecord:
    """单个工厂环境的一批信道-位置对。"""

    scene_id: int
    layout: FactoryLayout
    bs_position: np.ndarray  # (n_bs, 3)
    ue_position: np.ndarray  # (n_bs, n_ue, 3)
    num_paths: np.ndarray  # (n_bs, n_ue) int32
    tau_rel: np.ndarray  # (n_bs, n_ue, max_paths) float32，NaN 填充
    aoa_theta: np.ndarray
    aoa_phi: np.ndarray
    gain_rel: np.ndarray


def _empty_record(scene_id: int, layout: FactoryLayout, bs: np.ndarray, ue: np.ndarray, max_paths: int) -> SceneRecord:
    n_bs, n_ue, _ = ue.shape
    return SceneRecord(
        scene_id=scene_id,
        layout=layout,
        bs_position=bs,
        ue_position=ue,
        num_paths=np.zeros((n_bs, n_ue), dtype=np.int32),
        tau_rel=np.full((n_bs, n_ue, max_paths), np.nan, dtype=np.float32),
        aoa_theta=np.full((n_bs, n_ue, max_paths), np.nan, dtype=np.float32),
        aoa_phi=np.full((n_bs, n_ue, max_paths), np.nan, dtype=np.float32),
        gain_rel=np.full((n_bs, n_ue, max_paths), np.nan, dtype=np.float32),
    )


def _build_room_ply(width: float, length: float, height: float) -> str:
    """生成内法线（指向房间内部）的立方体 PLY 文本，供 Mitsuba 场景使用。"""
    w, l, h = width, length, height
    verts = [
        (0, 0, 0), (w, 0, 0), (w, l, 0), (0, l, 0),
        (0, 0, h), (w, 0, h), (w, l, h), (0, l, h),
    ]
    # 12 个三角形（6 面 × 2），法线指向房间内部
    faces = [
        (0, 1, 2), (0, 2, 3),  # 地面  +z
        (4, 7, 6), (4, 6, 5),  # 天花板 -z
        (0, 3, 7), (0, 7, 4),  # x=0  +x
        (1, 5, 6), (1, 6, 2),  # x=W  -x
        (0, 4, 5), (0, 5, 1),  # y=0  +y
        (3, 2, 6), (3, 6, 7),  # y=L  -y
    ]
    lines = [
        "ply", "format ascii 1.0",
        "element vertex 8",
        "property float x", "property float y", "property float z",
        "element face 12",
        "property list uchar int vertex_indices",
        "end_header",
    ]
    lines += [f"{x} {y} {z}" for x, y, z in verts]
    lines += ["3 %d %d %d" % f for f in faces]
    return "\n".join(lines)


def _build_factory_scene(layout: FactoryLayout, workdir: Path) -> Path:
    """把工厂布局写成 Mitsuba XML 场景（金属材质矩形房间），返回 XML 路径。"""
    workdir.mkdir(parents=True, exist_ok=True)
    ply_path = workdir / "room.ply"
    ply_path.write_text(_build_room_ply(layout.width, layout.length, layout.height), encoding="utf-8")
    xml = (
        '<scene version="2.1.0">\n'
        '  <bsdf type="itu-radio-material" id="wall-mat">\n'
        '    <string name="type" value="metal"/>\n'
        '    <float name="thickness" value="0.5"/>\n'
        '  </bsdf>\n'
        '  <shape type="ply" id="room">\n'
        f'    <string name="filename" value="{ply_path.as_posix()}"/>\n'
        '    <boolean name="face_normals" value="true"/>\n'
        '    <ref id="wall-mat" name="bsdf"/>\n'
        '  </shape>\n'
        '</scene>\n'
    )
    xml_path = workdir / "room.xml"
    xml_path.write_text(xml, encoding="utf-8")
    return xml_path


def _extract_sionna_paths(paths, max_paths: int) -> dict:
    """Sionna Paths 对象 → 与 specular tracer 同构的多径参数字典。

    Sionna 2.0 的 ``a`` 为 (实部, 虚部) 元组；增益取 |a|²，按时延升序（LOS 首径）
    取前 max_paths 条，输出相对时延 / 相对增益。
    """
    tau = np.asarray(paths.tau).reshape(-1)
    theta_r = np.asarray(paths.theta_r).reshape(-1)
    phi_r = np.asarray(paths.phi_r).reshape(-1)
    a = (np.asarray(paths.a[0]) + 1j * np.asarray(paths.a[1])).reshape(-1)
    valid = np.asarray(paths.valid).reshape(-1).astype(bool)
    power = np.abs(a) ** 2

    order = np.argsort(np.where(valid, tau, np.inf))[:max_paths]
    tau = tau[order]
    theta_r = theta_r[order]
    phi_r = phi_r[order]
    power = power[order]
    return {
        "tau_rel": (tau - tau[0]).astype(np.float32),
        "aoa_theta": theta_r.astype(np.float32),
        "aoa_phi": phi_r.astype(np.float32),
        "gain_rel": (10.0 * np.log10(power / (power[0] + 1e-12))).astype(np.float32),
        "num_paths": int(tau.shape[0]),
    }


def generate_sionna(
    *,
    scenes: int,
    bs_per_scene: int,
    ue_per_bs: int,
    seed: int,
    max_reflections: int,
    max_paths: int,
    frequency_hz: float,
    bs_height: float,
    ue_height: float,
) -> list[SceneRecord]:
    """Sionna RT 主路径（Sionna 2.0 / DrJit + Mitsuba，已在本环境实测可用）。"""
    try:
        import mitsuba as mi
        from sionna.rt import PathSolver, PlanarArray, Receiver, Transmitter, load_scene
    except ImportError as exc:  # pragma: no cover - 取决于部署环境
        raise RuntimeError(
            "Sionna RT 未安装（pip install sionna 即可，Sionna 2.x 不再依赖 TensorFlow）。"
            "若无法安装，请改用 --backend specular 走镜面反射降级路径。"
        ) from exc

    rng = np.random.default_rng(seed)
    records: list[SceneRecord] = []
    workdir = Path(tempfile.mkdtemp(prefix="c2w_sionna_"))

    for scene_id in range(scenes):
        layout = _sample_layout(rng, seed_vary=scenes > 1)
        bs, ue = _sample_positions(rng, layout, bs_per_scene, ue_per_bs, bs_height, ue_height)
        rec = _empty_record(scene_id, layout, bs, ue, max_paths)

        xml_path = _build_factory_scene(layout, workdir / f"scene_{scene_id:03d}")
        scene = load_scene(str(xml_path))
        scene.frequency = frequency_hz
        scene.tx_array = PlanarArray(num_rows=1, num_cols=1, pattern="iso", polarization="V")
        scene.rx_array = PlanarArray(num_rows=1, num_cols=1, pattern="iso", polarization="V")

        tx = Transmitter(name="tx", position=mi.Point3f(*bs[0].tolist()))
        rx = Receiver(name="rx", position=mi.Point3f(*ue[0, 0].tolist()))
        scene.add(tx)
        scene.add(rx)
        solver = PathSolver()

        for i in range(bs_per_scene):
            tx.position = mi.Point3f(*bs[i].tolist())
            for j in range(ue_per_bs):
                rx.position = mi.Point3f(*ue[i, j].tolist())
                paths = solver(
                    scene,
                    max_depth=max_reflections,
                    los=True,
                    specular_reflection=True,
                    refraction=False,
                    diffraction=False,
                    edge_diffraction=False,
                    max_num_paths_per_src=256,
                    seed=seed,
                )
                out = _extract_sionna_paths(paths, max_paths)
                n = out["num_paths"]
                rec.num_paths[i, j] = n
                rec.tau_rel[i, j, :n] = out["tau_rel"]
                rec.aoa_theta[i, j, :n] = out["aoa_theta"]
                rec.aoa_phi[i, j, :n] = out["aoa_phi"]
                rec.gain_rel[i, j, :n] = out["gain_rel"]
        records.append(rec)
    return records


def generate_specular(
    *,
    scenes: int,
    bs_per_scene: int,
    ue_per_bs: int,
    seed: int,
    max_reflections: int,
    max_paths: int,
    frequency_hz: float,
    bs_height: float,
    ue_height: float,
) -> list[SceneRecord]:
    """镜面反射降级路径（本环境实测路径，纯 NumPy）。"""
    rng = np.random.default_rng(seed)
    records: list[SceneRecord] = []
    for scene_id in range(scenes):
        layout = _sample_layout(rng, seed_vary=scenes > 1)
        bs, ue = _sample_positions(rng, layout, bs_per_scene, ue_per_bs, bs_height, ue_height)
        rec = _empty_record(scene_id, layout, bs, ue, max_paths)
        tracer = SpecularTracer(layout, max_reflections=max_reflections, max_paths=max_paths, frequency_hz=frequency_hz)
        for i in range(bs_per_scene):
            for j in range(ue_per_bs):
                out = tracer.trace(bs[i], ue[i, j])
                n = int(out["num_paths"])
                rec.num_paths[i, j] = n
                rec.tau_rel[i, j, :n] = out["tau_rel"]
                rec.aoa_theta[i, j, :n] = out["aoa_theta"]
                rec.aoa_phi[i, j, :n] = out["aoa_phi"]
                rec.gain_rel[i, j, :n] = out["gain_rel"]
        records.append(rec)
    return records


# ---------------------------------------------------------------------------
# 落盘：HDF5 + parquet + 数据卡 JSON
# ---------------------------------------------------------------------------


def write_hdf5(records: list[SceneRecord], path: Path, cfg: dict) -> None:
    import h5py

    with h5py.File(path, "w") as f:
        scalar_attrs = {k: v for k, v in cfg.items() if isinstance(v, (str, int, float, bool))}
        f.attrs.update(scalar_attrs)
        for rec in records:
            grp = f.create_group(f"scene_{rec.scene_id:03d}")
            grp.create_dataset("bs_position", data=rec.bs_position)
            grp.create_dataset("ue_position", data=rec.ue_position)
            grp.create_dataset("num_paths", data=rec.num_paths)
            grp.create_dataset("tau_rel", data=rec.tau_rel)
            grp.create_dataset("aoa_theta", data=rec.aoa_theta)
            grp.create_dataset("aoa_phi", data=rec.aoa_phi)
            grp.create_dataset("gain_rel", data=rec.gain_rel)


def write_parquet(records: list[SceneRecord], path: Path) -> None:
    import pandas as pd

    rows: list[dict] = []
    for rec in records:
        n_bs, n_ue, max_paths = rec.tau_rel.shape
        for i in range(n_bs):
            for j in range(n_ue):
                np_ = int(rec.num_paths[i, j])
                for p in range(np_):
                    rows.append(
                        {
                            "scene_id": rec.scene_id,
                            "bs_idx": i,
                            "ue_idx": j,
                            "path_idx": p,
                            "num_paths": np_,
                            "tau_rel": float(rec.tau_rel[i, j, p]),
                            "aoa_theta": float(rec.aoa_theta[i, j, p]),
                            "aoa_phi": float(rec.aoa_phi[i, j, p]),
                            "gain_rel": float(rec.gain_rel[i, j, p]),
                            "ue_x": float(rec.ue_position[i, j, 0]),
                            "ue_y": float(rec.ue_position[i, j, 1]),
                            "ue_z": float(rec.ue_position[i, j, 2]),
                            "bs_x": float(rec.bs_position[i, 0]),
                            "bs_y": float(rec.bs_position[i, 1]),
                            "bs_z": float(rec.bs_position[i, 2]),
                        }
                    )
    pd.DataFrame(rows).to_parquet(path, index=False, engine="pyarrow")


def _params_range(records: list[SceneRecord]) -> dict:
    def rng_of(arr: np.ndarray) -> dict:
        valid = arr[~np.isnan(arr)]
        if valid.size == 0:
            return {"min": None, "max": None}
        return {"min": float(valid.min()), "max": float(valid.max())}

    tau = np.concatenate([r.tau_rel for r in records])
    th = np.concatenate([r.aoa_theta for r in records])
    ph = np.concatenate([r.aoa_phi for r in records])
    g = np.concatenate([r.gain_rel for r in records])
    ue = np.concatenate([r.ue_position.reshape(-1, 3) for r in records])
    return {
        "relative_delay_ns": {"min": rng_of(tau)["min"] * 1e9 if rng_of(tau)["min"] is not None else None,
                              "max": rng_of(tau)["max"] * 1e9 if rng_of(tau)["max"] is not None else None},
        "aoa_theta_deg": {k: (v * 180.0 / np.pi if v is not None else None) for k, v in rng_of(th).items()},
        "aoa_phi_deg": {k: (v * 180.0 / np.pi if v is not None else None) for k, v in rng_of(ph).items()},
        "relative_gain_db": rng_of(g),
        "ue_x_m": {"min": float(ue[:, 0].min()), "max": float(ue[:, 0].max())},
        "ue_y_m": {"min": float(ue[:, 1].min()), "max": float(ue[:, 1].max())},
    }


def write_datacard(records: list[SceneRecord], path: Path, cfg: dict) -> None:
    card = {
        "backend": cfg["backend"],
        "num_scenes": len(records),
        "bs_per_scene": cfg["bs_per_scene"],
        "ue_per_bs": cfg["ue_per_bs"],
        "seed": cfg["seed"],
        "frequency_hz": cfg["frequency_hz"],
        "bs_height_m": cfg["bs_height"],
        "ue_height_m": cfg["ue_height"],
        "max_paths": cfg["max_paths"],
        "max_reflections": cfg["max_reflections"],
        "diffraction": False,
        "layout_per_scene": [asdict(r.layout) for r in records],
        "num_samples_total": sum(int(r.ue_position.shape[0]) * int(r.ue_position.shape[1]) for r in records),
        "params_range": _params_range(records),
        "outputs": {
            "hdf5": str(cfg["out_dir"] / "factory_channels.h5"),
            "parquet": str(cfg["out_dir"] / "factory_channels.parquet"),
            "datacard": str(path),
        },
    }
    path.write_text(json.dumps(card, ensure_ascii=False, indent=2), encoding="utf-8")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Channel2World T1 工厂信道数据生成器")
    p.add_argument("--backend", choices=["sionna", "specular"], default="sionna",
                   help="射线追踪后端：sionna 主路径 / specular 镜面反射降级路径")
    p.add_argument("--scenes", type=int, default=1, help="工厂环境（布局）数 N")
    p.add_argument("--bs-per-scene", type=int, default=100, help="每环境 BS 位置数 M")
    p.add_argument("--ue-per-bs", type=int, default=10, help="每 BS 的 UE 位置数 K")
    p.add_argument("--seed", type=int, default=0, help="随机种子")
    p.add_argument("--max-reflections", type=int, default=3, help="最大反射次数（≤3）")
    p.add_argument("--max-paths", type=int, default=12, help="每信道最大输出路径数")
    p.add_argument("--freq-hz", type=float, default=7.0e9, help="载波频率 (Hz)")
    p.add_argument("--bs-height", type=float, default=15.0, help="BS 高度 (m)")
    p.add_argument("--ue-height", type=float, default=1.5, help="UE 高度 (m)")
    p.add_argument("--out-dir", type=str, default=None, help="输出目录")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    repo_root = Path(__file__).resolve().parents[3]
    out_dir = Path(args.out_dir) if args.out_dir else repo_root / "radio_brain" / "channel2world" / "data"
    out_dir.mkdir(parents=True, exist_ok=True)

    cfg = {
        "backend": args.backend,
        "bs_per_scene": args.bs_per_scene,
        "ue_per_bs": args.ue_per_bs,
        "seed": args.seed,
        "frequency_hz": args.freq_hz,
        "bs_height": args.bs_height,
        "ue_height": args.ue_height,
        "max_paths": args.max_paths,
        "max_reflections": args.max_reflections,
        "out_dir": out_dir,
    }

    if args.backend == "sionna":
        records = generate_sionna(
            scenes=args.scenes, bs_per_scene=args.bs_per_scene, ue_per_bs=args.ue_per_bs,
            seed=args.seed, max_reflections=args.max_reflections, max_paths=args.max_paths,
            frequency_hz=args.freq_hz, bs_height=args.bs_height, ue_height=args.ue_height,
        )
    else:
        records = generate_specular(
            scenes=args.scenes, bs_per_scene=args.bs_per_scene, ue_per_bs=args.ue_per_bs,
            seed=args.seed, max_reflections=args.max_reflections, max_paths=args.max_paths,
            frequency_hz=args.freq_hz, bs_height=args.bs_height, ue_height=args.ue_height,
        )

    h5_path = out_dir / "factory_channels.h5"
    pq_path = out_dir / "factory_channels.parquet"
    card_path = out_dir / "datacard.json"

    write_hdf5(records, h5_path, cfg)
    write_parquet(records, pq_path)
    write_datacard(records, card_path, cfg)

    total = sum(int(r.ue_position.shape[0]) * int(r.ue_position.shape[1]) for r in records)
    print(f"[T1] backend={args.backend} scenes={args.scenes} samples={total}")
    print(f"[T1] HDF5   -> {h5_path}")
    print(f"[T1] parquet-> {pq_path}")
    print(f"[T1] datacard-> {card_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
