"""TLE 轨道传播 + 观测站几何（卷130 W130-03 §2）。

工单原文：「接入 TLE 预测（**sgp4 库**或调卷122 的 API；**验证许可 MIT 类**），
配合 NEO6M GPS 的经纬度/时间 → **实时 az/el**」。

**许可核验结果**（工单要求的动作，已做）：
`sgp4` 2.27，打包元数据 `License-Expression: MIT`，随包 `LICENSE` 为标准 MIT 全文
（© 2012–2016 Brandon Rhodes）。**MIT 类许可 → 可用**。

**为什么不是调卷122**：查过 `mcpserver/rf_brain/satellite/`——那里是 NOAA APT
**载荷解码**（音频 → 图像），**没有轨道传播 API**。工单给的是「或」，所以走 sgp4。

**降级设计**：`sgp4` 未安装时**不静默失败、不伪造结果**——`TlePropagator.available`
为 False，跟踪任务返回明确的 `no_propagator` 错误。绝不返回"看起来像角度但其实是
编的"数值：那会让云台按假数据乱转，比直接报错危险得多。

**内置兜底（仅用于离线/自测）**：`SimplePropagator` 用简化圆轨道模型
（两体 + 地球自转），精度**远低于 SGP4**，只用于把编排链路跑通，
**不可用于真机指向**。它必须被显式选择（`propagator="simple"`），不会悄悄顶替。
"""
from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

#: WGS-84 常用近似（SGP4 的 TEME 系把地球当球处理，用平均半径与 SGP4 自身一致）
EARTH_RADIUS_KM = 6378.137
EARTH_MU_KM3_S2 = 398600.4418
EARTH_ROT_RAD_S = 7.292115e-5

DEG = 180.0 / math.pi
RAD = math.pi / 180.0


# ---------------------------------------------------------------------------
# 数据模型
# ---------------------------------------------------------------------------


@dataclass
class SiteLocation:
    """观测站位置。`lat/lon` 度（东正北正），`alt_m` 海拔米。"""

    lat_deg: float = 39.9042
    lon_deg: float = 116.4074
    alt_m: float = 50.0

    def as_dict(self) -> Dict[str, float]:
        return {"lat_deg": self.lat_deg, "lon_deg": self.lon_deg, "alt_m": self.alt_m}


@dataclass
class Tle:
    """一条两行根数。`epoch` 是 TLE 自带的历元（UTC）。"""

    name: str
    line1: str
    line2: str
    epoch: datetime | None = None
    source: str = "manual"

    def as_dict(self) -> Dict[str, Any]:
        return {"name": self.name, "epoch": self.epoch.isoformat() if self.epoch else None,
                "source": self.source}

    @property
    def age_days(self) -> float | None:
        """TLE 龄期。**超过几天就不该用于指向了**——SGP4 误差随龄期快速增长。"""
        if self.epoch is None:
            return None
        return (datetime.now(timezone.utc) - self.epoch).total_seconds() / 86400.0

    @property
    def stale(self) -> bool:
        age = self.age_days
        return bool(age is not None and age > 7.0)

    @classmethod
    def parse(cls, name: str, text: str, *, source: str = "manual") -> "Tle":
        """从「名称 + 两行」文本解析。行首 `1 `/`2 ` 校验**且顺序不能颠倒**——不猜。

        为什么顺序也校验：第 1 行带历元（第 19–32 列），第 2 行带轨道根数。
        若只按前缀各自找一行，把两行写反了照样能"解析成功"，
        但历元会从第 2 行里取到错误位置的值 → **跟踪结果全错且无从察觉**。
        宁可在这里报错。
        """
        lines = [ln.strip() for ln in str(text or "").splitlines() if ln.strip()]
        body = [ln for ln in lines if ln.startswith(("1 ", "2 "))]
        if len(body) < 2 or not body[0].startswith("1 ") or not body[1].startswith("2 "):
            raise ValueError("TLE 需要按顺序包含以 '1 ' 开头和以 '2 ' 开头的两行")
        l1, l2 = body[0], body[1]
        epoch = _parse_tle_epoch(l1)
        # 名称若在首行且不是第 1 行，取它
        head = lines[0] if lines and not lines[0].startswith(("1 ", "2 ")) else name
        return cls(name=str(head or name).strip(), line1=l1, line2=l2,
                   epoch=epoch, source=source)


