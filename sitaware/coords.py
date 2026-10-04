"""坐标系转换 + Maidenhead 网格（卷132 B-01 / B-08）。

**为什么不装 `gcoord`**：工单 `requirements.txt` 写 `gcoord>=0.4`，但 `gcoord`
是 **JavaScript** 库（npm，6.7k⭐ —— 工单描述里的星数与 npm 仓一致），PyPI 上
不存在同名 Python 包（实测 404）。故在此自研实现，算法为公开标准：

- WGS84 ↔ GCJ-02：国测局偏移算法（椭球 Krasovsky 1940，a=6378245.0）
- GCJ-02 ↔ BD-09：百度球面偏移（x_pi = π·3000/180）
- Maidenhead：字段(A-R, 20°经×10°纬) / 方格(0-9, 2°×1°) /
  子字段(a-x, 5'×2.5') / 扩展格(0-9, 30"×15') / 再扩展(3"×1.5")

**精度事实（实测，纬 23° 广州）**：

| 位数 | 格子尺寸 | 半格误差 |
|---|---|---|
| 4  | 204.9 km × 110.6 km | ~117 km |
| 6  | 8.5 km × 4.6 km | ~4.8 km |
| 8  | 854 m × 461 m | ~490 m |
| 10 | 85 m × 46 m | ~48 m |

> 工单 B-08 验收写「Maidenhead 6 位精度误差 < 100m」——**几何上不可能**：
> 6 位格子本身就有 8.5km×4.6km，信息量不足以定位到 100m。
> 本实现把判据改为「误差 ≤ 半格对角线」且「精度随位数单调收敛」，
> 并单列 10 位用例证明 <100m 需要 10 位。见偏离说明第 8 条。

所有函数统一 **(经度, 纬度)** 参数顺序，与 GeoJSON 一致。
"""
from __future__ import annotations

import math

__all__ = [
    "out_of_china",
    "wgs84_to_gcj02", "gcj02_to_wgs84",
    "gcj02_to_bd09", "bd09_to_gcj02",
    "wgs84_to_bd09", "bd09_to_wgs84",
    "to_wgs84", "from_wgs84",
    "maidenhead_to_lonlat", "lonlat_to_maidenhead",
    "maidenhead_cell_size_deg", "maidenhead_cell_size_m",
    "haversine_km", "VALID_PRECISIONS",
    "circle_polygon", "point_in_bbox", "bbox_intersects", "segment_intersects_bbox",
]

# --------------------------------------------------------------------------- #
# 常量
# --------------------------------------------------------------------------- #

_A = 6378245.0                     # Krasovsky 1940 长半轴
_EE = 0.00669342162296594323       # 第一偏心率平方
_X_PI = math.pi * 3000.0 / 180.0   # 百度球面偏移常数
_M_PER_DEG_LAT = 110574.0          # 等距圆柱近似（仅用于粗算，见各函数说明）
_M_PER_DEG_LON_EQ = 111320.0

VALID_PRECISIONS = (2, 4, 6, 8, 10)


def out_of_china(lng: float, lat: float) -> bool:
    """粗略判断是否在中国境外（境外不做 GCJ-02 偏移）。"""
    if not (73.66 < lng < 135.05):
        return True
    if not (3.86 < lat < 53.55):
        return True
    return False


# --------------------------------------------------------------------------- #
# WGS84 ↔ GCJ-02
# --------------------------------------------------------------------------- #

def _transform_lat(x: float, y: float) -> float:
    ret = (-100.0 + 2.0 * x + 3.0 * y + 0.2 * y * y + 0.1 * x * y
           + 0.2 * math.sqrt(abs(x)))
    ret += (20.0 * math.sin(6.0 * x * math.pi) + 20.0 * math.sin(2.0 * x * math.pi)) * 2.0 / 3.0
    ret += (20.0 * math.sin(y * math.pi) + 40.0 * math.sin(y / 3.0 * math.pi)) * 2.0 / 3.0
    ret += (160.0 * math.sin(y / 12.0 * math.pi) + 320.0 * math.sin(y * math.pi / 30.0)) * 2.0 / 3.0
    return ret


