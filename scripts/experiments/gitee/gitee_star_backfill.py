#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Gitee 授权SPEC候选仓星数回填 — 用单仓 repos API 避开搜索限流。

用法: python3 gitee_star_backfill.py
错峰建议: 凌晨 02-04 点跑（cron）。
候选仓清单来自 docs/扫货-Gitee-API-2026-09-02.md 网页侧发现。
单仓 API repos/{owner}/{repo} 返回 stargazers_count，不触发 search 限流。
可选 GITEE_TOKEN 环境变量提升配额。
历史: 2026-09-15 轮 cd9d8b339 (15/16成功); 本文件自该提交恢复, 落盘名改为运行日期。
"""
import datetime
import json
import os
import time
import urllib.request

# owner/repo 清单（网页侧候选）
REPOS = [
    "syzh120/ZYNQ7010-7020_AD9363",
    "ledgejin/sdr-neutral-hydrogen",
    "ledgejin/STM32_SDR",
    "yzbluesky/Navigation-Learning",
    "yzq114/NGroundStation",
    "skydroid/OpenTower",
    "gaasdev/GAAS",
    "Avem/Avem",
    "ai27810617/DuiJiangJiXiePinRuanJian",
    "tan-wenyuan1/lora-gateway",
    "Barry-sh/KnowledgeGraphData",
    "openkg/deepke",
    "openkg/openspg",
    "openkg/OpenEA",
    "qiantongtech/qKnow",
    "pchen_Lyndon/cnschema",
]

TOKEN = os.environ.get("GITEE_TOKEN", "")


def api_get(owner_repo):
    url = "https://gitee.com/api/v5/repos/%s" % owner_repo
    if TOKEN:
        url += "?access_token=" + TOKEN
    req = urllib.request.Request(url, headers={"User-Agent": "pollination/1.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode())


def main():
    out = {}
    delay = 3  # 初始间隔 3s
    for i, repo in enumerate(REPOS):
        for attempt in range(4):
            try:
                d = api_get(repo)
                out[repo] = {
                    "stars": d.get("stargazers_count"),
                    "language": d.get("language"),
                    "desc": (d.get("description") or "")[:80],
                }
                print("[OK] %-40s ★%s  %s" % (repo, out[repo]["stars"], out[repo]["desc"]))
                delay = 3  # 成功复位
                break
            except Exception as e:
                print("[retry] %-40s %s (attempt %d/4, backoff %ds)" % (repo, e, attempt + 1, delay))
                time.sleep(delay)
                delay = min(delay * 2, 120)  # 指数退避 3→6→12...
        time.sleep(delay)

    datestr = datetime.date.today().strftime("%Y-%m-%d")
    path = "docs/gitee-stars-backfill-%s.json" % datestr
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print("\n== 回填完成: %d/%d 成功 ==" % (sum(1 for v in out.values() if v.get("stars") is not None), len(REPOS)))
    print("已落盘 %s" % path)


if __name__ == "__main__":
    main()
