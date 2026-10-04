"""intel_source_registry 测试（P2-3 原型）。"""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from intel_source_registry import IntelSourceRegistry


def test_register_and_compliant_filter():
    reg = IntelSourceRegistry()
    reg.register("OpenSky ADS-B", "adsb")
    reg.register("Tor .onion feed", "darknet", compliant=False)
    names = {s.name for s in reg.compliant()}
    assert "OpenSky ADS-B" in names
    assert "Tor .onion feed" not in names


def test_by_category():
    reg = IntelSourceRegistry()
    reg.register("OpenSky ADS-B", "adsb")
    reg.register("USGS Earthquake", "seismic")
    assert len(reg.by_category("adsb")) == 1
    assert reg.by_category("seismic")[0].name == "USGS Earthquake"


def test_categories():
    reg = IntelSourceRegistry()
    reg.register("A", "adsb")
    reg.register("B", "seismic")
    assert reg.categories() == ["adsb", "seismic"]