def _transform_lng(x: float, y: float) -> float:
    ret = 300.0 + x + 2.0 * y + 0.1 * x * x + 0.1 * x * y + 0.1 * math.sqrt(abs(x))
    ret += (20.0 * math.sin(6.0 * x * math.pi) + 20.0 * math.sin(2.0 * x * math.pi)) * 2.0 / 3.0
    ret += (20.0 * math.sin(x * math.pi) + 40.0 * math.sin(x / 3.0 * math.pi)) * 2.0 / 3.0
    ret += (150.0 * math.sin(x / 12.0 * math.pi) + 300.0 * math.sin(x / 30.0 * math.pi)) * 2.0 / 3.0
    return ret


def _delta(lng: float, lat: float) -> tuple[float, float]:
    """WGS84 → GCJ-02 的经纬偏移量（度）。"""
    dlat = _transform_lat(lng - 105.0, lat - 35.0)
    dlng = _transform_lng(lng - 105.0, lat - 35.0)
    radlat = lat / 180.0 * math.pi
    magic = math.sin(radlat)
    magic = 1 - _EE * magic * magic
    sqrtmagic = math.sqrt(magic)
    dlat = (dlat * 180.0) / ((_A * (1 - _EE)) / (magic * sqrtmagic) * math.pi)
    dlng = (dlng * 180.0) / (_A / sqrtmagic * math.cos(radlat) * math.pi)
    return dlng, dlat


def wgs84_to_gcj02(lng: float, lat: float) -> tuple[float, float]:
    """WGS84 → GCJ-02（火星坐标）。境外原样返回。"""
    if out_of_china(lng, lat):
        return lng, lat
    dlng, dlat = _delta(lng, lat)
    return lng + dlng, lat + dlat


def gcj02_to_wgs84(lng: float, lat: float) -> tuple[float, float]:
    """GCJ-02 → WGS84。

    正向公式不可解析求逆，用「偏移量迭代」：以当前估计点重新算偏移并扣除。
    3 次迭代在国境内收敛到 <0.1mm（偏移量本身是缓变量，迭代收敛极快）。
    """
    if out_of_china(lng, lat):
        return lng, lat
    est_lng, est_lat = lng, lat
    for _ in range(3):
        dlng, dlat = _delta(est_lng, est_lat)
        est_lng, est_lat = lng - dlng, lat - dlat
    return est_lng, est_lat


# --------------------------------------------------------------------------- #
# GCJ-02 ↔ BD-09
# --------------------------------------------------------------------------- #

def gcj02_to_bd09(lng: float, lat: float) -> tuple[float, float]:
    z = math.sqrt(lng * lng + lat * lat) + 0.00002 * math.sin(lat * _X_PI)
    theta = math.atan2(lat, lng) + 0.000003 * math.cos(lng * _X_PI)
    return z * math.cos(theta) + 0.0065, z * math.sin(theta) + 0.006


def bd09_to_gcj02(lng: float, lat: float) -> tuple[float, float]:
    x, y = lng - 0.0065, lat - 0.006
    z = math.sqrt(x * x + y * y) - 0.00002 * math.sin(y * _X_PI)
    theta = math.atan2(y, x) - 0.000003 * math.cos(x * _X_PI)
    return z * math.cos(theta), z * math.sin(theta)


def wgs84_to_bd09(lng: float, lat: float) -> tuple[float, float]:
    return gcj02_to_bd09(*wgs84_to_gcj02(lng, lat))


def bd09_to_wgs84(lng: float, lat: float) -> tuple[float, float]:
    return gcj02_to_wgs84(*bd09_to_gcj02(lng, lat))


# --------------------------------------------------------------------------- #
# 统一入口
# --------------------------------------------------------------------------- #

def to_wgs84(lng: float, lat: float, source: str = "wgs84") -> tuple[float, float]:
    """任意声明坐标系 → WGS84。

    `source` 取 `wgs84` / `gcj02` / `bd09`（大小写不敏感）。
    未知取值**抛 ValueError**，不静默放行 —— 猜坐标系等于给地图埋错位。
    """
    key = str(source or "wgs84").strip().lower()
    if key in ("wgs84", "epsg:4326", "4326"):
        return lng, lat
    if key in ("gcj02", "gcj-02", "mars", "amap", "tencent"):
        return gcj02_to_wgs84(lng, lat)
    if key in ("bd09", "bd09ll", "baidu", "bmap"):
        return bd09_to_wgs84(lng, lat)
    raise ValueError(f"未知坐标系 source={source!r}，支持 wgs84 / gcj02 / bd09")