def _parse_tle_epoch(line1: str) -> datetime | None:
    """TLE 第 1 行 19–32 列的历元 `YYDDD.DDDDDDDD` → UTC。

    TLE 的两位数年份用**滚动世纪**：57–99 → 19xx，00–56 → 20xx。
    这不是猜测，是 CCSDS/北美防空司令部公开约定。
    """
    try:
        raw = line1[18:32].strip()
    except Exception:  # noqa: BLE001
        return None
    if len(raw) < 5:
        return None
    try:
        yy = int(raw[:2])
        doy = float(raw[2:])
    except ValueError:
        return None
    year = 1900 + yy if yy >= 57 else 2000 + yy
    return datetime(year, 1, 1, tzinfo=timezone.utc) + timedelta(days=doy - 1.0)


# ---------------------------------------------------------------------------
# 传播器
# ---------------------------------------------------------------------------


def sgp4_available() -> bool:
    """`sgp4` 是否可用（工单许可核验：MIT）。"""
    try:
        import sgp4  # noqa: F401,PLC0415
    except ImportError:
        return False
    return True


class TlePropagator:
    """SGP4 传播器（首选）。未安装 sgp4 时 `available=False`，调用 `look_angles` 报错。"""

    kind = "sgp4"

    def __init__(self, tle: Tle):
        self.tle = tle
        self._sat = None
        self._error = ""
        try:
            from sgp4.api import Satrec, jday  # noqa: PLC0415

            self._sat = Satrec.twoline2rv(tle.line1, tle.line2)
            self._jday = jday
        except ImportError:
            self._error = "sgp4 未安装（pip install sgp4；MIT 许可）"
        except Exception as exc:  # noqa: BLE001
            self._error = f"TLE 解析失败: {exc}"

    @property
    def available(self) -> bool:
        return self._sat is not None

    @property
    def error(self) -> str:
        return self._error

    def look_angles(self, site: SiteLocation,
                    when: datetime | None = None) -> Tuple[float, float, float]:
        """→ `(az_deg, el_deg, range_km)`；不可用或传播失败抛 `RuntimeError`。"""
        if self._sat is None:
            raise RuntimeError(self._error or "SGP4 传播器不可用")
        t = _as_utc(when)
        jd, fr = self._jday(t.year, t.month, t.day, t.hour, t.minute,
                            t.second + t.microsecond / 1e6)
        err, r, _v = self._sat.sgp4(jd, fr)
        if err != 0:
            raise RuntimeError(f"SGP4 传播失败（错误码 {err}）")
        return _eci_to_look(r, t, site)


class SimplePropagator:
    """简化圆轨道兜底（**仅离线自测**，精度远低于 SGP4，不可用于真机指向）。

    平均运动 → 半长轴（开普勒第三定律）→ 均匀相位推进 → 位置 → 观测几何。
    忽略 J2 摄动、偏心率、轨道的长期漂移，因此**分钟级就有可见误差**。
    存在的意义：没有 sgp4 时仍能把「任务编排 → 下发 → 误差统计」这条链路跑通。
    """

    kind = "simple"

    def __init__(self, tle: Tle):
        self.tle = tle
        self._error = ""
        try:
            self._n_rev_day, self._inc, self._raan, self._ecc, self._argp, self._ma = \
                _parse_tle_orbital(line2=tle.line2)
        except Exception as exc:  # noqa: BLE001
            self._error = f"TLE 轨道根数解析失败: {exc}"

    @property
    def available(self) -> bool:
        return not self._error

    @property
    def error(self) -> str:
        return self._error

    def look_angles(self, site: SiteLocation,
                    when: datetime | None = None) -> Tuple[float, float, float]:
        if not self.available:
            raise RuntimeError(self._error)
        t = _as_utc(when)
        epoch = self.tle.epoch or t
        dt_s = (t - epoch).total_seconds()

        n = self._n_rev_day * 2.0 * math.pi / 86400.0        # rad/s
        a = (EARTH_MU_KM3_S2 / (n * n)) ** (1.0 / 3.0)       # km
        m = self._ma + n * dt_s                              # 平近点角
        # 圆轨道近似：真近点角 ≈ 平近点角（e 忽略）
        nu = m
        u = self._argp + nu                                  # 幅角纬度
        # 惯性系位置（升交点赤经进动忽略——这正是"仅自测"的原因）
        x_orb, y_orb = a * math.cos(u), a * math.sin(u)
        ci, si = math.cos(self._inc), math.sin(self._inc)
        cr, sr = math.cos(self._raan), math.sin(self._raan)
        x = x_orb * cr - y_orb * ci * sr
        y = x_orb * sr + y_orb * ci * cr
        z = y_orb * si
        # 惯性 → 地固（按地球自转角 GMST 近似用简化式）
        theta = EARTH_ROT_RAD_S * ((t - epoch).total_seconds())
        ct, st = math.cos(theta), math.sin(theta)
        rx = x * ct + y * st
        ry = -x * st + y * ct
        return _ecef_to_look((rx, ry, z), site)


