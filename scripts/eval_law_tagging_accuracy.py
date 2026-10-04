"""卷164 实测门槛辅助脚本：20 篇判决书案由分类准确率评估。

用法（**需要真实 Von 服务在线**）::

    .venv/Scripts/python.exe scripts/eval_law_tagging_accuracy.py --cases <dir>

``<dir>`` 内放 20 篇真实判决书（.docx/.pdf/.xlsx），并附一个 ``labels.json``::

    {"文件名.docx": "合同纠纷", ...}

脚本流程：导入 → 打标 → 与人工标注对比 → 输出准确率与逐条明细。

**诚实声明**：本脚本不内置任何「真实判决书」数据。工单要求的 20 篇实测样本
需由项目方提供（涉版权与个人信息，不入仓库）。在无样本/无 Von 服务时，
脚本会明确报告「无法实测」，**不会伪造结果**。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

#: 案由问题键（与 pack.yaml 蓝图一致）。
CAUSE_KEY = "案由分类"


def evaluate(cases_dir: Path, endpoint: str | None) -> int:
    """对 cases_dir 下判决书打标并与 labels.json 对比。返回退出码。"""
    labels_path = cases_dir / "labels.json"
    if not labels_path.is_file():
        print(f"[SKIP] 缺少人工标注 {labels_path}，无法计算准确率。")
        print("       请提供 20 篇真实判决书 + labels.json 后重跑。")
        return 2

    labels: dict[str, str] = json.loads(labels_path.read_text(encoding="utf-8"))
    if len(labels) < 20:
        print(f"[WARN] 工单要求 20 篇，当前仅 {len(labels)} 篇。")

    files = [
        p for p in sorted(cases_dir.iterdir())
        if p.suffix.lower() in (".docx", ".pdf", ".xlsx")
    ]
    if not files:
        print(f"[SKIP] {cases_dir} 下无 .docx/.pdf/.xlsx 文件。")
        return 2

    from system.config import get_config

    cfg = get_config()
    if endpoint:
        cfg.von.endpoint = endpoint
    if not cfg.von.enabled:
        print("[SKIP] von.enabled=false，请先启动 Von 并启用打标。")
        return 2

    from apiserver.von_client import VonError, get_von_client

    client = get_von_client()
    if not client.is_alive(force=True):
        print(f"[SKIP] Von 服务离线（{client.endpoint}），无法实测。")
        print("       部署步骤见 docs/von-部署-2026-09-27.md")
        return 2

    from domains.law.importers import case_import as ci
    from domains.law.importers import tagging

    hits = 0
    rows: list[dict] = []
    for f in files:
        expected = labels.get(f.name, "")
        try:
            item = ci.process_upload(f.name, f.read_bytes())
        except ci.ParseError as exc:
            rows.append({"file": f.name, "expected": expected, "got": None,
                         "ok": False, "error": str(exc)})
            continue
        if not item.ok or not item.cases:
            rows.append({"file": f.name, "expected": expected, "got": None,
                         "ok": False, "error": item.error})
            continue
        case = item.cases[0]
        try:
            result = tagging.tag_case(
                parties=case.parties, cause_of_action=case.cause_of_action,
                court=case.court, trial_level=case.trial_level,
                content=case.content, case_no=case.case_no, client=client,
            )
        except VonError as exc:
            rows.append({"file": f.name, "expected": expected, "got": None,
                         "ok": False, "error": str(exc)})
            continue
        got = result.tags.get(CAUSE_KEY)
        got_value = got.value if got else None
        ok = got_value == expected
        hits += int(ok)
        rows.append({
            "file": f.name, "expected": expected, "got": got_value,
            "confidence": round(got.confidence, 3) if got else None,
            "ok": ok,
        })

    total = len([r for r in rows if r.get("got") is not None])
    acc = (hits / total) if total else 0.0
    print(f"\n=== 案由分类准确率：{hits}/{total} = {acc:.1%}（门槛 80%）===")
    for r in rows:
        flag = "PASS" if r.get("ok") else "FAIL"
        print(f"[{flag}] {r['file']}: 期望={r.get('expected')!r} 实得={r.get('got')!r}"
              f"{' err=' + r['error'] if r.get('error') else ''}")

    out = cases_dir / "eval_result.json"
    out.write_text(json.dumps(
        {"accuracy": acc, "hits": hits, "total": total, "rows": rows},
        ensure_ascii=False, indent=2,
    ), encoding="utf-8")
    print(f"\n明细已写入 {out}")
    return 0 if acc >= 0.8 else 1


def main() -> int:
    ap = argparse.ArgumentParser(description="判决书案由分类准确率实测")
    ap.add_argument("--cases", required=True, help="判决书目录（含 labels.json）")
    ap.add_argument("--endpoint", default=None, help="Von 服务地址（覆盖配置）")
    args = ap.parse_args()
    return evaluate(Path(args.cases), args.endpoint)


if __name__ == "__main__":
    raise SystemExit(main())
