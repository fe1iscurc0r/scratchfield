#!/usr/bin/env python3
"""
扫货防幻觉守卫 (Anti-Hallucination Guard)
========================================
给扫货/授粉/日报流程加一道程序化核验闸门，堵三类幻觉：
  1. 数字幻觉 —— 星数/日期从 badge/搜索页误读（8-21 教训：日报星数灌水）
  2. 身份幻觉 —— 把自家上游/已融合项目当新对象推荐（8-22 教训：nuwa-skill 险情）
  3. 来源幻觉 —— 报告里出现不存在的仓库 / archived 死项目 / 许可误标

用法:
  # 1) 核验候选清单（逗号分隔，gh api 权威数据）
  python3 anti_hallucination_guard.py --verify "owner/repo1,owner/repo2"

  # 2) 核验一份报告文件（自动提取 owner/repo + 星数声明，逐项比对）
  python3 anti_hallucination_guard.py --check-report <report.md>

  # 3) 检测单个候选是否本地上游 / 已融合 / 已授粉过
  python3 anti_hallucination_guard.py --detect-upstream "owner/repo"

  # 4) 组合：先检测上游再核验
  python3 anti_hallucination_guard.py --verify "a/b,c/d" --detect-upstream

输出: 每项 ✅PASS / ❌FAIL / ⚠️WARN + 证据。FAIL 项修正前禁止发布报告。
退出码: 0=全过  1=有 FAIL  2=有 WARN 无 FAIL  3=工具/网络错误
"""
import argparse
import json
import re
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

# ---------------------------------------------------------------- 本地知识库（上游检测用）
def local_corpus_paths():
    """返回要 grep 的本地路径集合（skills / 授粉报告 / FUSION-LOG / 已融合代码）。"""
    paths = []
    for p in [
        Path.home() / ".hermes" / "skills",
        Path.home() / "scratchpad" / "docs",
        Path.home() / "github_haul",
    ]:
        if p.exists():
            paths.append(p)
    return paths

# ---------------------------------------------------------------- gh api 核验
def gh_api(repo):
    """调 gh api 拉权威元数据。失败返回带 error 字段的 dict。"""
    r = subprocess.run(
        ["gh", "api", f"repos/{repo}", "--jq",
         '{full_name, stars: .stargazers_count, lic: (.license.spdx_id // "NONE"), '
         'archived, fork, pushed: (.pushed_at // "")[:10], desc: (.description // "")[:80]}'],
        capture_output=True, text=True, timeout=30)
    if r.returncode != 0:
        err = r.stderr.strip().splitlines()
        msg = err[0][:120] if err else "gh api failed"
        return {"full_name": repo, "error": msg}
    try:
        return json.loads(r.stdout)
    except Exception:
        return {"full_name": repo, "error": "bad json from gh api"}


def verify_repos(repos):
    """批量核验。返回 [{repo, meta|error}]。"""
    results = []
    with ThreadPoolExecutor(max_workers=8) as ex:
        futures = {ex.submit(gh_api, r): r for r in repos}
        for f in futures:
            results.append(f.result())
    return results


def parse_star_claim(text):
    """从一行文本提取星数声明（如 31k★ / ⭐12345 / 12345 stars），转成 int，找不到返回 None。"""
    m = re.search(r'(?:⭐|★|\b)(\d+(?:\.\d+)?)\s*[kK]?\s*(?:★|stars?\b|⭐)?', text)
    if not m:
        return None
    n = float(m.group(1))
    if re.search(r'\d+\.?\d*\s*[kK]\s*★', text) or re.search(r'[kK]\s*★', text):
        n *= 1000
    return int(n)


REPO_RE = re.compile(r'(?<![\w@.-])([A-Za-z0-9][A-Za-z0-9_.-]{0,38}/[A-Za-z0-9][A-Za-z0-9_.-]{0,99})(?![\w@.-])')


def extract_repos_from_report(path):
    """从报告 md 提取疑似 owner/repo。返回 (repos, lines_with_claims)。"""
    text = Path(path).read_text(encoding="utf-8", errors="ignore")
    lines = text.splitlines()
    repos = {}
    for ln in lines:
        for m in REPO_RE.finditer(ln):
            cand = m.group(1)
            # 过滤 URL 路径 / 日期 / 文件路径误匹配
            if cand.endswith(('.md', '.py', '.json', '.yaml', '.yml', '.png', '.jpg', '.tar', '.gz')):
                continue
            if cand.count('/') != 1:
                continue
            repos.setdefault(cand, []).append(ln.strip()[:200])
    return repos