def from_wgs84(lng: float, lat: float, target: str = "wgs84") -> tuple[float, float]:
    """WGS84 → 指定坐标系。"""
    key = str(target or "wgs84").strip().lower()
    if key in ("wgs84", "epsg:4326", "4326"):
        return lng, lat
    if key in ("gcj02", "gcj-02", "mars", "amap", "tencent"):
        return wgs84_to_gcj02(lng, lat)
    if key in ("bd09", "bd09ll", "baidu", "bmap"):
        return wgs84_to_bd09(lng, lat)
    raise ValueError(f"未知坐标系 target={target!r}，支持 wgs84 / gcj02 / bd09")


# --------------------------------------------------------------------------- #
# Maidenhead
# --------------------------------------------------------------------------- #

# 每一级「当前精度下已用掉的格宽」：(经度跨度, 纬度跨度) 单位：度
_MH_STEPS: tuple[tuple[float, float], ...] = (
    (20.0, 10.0),            # 字段        A-R
    (2.0, 1.0),              # 方格        0-9
    (5.0 / 60.0, 2.5 / 60.0),        # 子字段 a-x
    (30.0 / 3600.0, 15.0 / 3600.0),  # 扩展格 0-9
    (3.0 / 3600.0, 1.5 / 3600.0),    # 再扩展 a-x
)


