"""W69-07 融合测试：卫星过境跟踪（TLE 解析 + 传播 + 方位仰角 + 过境窗口）。

运行：python -m pytest tools/test_satellite_track.py -q
"""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

import numpy as np
from satellite_track import RE, find_pass, parse_tle, propagate_eci, topocentric_az_el

# 合成 TLE：赤道近圆轨道（倾角 0），保证过境赤道地面站；周期约 90 分钟
LINE1 = "1 25544U 98067A   25001.00000000  .00000000  00000-0  00000-0 0  9990"
LINE2 = "2 25544   0.0000   0.0000 0000000   0.0000   0.0000 15.50000000  9990"


def test_parse_tle_extracts_elements():
    el = parse_tle(LINE1, LINE2)
    assert abs(np.rad2deg(el["inclination"]) - 0.0) < 0.1
    assert el["mean_motion"] > 0
    assert el["semi_major_axis"] > RE + 300e3  # LEO 轨道


def test_propagate_periodic():
    """一个轨道周期后位置回到起点（Kepler 传播自洽）。"""
    el = parse_tle(LINE1, LINE2)
    period = 2 * np.pi / el["mean_motion"]
    p0 = propagate_eci(el, np.array([0.0]))
    p1 = propagate_eci(el, np.array([period]))
    assert np.allclose(p0, p1, atol=1e-6)


def test_zenith_gives_high_elevation():
    """卫星在头顶（天顶方向）→ 仰角接近 90°。"""
    gs = np.array([RE, 0.0, 0.0])  # 地面站（赤道、经度 0）
    up = gs / np.linalg.norm(gs)
    sat = gs + 400e3 * up  # 卫星在头顶上方 400km
    az, el = topocentric_az_el(sat[None, :], gs, gmst=0.0)
    assert np.rad2deg(el[0]) > 80.0


def test_find_pass_detects_overhead_pass():
    """过境窗口：近顶过境能被扫到，峰值仰角 > 0。"""
    el = parse_tle(LINE1, LINE2)
    gs = np.array([RE, 0.0, 0.0])
    r = find_pass(el, gs, gmst=0.0, duration_s=7200.0, dt_s=10.0)
    assert r["has_pass"] is True
    assert r["peak_el_deg"] > 0.0


def test_find_pass_reports_aos_los_ordering():
    el = parse_tle(LINE1, LINE2)
    gs = np.array([RE, 0.0, 0.0])
    r = find_pass(el, gs, gmst=0.0, duration_s=7200.0, dt_s=10.0)
    if r["has_pass"]:
        assert r["aos_s"] < r["los_s"]
