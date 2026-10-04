"""token-savior 压缩比复测脚本（W99-02 · 可复现的真实数字）。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import tiktoken
from token_savior.project_indexer import ProjectIndexer


def measure(root: Path) -> dict:
    """对给定源码目录做 原始 vs 结构索引 的 token 对比（cl100k_base）。"""
    enc = tiktoken.get_encoding("cl100k_base")
    py_files = sorted(
        p for p in root.rglob("*.py")
        if "test" not in p.name and "__pycache__" not in str(p)
    )
    raw_text = "\n".join(
        f"# file: {p}" + p.read_text(encoding="utf-8", errors="replace")
        for p in py_files
    )
    raw_tokens = len(enc.encode(raw_text))

    index = ProjectIndexer(str(root)).index()
    parts = []
    for p in py_files:
        meta = index.files.get(str(p).replace("\\", "/")) or index.files.get(p.name)
        if meta is None:
            continue
        parts.append(f"{p.name}: {len(meta.functions)} funcs, {len(meta.classes)} classes")
        for f in meta.functions[:40]:
            parts.append(f"  def {f.name}")
        for c in meta.classes[:20]:
            parts.append(f"  class {c.name}")
    compact_tokens = len(enc.encode("\n".join(parts)))
    return {
        "files": len(py_files),
        "raw_tokens": raw_tokens,
        "compact_tokens": compact_tokens,
        "ratio_pct": round(100.0 * compact_tokens / raw_tokens, 1) if raw_tokens else 0.0,
        "total_lines": index.total_lines,
        "total_functions": index.total_functions,
    }


def main() -> None:
    import json

    root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("mcpserver/rf_brain/decoders")
    print(json.dumps(measure(root), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
