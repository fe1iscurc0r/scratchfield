"""态势数据源清单最小原型（P2-3 · W73-05 Shadowbroker）。

依据 docs/shadowbroker-态势-评估.md：多域态势数据源聚合（ADS-B/AIS/卫星/震情），
AGPL 只参考设计不融合。此处做一个「合规数据源注册表」——数据源按类别登记，
按合规性过滤，作为 sentinel_intel 的扩展清单。

原型（纯 stdlib）：
  - IntelSourceRegistry：register(source) / compliant()（合规源）/ by_category()

运行：python tools/intel_source_registry.py
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class IntelSource:
    name: str
    category: str       # adsb / ais / seismic / satellite / ...
    compliant: bool     # 合规（合法公开 API / 授权）

    def __post_init__(self):
        pass


@dataclass
class IntelSourceRegistry:
    """态势数据源注册表：按类别登记 + 合规过滤。"""

    sources: list[IntelSource] = field(default_factory=list)

    def register(self, name: str, category: str, compliant: bool = True) -> None:
        self.sources.append(IntelSource(name, category, compliant))

    def compliant(self) -> list[IntelSource]:
        return [s for s in self.sources if s.compliant]

    def by_category(self, category: str) -> list[IntelSource]:
        return [s for s in self.sources if s.category == category]

    def categories(self) -> list[str]:
        return sorted({s.category for s in self.sources})


if __name__ == "__main__":
    reg = IntelSourceRegistry()
    reg.register("OpenSky ADS-B", "adsb")
    reg.register("USGS Earthquake", "seismic")
    reg.register("CelesTrak TLE", "satellite")
    reg.register("Tor .onion feed", "darknet", compliant=False)  # 合规标注
    print("[合规源]", [s.name for s in reg.compliant()])
    print("[类别]", reg.categories())