def maidenhead_cell_size_deg(grid: str) -> tuple[float, float]:
    """给定网格的格子尺寸（经度跨度, 纬度跨度），单位度。

    例：`OL62ir`（6 位）→ (5/60, 2.5/60) 度。
    """
    n = len(str(grid).strip())
    if n not in VALID_PRECISIONS:
        raise ValueError(f"Maidenhead 位数必须是 {VALID_PRECISIONS} 之一，收到 {n}")
    return _MH_STEPS[n // 2 - 1]


def maidenhead_cell_size_m(grid: str, lat: float | None = None) -> tuple[float, float]:
    """格子尺寸（米）。`lat` 给定时经度按 cos(lat) 收缩。"""
    lon_deg, lat_deg = maidenhead_cell_size_deg(grid)
    lat_ref = lat
    if lat_ref is None:
        # 取格子自身中心纬度
        try:
            _, lat_ref = maidenhead_to_lonlat(grid)
        except ValueError:
            lat_ref = 0.0
    return (lon_deg * _M_PER_DEG_LON_EQ * math.cos(math.radians(lat_ref)),
            lat_deg * _M_PER_DEG_LAT)


def maidenhead_to_lonlat(grid: str) -> tuple[float, float]:
    """Maidenhead → 格子中心点 (经度, 纬度)。非法网格抛 ValueError。

    各级累加后用「当前精度格宽的一半」取中心。
    """
    g = str(grid).strip().upper().replace(" ", "")
    n = len(g)
    if n not in VALID_PRECISIONS:
        raise ValueError(f"Maidenhead 位数必须是 {VALID_PRECISIONS} 之一，收到 {n}: {grid!r}")

    # 字符类型校验：偶位字母、奇位数字（第 3 组 letters 也是偶位）
    for i, ch in enumerate(g):
        group = i // 2                       # 0=字段 1=方格 2=子字段 3=扩展 4=再扩展
        want_digit = group % 2 == 1          # 组 1、3 是数字
        if want_digit:
            if not ch.isdigit():
                raise ValueError(f"Maidenhead 第 {i + 1} 位应为数字，收到 {ch!r}: {grid!r}")
        else:
            if not ch.isalpha():
                raise ValueError(f"Maidenhead 第 {i + 1} 位应为字母，收到 {ch!r}: {grid!r}")

    lng = -180.0
    lat = -90.0
    for idx in range(0, n, 2):
        level = idx // 2
        lon_span, lat_span = _MH_STEPS[level]
        a, b = g[idx], g[idx + 1]
        if a.isdigit():
            ia, ib = int(a), int(b)
            maxa = maxb = 9
        else:
            ia, ib = ord(a) - ord("A"), ord(b) - ord("A")
            # 字段级 18 格（A-R）；子字段/再扩展 24 格（A-X）
            maxa = maxb = 17 if level == 0 else 23
        if ia > maxa or ib > maxb:
            raise ValueError(f"Maidenhead 字符越界 {a}{b}（第 {level + 1} 组）: {grid!r}")
        lng += ia * lon_span
        lat += ib * lat_span

    lon_span, lat_span = _MH_STEPS[n // 2 - 1]
    return lng + lon_span / 2.0, lat + lat_span / 2.0


def lonlat_to_maidenhead(lng: float, lat: float, precision: int = 6) -> str:
    """(经度, 纬度) → Maidenhead 网格。`precision` 取 2/4/6/8/10。"""
    if precision not in VALID_PRECISIONS:
        raise ValueError(f"precision 必须是 {VALID_PRECISIONS} 之一，收到 {precision}")

    # 夹到合法范围；极点/边界浮点残留会算出非法字符，故留极小内缩
    x = min(max(lng + 180.0, 0.0), 360.0 - 1e-9)
    y = min(max(lat + 90.0, 0.0), 180.0 - 1e-9)

    out: list[str] = []
    for level, (lon_span, lat_span) in enumerate(_MH_STEPS):
        if level * 2 >= precision:
            break
        ia = int(x / lon_span)
        ib = int(y / lat_span)
        x -= ia * lon_span
        y -= ib * lat_span
        if level == 0:
            ia, ib = min(ia, 17), min(ib, 17)
            out += [chr(ord("A") + ia), chr(ord("A") + ib)]
        elif level % 2 == 1:
            out += [str(min(ia, 9)), str(min(ib, 9))]
        else:
            ia, ib = min(ia, 23), min(ib, 23)
            out += [chr(ord("a") + ia), chr(ord("a") + ib)]
    return "".join(out)


# --------------------------------------------------------------------------- #
# 距离
# --------------------------------------------------------------------------- #

def haversine_km(lng1: float, lat1: float, lng2: float, lat2: float) -> float:
    """两点大圆距离（km）。"""
    r = 6371.0088
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(min(1.0, math.sqrt(a)))


def circle_polygon(lng: float, lat: float, radius_km: float,
                   points: int = 32) -> list[list[float]]:
    """圆 → GeoJSON 多边形环（闭合）。用于 B-04 影响范围。

    以给定点为圆心、`radius_km` 为半径，按等距圆柱近似铺点：
    纬度按 1°≈110.574km 折算，经度按 cos(lat) 收缩。半径量级（公里级）下
    误差 <0.1%，足够画影响圈用。返回环**首尾相同**（GeoJSON 要求）。
    """
    pts = max(8, int(points))
    cosf = max(1e-6, math.cos(math.radians(lat)))
    ring: list[list[float]] = []
    for i in range(pts):
        theta = 2.0 * math.pi * i / pts
        dlat = (radius_km / 110.574) * math.cos(theta)
        dlon = (radius_km / (111.320 * cosf)) * math.sin(theta)
        ring.append([round(lng + dlon, 6), round(lat + dlat, 6)])
    ring.append(list(ring[0]))
    return ring


def point_in_bbox(lng: float, lat: float, bbox: tuple[float, float, float, float]) -> bool:
    """点是否在 (west, south, east, north) 框内。"""
    w, s, e, n = bbox
    return w <= lng <= e and s <= lat <= n


def bbox_intersects(a: tuple[float, float, float, float],
                    b: tuple[float, float, float, float]) -> bool:
    """两个 (w,s,e,n) 框是否相交（含边界相接）。"""
    return not (a[2] < b[0] or b[2] < a[0] or a[3] < b[1] or b[3] < a[1])


def segment_intersects_bbox(p1: tuple[float, float], p2: tuple[float, float],
                            bbox: tuple[float, float, float, float]) -> bool:
    """线段是否与框相交。

    先用端点包含判定，再用 **Liang-Barsky 参数裁剪**做精确求交 ——
    只判"端点是否在框内"会漏掉「线穿过框但两端都在框外」这一最常见情形
    （路线横穿风险区正是如此）。经纬度当平面处理，公里级尺度误差可忽略。
    """
    x1, y1 = p1
    x2, y2 = p2
    w, s, e, n = bbox
    if w <= x1 <= e and s <= y1 <= n:
        return True
    if w <= x2 <= e and s <= y2 <= n:
        return True
    dx, dy = x2 - x1, y2 - y1
    # Liang-Barsky：t 的可行区间与 [0,1] 求交
    t0, t1 = 0.0, 1.0
    for p, q in ((-dx, x1 - w), (dx, e - x1), (-dy, y1 - s), (dy, n - y1)):
        if p == 0:
            if q < 0:
                return False                       # 平行且在外侧
        else:
            r = q / p
            if p < 0:
                t0 = max(t0, r)
            else:
                t1 = min(t1, r)
            if t0 > t1:
                return False
    return True
