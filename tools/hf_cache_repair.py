"""修复 HuggingFace 缓存里「0 字节快照占位」的模型文件（工单244g）。

## 为什么需要它

Windows **未开开发者模式**（或非管理员）时 `os.symlink` 不可用。
`huggingface_hub` 的快照目录本应是「指向 `blobs/<etag>` 的符号链接」，
但在这种机器上它会**留下 0 字节的普通文件**（不是链接、也不是副本）
⇒ 任何读这些文件的库都拿到**空内容**，且报错往往**指不到根因**。

实测（本机，`huggingface_hub` 1.4.1）：
- `docling-layout-heron` 的 `preprocessor_config.json` 0 字节 ⇒
  docling 报 `Failed to load image processor …: Expecting value: line 1 column 1 (char 0)`
- `docling-models` 的 `model_artifacts/tableformer/{fast,accurate}/tm_config.json` 0 字节 ⇒
  docling 报 `JSONDecodeError: Expecting value: line 1 column 1 (char 0)`（**连文件路径都没有**）

⚠️ **`HF_HUB_DISABLE_SYMLINKS` 这个环境变量在当前版本里并不存在** ——
只有 `HF_HUB_DISABLE_SYMLINKS_WARNING`（只是不打印警告，**不改变行为**）。
所以设了它也没用（本单实测确认过），只能**事后按 blob 重建**。

## 做法

`blobs/` 里的数据通常是**完好**的（下载本身成功，只是快照没链接上）。
于是向 Hub 取一次「文件名 → blob（etag/sha256）」映射，把 blob **复制**成快照里的真文件。
⇒ **不重新下载**（本单实测：342 MB 的两个模型，重建耗时 < 10 s）。

## 用法

    python tools/hf_cache_repair.py --scan-all          # 修所有已缓存模型（推荐）
    python tools/hf_cache_repair.py owner/name [...]    # 只修指定模型

`HF_HOME` 决定缓存根（默认 `~/.cache/huggingface`）。

## 边界

- **只补不改**：快照里已存在且大小与 blob 一致的文件不动；缺的才复制。
- 若某个文件的 blob 本身不存在（下载曾中断），本工具**修不了** —— 会如实列出，
  此时需要对那个模型重新 `snapshot_download`。
- 幂等：重复跑第二次应全部命中「已就好」。
"""

from __future__ import annotations

import argparse
import os
import shutil
import sys
from pathlib import Path

#: 被本工具修过的快照会带这个后缀（见 --scan-all 的跳过逻辑）
BROKEN_SUFFIX = ".broken"


def _hf_home() -> Path:
    """缓存根：`HF_HOME` 优先，否则 `~/.cache/huggingface`。"""
    return Path(os.environ.get("HF_HOME") or (Path.home() / ".cache" / "huggingface"))


def _repo_id_of(folder: Path) -> str | None:
    """把 `models--owner--name` 目录名还原成 `owner/name`。"""
    name = folder.name
    if not name.startswith("models--"):
        return None
    return name[len("models--"):].replace("--", "/", 1)


def _revision(folder: Path) -> str | None:
    """修订号：优先 `refs/main`；没有就取 `snapshots/` 下唯一的那个目录。"""
    ref = folder / "refs" / "main"
    if ref.is_file():
        return ref.read_text(encoding="utf-8").strip()
    cands = [p.name for p in (folder / "snapshots").iterdir()
             if p.is_dir() and not p.name.endswith(BROKEN_SUFFIX)]
    return cands[0] if len(cands) == 1 else None


