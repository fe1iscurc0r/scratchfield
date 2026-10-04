"""B-06（续）· 在线检测与地图瓦片预取（卷132）。

`is_online()` 用 **TCP 连通性探测**而不是 HTTP 请求：探测要快、要能失败得干脆，
拉一个 HTTP 体只为判"通不通"既慢又费流量。目标列表可配，任一可达即视为在线。

`prefetch_region()` 按 XYZ 瓦片方案算出 bbox 覆盖的瓦片集合，逐个下到本地目录。
瓦片数按 zoom 指数增长，因此**强制上限** `max_tiles`，超限时拒绝而不是悄悄拉爆
（拿不到全部瓦片比把带宽打满好）。
"""
from __future__ import annotations

import math
import socket
import time
from pathlib import Path
from typing import Any, Iterable, Sequence

__all__ = [
    "OfflineManager", "lonlat_to_tile", "tile_bounds", "tiles_for_bbox",
    "DEFAULT_PROBE_TARGETS",
]

# 默认探测目标：(host, port)。选的都是"在国内可用、且连通性随机房变化"的端点
DEFAULT_PROBE_TARGETS: tuple[tuple[str, int], ...] = (
    ("223.5.5.5", 53),        # 阿里 DNS
    ("119.29.29.29", 53),     # DNSPod
    ("1.1.1.1", 53),          # Cloudflare
)

DEFAULT_TILE_TEMPLATE = "https://tile.openstreetmap.org/{z}/{x}/{y}.png"
DEFAULT_MAX_TILES = 512


# --------------------------------------------------------------------------- #
# 瓦片数学（XYZ / Web Mercator）
# --------------------------------------------------------------------------- #

def lonlat_to_tile(lng: float, lat: float, zoom: int) -> tuple[int, int]:
    """(经度, 纬度) → 瓦片 (x, y)。纬度先夹到墨卡托可表示范围。"""
    z = int(zoom)
    n = 2.0 ** z
    lat = max(-85.05112878, min(85.05112878, float(lat)))
    x = int((float(lng) + 180.0) / 360.0 * n)
    lat_rad = math.radians(lat)
    y = int((1.0 - math.asinh(math.tan(lat_rad)) / math.pi) / 2.0 * n)
    return max(0, min(int(n) - 1, x)), max(0, min(int(n) - 1, y))


def tile_bounds(x: int, y: int, zoom: int) -> tuple[float, float, float, float]:
    """瓦片 → (west, south, east, north)，单位度（Web Mercator 反算）。"""
    z = int(zoom)
    n = 2.0 ** z

    def _lon(px: float) -> float:
        return px / n * 360.0 - 180.0

    def _lat(py: float) -> float:
        return math.degrees(math.atan(math.sinh(math.pi * (1.0 - 2.0 * py / n))))

    return (_lon(x), _lat(y + 1), _lon(x + 1), _lat(y))


def tiles_for_bbox(bbox: tuple[float, float, float, float], zoom: int
                   ) -> list[tuple[int, int]]:
    """bbox → 覆盖它的瓦片 (x, y) 列表（左上→右下扫描）。"""
    w, s, e, n = (float(v) for v in bbox)
    x0, y1 = lonlat_to_tile(w, s, zoom)
    x1, y0 = lonlat_to_tile(e, n, zoom)
    xs = range(min(x0, x1), max(x0, x1) + 1)
    ys = range(min(y0, y1), max(y0, y1) + 1)
    return [(x, y) for y in ys for x in xs]


# --------------------------------------------------------------------------- #
# 管理器
# --------------------------------------------------------------------------- #