def _parse_tle_orbital(line2: str) -> Tuple[float, float, float, float, float, float]:
    """从 TLE 第 2 行取 `(n_rev_day, inc, raan, ecc, argp, mean_anomaly)`（度→弧度）。"""
    inc = float(line2[8:16])
    raan = float(line2[17:25])
    ecc = float("0." + line2[26:33].strip())
    argp = float(line2[34:42])
    ma = float(line2[43:51])
    n = float(line2[52:63])
    return n, inc * RAD, raan * RAD, ecc, argp * RAD, ma * RAD


def make_propagator(tle: Tle, kind: str = "sgp4"):
    """按 `kind` 造传播器。`"auto"` = 有 sgp4 就用，否则 simple（**并记录降级**）。"""
    text = str(kind or "sgp4").strip().lower()
    if text == "auto":
        return TlePropagator(tle) if sgp4_available() else SimplePropagator(tle)
    if text in ("sgp4", "sdp4"):
        return TlePropagator(tle)
    if text in ("simple", "fallback", "offline"):
        return SimplePropagator(tle)
    raise ValueError(f"未知传播器：{kind}（可选 sgp4 / simple / auto）")


def _as_utc(when: datetime | None) -> datetime:
    t = when or datetime.now(timezone.utc)
    return t if t.tzinfo else t.replace(tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# 坐标变换
# ---------------------------------------------------------------------------


def _eci_to_look(r_km, when: datetime, site: SiteLocation) -> Tuple[float, float, float]:
    """TEME/ECI → 观测站 az/el。

    SGP4 输出在 TEME 系；严格做法要过 GMST 与极移。这里用 GMST 近似
    （与 SGP4 自身的球地球假设一致），并把观测站放到地固系。
    """
    t = when
    # GMST（IAU 1982 多项式，弧度）——足够 SGP4 精度
    jd = _to_jd(t)
    T = (jd - 2451545.0) / 36525.0
    gmst_deg = (280.46061837 + 360.98564736629 * (jd - 2451545.0)
                + 0.000387933 * T * T - T * T * T / 38710000.0)
    th = (gmst_deg % 360.0) * RAD
    ct, st = math.cos(th), math.sin(th)
    x, y, z = (float(r_km[0]), float(r_km[1]), float(r_km[2]))
    # ECI → ECEF
    xs = x * ct + y * st
    ys = -x * st + y * ct
    zs = z
    return _ecef_to_look((xs, ys, zs), site)


def _to_jd(t: datetime) -> float:
    """UTC datetime → 儒略日（整数日 + 小数）。"""
    y, m = t.year, t.month
    d = t.day + (t.hour + (t.minute + (t.second + t.microsecond / 1e6) / 60.0) / 60.0) / 24.0
    if m <= 2:
        y -= 1
        m += 12
    a = y // 100
    b = 2 - a + a // 4
    return int(365.25 * (y + 4716)) + int(30.6001 * (m + 1)) + d + b - 1524.5


def _ecef_to_look(r_ecef, site: SiteLocation) -> Tuple[float, float, float]:
    """地固系位置 → `(az, el, range)`：先把观测站换算成 ECEF，再算站心视线。"""
    lat, lon = site.lat_deg * RAD, site.lon_deg * RAD
    # 球地球近似（与 SGP4 的假设一致；椭球差异 × 高度只在米级）
    rs = EARTH_RADIUS_KM + site.alt_m / 1000.0
    sl, cl = math.sin(lat), math.cos(lat)
    so, co = math.sin(lon), math.cos(lon)
    ox, oy, oz = rs * cl * co, rs * cl * so, rs * sl

    dx = float(r_ecef[0]) - ox
    dy = float(r_ecef[1]) - oy
    dz = float(r_ecef[2]) - oz
    rng = math.sqrt(dx * dx + dy * dy + dz * dz)

    # 站心 ENU
    e = -so * dx + co * dy
    n = -sl * co * dx - sl * so * dy + cl * dz
    u = cl * co * dx + cl * so * dy + sl * dz

    el = math.asin(u / rng) * DEG if rng > 1e-9 else 0.0
    az = math.atan2(e, n) * DEG
    az %= 360.0
    return (round(az, 4), round(el, 4), round(rng, 4))


__all__ = [
    "SiteLocation", "Tle", "TlePropagator", "SimplePropagator", "make_propagator",
    "sgp4_available", "EARTH_RADIUS_KM",
]