def star_mismatch(claimed, actual):
    """星数声明 vs 实际：偏差 >25% 或数量级不同算 FAIL，>10% 算 WARN。"""
    if actual <= 0:
        return None
    ratio = claimed / actual
    if ratio > 1.25 or ratio < 0.75:
        return "FAIL"
    if ratio > 1.10 or ratio < 0.90:
        return "WARN"
    return None


# ---------------------------------------------------------------- 上游/已融合检测
def detect_upstream(repos):
    """grep 本地语料，找候选是否已被引用（skills/报告/日志/代码）。"""
    hits = {}
    paths = local_corpus_paths()
    for repo in repos:
        owner, name = repo.split("/", 1)
        found = []
        for base in paths:
            r = subprocess.run(
                ["grep", "-rIl", "-e", repo, "-e", name,
                 str(base)],
                capture_output=True, text=True, timeout=60)
            if r.returncode == 0:
                for fp in r.stdout.strip().splitlines()[:5]:
                    found.append(fp.replace(str(Path.home()), "~"))
        hits[repo] = found
    return hits


# ---------------------------------------------------------------- 输出
def fmt_repo_status(meta):
    if "error" in meta:
        return f"❌FAIL  {meta['full_name']:<45} 不存在/查询失败: {meta['error']}"
    flags = []
    if meta.get("archived"):
        flags.append("ARCHIVED")
    if meta.get("fork"):
        flags.append("FORK")
    lic = meta.get("lic", "NONE")
    if lic in ("NONE", "NOASSERTION"):
        flags.append("无LICENSE")
    tag = "✅PASS " if not flags else "⚠️WARN "
    extra = f"  [{','.join(flags)}]" if flags else ""
    return (f"{tag} {meta['full_name']:<45} {meta.get('stars', '?'):>7}★ "
            f"{lic:<14} pushed:{meta.get('pushed','?')}{extra}  {meta.get('desc','')}")


def main():
    ap = argparse.ArgumentParser(description="扫货防幻觉守卫")
    ap.add_argument("--verify", help="逗号分隔 repo 列表")
    ap.add_argument("--check-report", help="核验报告 md 文件")
    ap.add_argument("--detect-upstream", action="store_true", help="检测本地上游/已引用")
    ap.add_argument("--json", action="store_true", help="JSON 输出")
    args = ap.parse_args()

    repos = []
    found = {}
    if args.verify:
        repos = [r.strip() for r in args.verify.split(",") if r.strip()]
    if args.check_report:
        found = extract_repos_from_report(args.check_report)
        repos = list(found.keys())
        if not repos:
            print("⚠️ 报告里没提取到 owner/repo 模式，跳过核验")
            sys.exit(2)

    if not repos:
        ap.print_help()
        sys.exit(3)

    metas = verify_repos(repos)
    problems = 0
    warns = 0
    out_lines = []

    if args.detect_upstream:
        hits = detect_upstream(repos)
        for repo in repos:
            if hits[repo]:
                warns += 1
                out_lines.append(f"⚠️WARN  {repo:<45} 本地已引用(可能上游/已融合):")
                for fp in hits[repo][:3]:
                    out_lines.append(f"        └ {fp}")

    for meta in metas:
        line = fmt_repo_status(meta)
        out_lines.append(line)
        if line.startswith("❌FAIL"):
            problems += 1
        elif line.startswith("⚠️WARN"):
            warns += 1

    # 星数声明比对（仅 --check-report 时）
    if args.check_report:
        for repo, lines in found.items():
            meta = next((m for m in metas if m["full_name"] == repo), None)
            if not meta or "error" in meta:
                continue
            for ln in lines:
                claimed = parse_star_claim(ln)
                if claimed is None:
                    continue
                verdict = star_mismatch(claimed, meta.get("stars", 0))
                if verdict == "FAIL":
                    problems += 1
                    out_lines.append(f"❌FAIL  星数声明 {claimed} vs 实际 {meta['stars']} (repo={repo})")
                    out_lines.append(f"        └ 原文: {ln}")
                elif verdict == "WARN":
                    warns += 1
                    out_lines.append(f"⚠️WARN  星数声明 {claimed} vs 实际 {meta['stars']} 偏差>10% (repo={repo})")

    print("\n".join(out_lines))
    print(f"\n===== 守卫结论: {len(repos)} 项 | FAIL={problems} WARN={warns} =====")
    if problems > 0:
        sys.exit(1)
    if warns > 0:
        sys.exit(2)
    sys.exit(0)


if __name__ == "__main__":
    main()