class OfflineManager:
    """在线检测 + 瓦片预取。`client` 可注入（httpx.Client 或替身）。"""

    def __init__(self, cache_dir: str | Path | None = None,
                 client: Any = None,
                 probe_targets: Sequence[tuple[str, int]] | None = None,
                 probe_timeout: float = 1.5,
                 tile_template: str = DEFAULT_TILE_TEMPLATE,
                 max_tiles: int = DEFAULT_MAX_TILES,
                 allow_network: bool = True,
                 online_override: bool | None = None) -> None:
        self.cache_dir = Path(cache_dir) if cache_dir is not None else Path("tile_cache")
        self._client = client
        self._owns_client = client is None
        self.probe_targets = tuple(probe_targets) if probe_targets is not None else DEFAULT_PROBE_TARGETS
        self.probe_timeout = probe_timeout
        self.tile_template = tile_template
        self.max_tiles = int(max_tiles)
        self.allow_network = bool(allow_network)
        self.online_override = online_override
        self._last_probe: dict[str, Any] | None = None

    # ---- 基础设施 ----

    def _get_client(self) -> Any:
        if self._client is None:
            import httpx
            self._client = httpx.Client(timeout=20.0, headers={"User-Agent": "sitaware/0.1"})
        return self._client

    def close(self) -> None:
        if self._client is not None and self._owns_client:
            try:
                self._client.close()
            except Exception:                               # noqa: BLE001
                pass
        self._client = None

    # ---- 在线检测 ----

    def is_online(self) -> bool:
        """任一探测目标 TCP 可达 → True。

        `online_override` 显式给定时直接返回（测试与强制离线演示用）。
        `allow_network=False` 时恒为 False。
        """
        if self.online_override is not None:
            return bool(self.online_override)
        if not self.allow_network:
            return False
        t0 = time.time()
        reachable: list[str] = []
        for host, port in self.probe_targets:
            try:
                with socket.create_connection((host, int(port)), timeout=self.probe_timeout):
                    reachable.append(f"{host}:{port}")
                    break
            except OSError:
                continue
        self._last_probe = {
            "online": bool(reachable),
            "reachable": reachable,
            "elapsed_ms": round((time.time() - t0) * 1000, 1),
            "checked": [f"{h}:{p}" for h, p in self.probe_targets],
        }
        return bool(reachable)

    def probe_status(self) -> dict[str, Any]:
        return {"ok": True, "override": self.online_override,
                "last_probe": self._last_probe}

    # ---- 瓦片预取 ----

    def tile_path(self, z: int, x: int, y: int) -> Path:
        return self.cache_dir / str(int(z)) / str(int(x)) / f"{int(y)}.png"

    def prefetch_region(self, bbox: tuple[float, float, float, float],
                        zoom: int = 10,
                        max_tiles: int | None = None) -> dict[str, Any]:
        """预取 bbox 在给定 zoom 下的瓦片。

        超过上限时**不下载**并返回 `ok=False, error="too_many_tiles"`，
        附上实际需要数，让调用方自己决定降 zoom 还是分批。
        """
        cap = int(max_tiles if max_tiles is not None else self.max_tiles)
        tiles = tiles_for_bbox(bbox, zoom)
        if len(tiles) > cap:
            return {"ok": False, "error": "too_many_tiles", "needed": len(tiles),
                    "cap": cap, "zoom": zoom, "hint": "降低 zoom 或提高 max_tiles"}

        downloaded = skipped = failed = 0
        errors: list[str] = []
        for (x, y) in tiles:
            dest = self.tile_path(zoom, x, y)
            if dest.exists() and dest.stat().st_size > 0:
                skipped += 1
                continue
            if not self.allow_network:
                failed += 1
                errors.append("network_disabled")
                break
            url = self.tile_template.format(z=zoom, x=x, y=y)
            try:
                resp = self._get_client().get(url)
                if getattr(resp, "status_code", 200) != 200:
                    failed += 1
                    errors.append(f"http_{resp.status_code}@{zoom}/{x}/{y}")
                    continue
                content = getattr(resp, "content", None)
                if content is None:
                    content = resp.read()
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(content)
                downloaded += 1
            except Exception as exc:                        # noqa: BLE001
                failed += 1
                errors.append(f"{type(exc).__name__}@{zoom}/{x}/{y}")

        return {
            "ok": failed == 0,
            "zoom": zoom,
            "tiles_total": len(tiles),
            "downloaded": downloaded,
            "skipped_cached": skipped,
            "failed": failed,
            "errors": errors[:10],
            "cache_dir": str(self.cache_dir),
        }

    def cache_status(self) -> dict[str, Any]:
        """已缓存瓦片数与占用体积。"""
        count = 0
        size = 0
        if self.cache_dir.exists():
            for p in self.cache_dir.rglob("*.png"):
                count += 1
                try:
                    size += p.stat().st_size
                except OSError:
                    pass
        return {"tiles_cached": count, "tiles_bytes": size, "cache_dir": str(self.cache_dir)}