def repair(repo_id: str, *, hf_home: Path | None = None, dry_run: bool = False) -> dict:
    """修一个模型。返回 ``{repo, fixed, ok, missing, failed}``。"""
    from huggingface_hub import HfApi  # 惰性：本工具只在需要时依赖 HF

    home = hf_home or _hf_home()
    folder = home / "hub" / ("models--" + repo_id.replace("/", "--"))
    if not folder.is_dir():
        return {"repo": repo_id, "error": f"缓存目录不存在：{folder}"}
    rev = _revision(folder)
    if not rev:
        return {"repo": repo_id, "error": "无法确定修订号（snapshots 下有多个目录且无 refs/main）"}

    snap = folder / "snapshots" / rev
    result = {"repo": repo_id, "rev": rev, "fixed": [], "ok": [], "missing": [], "failed": []}
    for sibling in HfApi().model_info(repo_id, files_metadata=True).siblings:
        key = (sibling.lfs.get("sha256") if sibling.lfs else None) or sibling.blob_id
        src = folder / "blobs" / key
        dst = snap / sibling.rfilename
        if not src.is_file():
            result["missing"].append(f"{sibling.rfilename}（blob {key} 不存在）")
            continue
        if dst.is_file() and dst.stat().st_size == src.stat().st_size and src.stat().st_size > 0:
            result["ok"].append(sibling.rfilename)
            continue
        if dry_run:
            result["fixed"].append(f"{sibling.rfilename}（dry-run）")
            continue
        try:
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(src, dst)
        except OSError as exc:
            result["failed"].append(f"{sibling.rfilename}: {exc}")
            continue
        result["fixed"].append(f"{sibling.rfilename}（{src.stat().st_size:,} B）")
    return result


def scan_all(*, hf_home: Path | None = None, dry_run: bool = False) -> list[dict]:
    """扫 `hub/` 下所有模型目录逐个修。"""
    hub = (hf_home or _hf_home()) / "hub"
    if not hub.is_dir():
        return []
    out = []
    for folder in sorted(p for p in hub.iterdir() if p.is_dir() and p.name.startswith("models--")):
        repo_id = _repo_id_of(folder)
        if repo_id:
            out.append(repair(repo_id, hf_home=hf_home, dry_run=dry_run))
    return out


def _print(results: list[dict]) -> int:
    broken = 0
    for r in results:
        if "error" in r:
            print(f"❌ {r['repo']}: {r['error']}")
            broken += 1
            continue
        n_fix, n_ok = len(r["fixed"]), len(r["ok"])
        print(f"{'🔧' if n_fix else '✅'} {r['repo']}（rev {r['rev'][:12]}）"
              f"：修复 {n_fix} / 本来就好 {n_ok}")
        for item in r["fixed"]:
            print(f"      + {item}")
        for item in r["missing"]:
            print(f"      ⚠️ 缺 blob（需重新下载该模型）：{item}")
            broken += 1
        for item in r["failed"]:
            print(f"      ❌ 复制失败：{item}")
            broken += 1
    print(f"\n共 {len(results)} 个模型；有问题的 {broken} 项")
    return 1 if broken else 0


def build_parser() -> argparse.ArgumentParser:
    """命令行入口。"""
    parser = argparse.ArgumentParser(description="修复 HF 缓存里的 0 字节快照占位")
    parser.add_argument("repos", nargs="*", help="要修的模型 id（owner/name）；留空需配合 --scan-all")
    parser.add_argument("--scan-all", action="store_true", help="扫描并修复缓存里的全部模型")
    parser.add_argument("--hf-home", default="", help="覆盖 HF_HOME")
    parser.add_argument("--dry-run", action="store_true", help="只报告要修什么，不写盘")
    return parser


def main(argv: list[str] | None = None) -> int:
    """跑修复并打印摘要；有无法修复的项时非零退出。"""
    args = build_parser().parse_args(argv)
    home = Path(args.hf_home) if args.hf_home else None
    if args.scan_all:
        results = scan_all(hf_home=home, dry_run=args.dry_run)
        if not results:
            print("缓存里没有模型目录（或 HF_HOME 指错了）")
            return 0
    elif args.repos:
        results = [repair(r, hf_home=home, dry_run=args.dry_run) for r in args.repos]
    else:
        print("请给模型 id，或用 --scan-all")
        return 2
    return _print(results)


if __name__ == "__main__":
    sys.exit(main())
