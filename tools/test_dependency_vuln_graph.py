"""dependency_vuln_graph 测试（P2-2 原型）。"""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from dependency_vuln_graph import VulnGraph


def test_add_vuln_bidirectional():
    g = VulnGraph()
    g.add_vuln("lib", "CVE-1", "high")
    assert g.vulns_for("lib") == {"CVE-1"}
    assert g.affected_deps("CVE-1") == {"lib"}


def test_impact_chain_reaches_transitive():
    g = VulnGraph()
    g.add_dependency("app", "lib-a")
    g.add_dependency("lib-a", "lib-b")
    g.add_vuln("lib-b", "CVE-1", "high")
    assert "CVE-1" in g.impact_chain("app")


def test_empty_graph():
    g = VulnGraph()
    assert g.vulns_for("x") == set()
    assert g.impact_chain("x") == set()
