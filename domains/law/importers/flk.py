"""法规导入器骨架（法学领域包）。

数据源：国家法律法规数据库 https://flk.npc.gov.cn

本卷（卷162）**只交付结构**：
- 法规清单从 `domains/law/pack.yaml` 声明式读取
- `FlkItem` 数据模型与 `parse_flk_payload()` 解析逻辑
- 入库路径约定（`papers.id_fields = [flk_id, case_no]`）

**反爬策略不在本卷范围**（单列下一卷，卷163 只做请求间隔 ≥3s / 标准 UA /
失败重试 ≤2 次的轻量版）。本文件不含任何真实网络请求实现，
`fetch_regulation()` 刻意留空并抛 NotImplementedError，避免被误认为已可用。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

#: 本包目录，供读取 pack.yaml 声明的法规清单。
PACK_DIR = Path(__file__).resolve().parent.parent

#: 默认法规清单（若 pack.yaml 未声明 flk.regulations 时使用）。
DEFAULT_REGULATIONS = [
    "中华人民共和国民法典",
    "中华人民共和国刑法",
    "中华人民共和国刑事诉讼法",
    "中华人民共和国民事诉讼法",
    "中华人民共和国行政诉讼法",
    "最高人民法院关于适用《中华人民共和国民法典》总则编若干问题的解释",
]

#: 请求间隔下限（秒）。卷163 实装时必须遵守。
MIN_REQUEST_INTERVAL_SECONDS = 3.0

#: 标准 User-Agent。
USER_AGENT = "lumo-flk-importer/0.1 (+https://flk.npc.gov.cn; 低频礼貌抓取)"

#: 失败重试上限。
MAX_RETRIES = 2


@dataclass
class FlkItem:
    """一条法规记录，映射到 papers 表的一行。"""

    flk_id: str
    """法规编号（flk.npc.gov.cn 编号体系），papers 主键之一。"""

    title: str
    """法规标题。"""

    issuing_body: str = ""
    """发布机关。"""

    validity: str = ""
    """时效性（有效/已废止/尚未生效等）。"""

    version_date: str = ""
    """版本日期。"""

    content: str = ""
    """正文全文。入库时写入 papers.abstract（截断），完整文本另存 md_path。"""

    source: str = "flk"
    """来源标识，写入 papers.source。"""

    license_note: str = "国家法律法规数据库，官方公开"
    """版权说明，写入 papers.license_note。"""

    extra: dict[str, Any] = field(default_factory=dict)

    def to_paper_dict(self) -> dict[str, Any]:
        """转换为 papers 表可入库的字典。"""
        return {
            "flk_id": self.flk_id,
            "title": self.title,
            "tags": f"发布机关:{self.issuing_body}|时效性:{self.validity}",
            "abstract": self.content[:2000] if self.content else None,
            "source": self.source,
            "license_note": self.license_note,
            **self.extra,
        }


def load_regulation_list(pack_yaml_path: Path | None = None) -> list[str]:
    """从 pack.yaml 读取待同步法规清单。缺失时返回 DEFAULT_REGULATIONS。

    只读 `flk.regulations`（字符串列表）；解析失败不抛异常，回退默认清单。
    """
    import yaml

    manifest = pack_yaml_path or (PACK_DIR / "pack.yaml")
    try:
        raw = yaml.safe_load(manifest.read_text(encoding="utf-8")) or {}
        regs = (raw.get("flk") or {}).get("regulations")
        if isinstance(regs, list) and regs and all(isinstance(r, str) for r in regs):
            return [r.strip() for r in regs if r.strip()]
    except Exception as exc:  # 骨架阶段：任何异常都回退默认值
        logger.warning("读取 flk.regulations 失败，回退默认清单: %r", exc)
    return list(DEFAULT_REGULATIONS)


def parse_flk_payload(payload: dict[str, Any]) -> FlkItem | None:
    """把 flk 接口返回的单条记录解析为 FlkItem。

    骨架实现：字段映射按 flk 开放接口的常见结构假设，**待卷163 用真实
    响应校准**。缺关键字段（flk_id / title）返回 None。
    """
    if not isinstance(payload, dict):
        return None

    flk_id = payload.get("id") or payload.get("flk_id") or payload.get("code")
    title = payload.get("title") or payload.get("name")
    if not flk_id or not title:
        return None

    return FlkItem(
        flk_id=str(flk_id).strip(),
        title=str(title).strip(),
        issuing_body=str(payload.get("office") or payload.get("issuing_body") or "").strip(),
        validity=str(payload.get("status") or payload.get("validity") or "").strip(),
        version_date=str(
            payload.get("publish") or payload.get("version_date") or ""
        ).strip(),
        content=str(payload.get("content") or payload.get("body") or ""),
    )


#: 串行抓取锁（**严禁并发**，工单硬约束）。惰性创建，避免 import 期绑定事件循环。
_REQUEST_LOCK: Any = None

#: 上次请求时间戳（单调时钟），用于强制请求间隔。
_last_request_ts: float = 0.0


def _proc_locks() -> Any:
    """惰性创建模块级 asyncio.Lock（避免 import 期绑定事件循环）。"""
    global _REQUEST_LOCK
    if _REQUEST_LOCK is None:
        import asyncio

        _REQUEST_LOCK = asyncio.Lock()
    return _REQUEST_LOCK


async def _respect_interval() -> None:
    """确保距上次请求 ≥ ``MIN_REQUEST_INTERVAL_SECONDS`` 秒（否则等待）。"""
    global _last_request_ts
    import asyncio
    import time

    if _last_request_ts:
        elapsed = time.monotonic() - _last_request_ts
        wait = MIN_REQUEST_INTERVAL_SECONDS - elapsed
        if wait > 0:
            await asyncio.sleep(wait)


def _mark_request() -> None:
    """记录本次请求时间戳。"""
    global _last_request_ts
    import time

    _last_request_ts = time.monotonic()


async def fetch_regulation(regulation_name: str) -> list[FlkItem]:
    """抓取单个法规（低频、串行、可重试）。

    实现要点（工单卷163 硬约束）：
    - 请求间隔 ≥ ``MIN_REQUEST_INTERVAL_SECONDS``（3s），模块级 ``_last_request_ts``
      记录上次请求时间，**串行等待**（模块级 ``asyncio.Lock`` 保证不并发）；
    - 标准 User-Agent；
    - 失败重试 ≤ ``MAX_RETRIES``（2 次），指数退避；
    - 使用官方搜索接口 ``https://flk.npc.gov.cn/api/search``（公开、允许低频访问）。

    返回该法规名下的 ``FlkItem`` 列表（通常 1 条，可能含多个版本）。
    网络异常时返回空列表并记 warning（不抛，避免整批同步失败）。
    """
    import asyncio

    try:
        import httpx
    except ImportError as exc:  # pragma: no cover - 环境相关
        raise RuntimeError("flk 抓取需要 httpx（核心依赖，应已安装）") from exc

    url = "https://flk.npc.gov.cn/api/search"
    params = {"type": "flfg", "searchType": "title;accurate", "sortTr": "f_bbrq_s;desc",
              "gbrqStart": "", "gbrqEnd": "", "sxrqStart": "", "sxrqEnd": "",
              "sort": "true", "page": "1", "size": "10", "_": "0",
              "keyword": regulation_name}

    last_err = ""
    async with _proc_locks():
        for attempt in range(MAX_RETRIES + 1):
            await _respect_interval()
            try:
                async with httpx.AsyncClient(timeout=20.0, follow_redirects=True) as client:
                    resp = await client.get(url, params=params, headers={"User-Agent": USER_AGENT})
                _mark_request()
                if resp.status_code != 200:
                    last_err = f"HTTP {resp.status_code}"
                    raise RuntimeError(last_err)
                payload = resp.json()
                return _parse_search_response(payload)
            except Exception as exc:  # noqa: BLE001 - 网络异常统一处理
                last_err = str(exc)
                logger.warning(
                    "[flk] 抓取 %r 第 %d 次失败: %s", regulation_name, attempt + 1, exc
                )
                if attempt < MAX_RETRIES:
                    await asyncio.sleep(MIN_REQUEST_INTERVAL_SECONDS)
    logger.warning("[flk] 抓取 %r 最终失败: %s", regulation_name, last_err)
    return []


def _parse_search_response(payload: dict[str, Any]) -> list[FlkItem]:
    """解析 flk 搜索接口响应 → FlkItem 列表。

    官方响应结构（``result.data`` 为记录数组）：``{code, result: {data: [...]}}``
    字段名以真实响应为准：``id`` / ``title`` / ``office`` / ``status`` /
    ``publish``。字段缺失时降级处理（不抛异常）。
    """
    items: list[FlkItem] = []
    if not isinstance(payload, dict):
        return items
    result = payload.get("result") or payload.get("data") or {}
    records = result.get("data") if isinstance(result, dict) else None
    if not isinstance(records, list):
        return items
    for rec in records:
        item = parse_flk_payload(rec)
        if item is not None:
            items.append(item)
    return items


async def sync_regulations(
    names: list[str] | None = None,
) -> dict[str, Any]:
    """手动触发式同步入口（供 `POST /api/domains/law/import-flk` 调用）。

    **串行**逐个抓取（``for`` + ``await``，无 ``gather``），相邻请求间隔 ≥3s。
    返回汇总：每条法规的抓取结果与 ``items``（供路由层入库）。
    """
    targets = names if names is not None else load_regulation_list()
    results: list[dict[str, Any]] = []
    all_items: list[FlkItem] = []
    for name in targets:
        items = await fetch_regulation(name)
        all_items.extend(items)
        results.append({
            "name": name,
            "found": len(items),
            "titles": [it.title for it in items],
        })
    return {
        "status": "ok" if all_items else "empty",
        "message": (
            f"同步完成：{len(targets)} 条法规，抓取 {len(all_items)} 条记录"
        ),
        "min_request_interval_seconds": MIN_REQUEST_INTERVAL_SECONDS,
        "targets": targets,
        "results": results,
        "items": all_items,
    }
