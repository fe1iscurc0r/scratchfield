"""W71-03 工单↔代码知识图谱测试。"""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

from workorder_graph import WorkorderGraph


def _graph():
    g = WorkorderGraph()
    g.add_commit("c1", ["tools/adif.py", "docs/x.md"], "w71-09")
    g.add_commit("c2", ["tools/soft_lora_phy.py"], "w71-08")
    g.add_commit("c3", ["tools/adif.py", "tools/test_adif.py"], "w71-09")
    return g


def test_files_for_workorder():
    g = _graph()
    assert g.files_for_workorder("w71-09") == {"tools/adif.py", "docs/x.md", "tools/test_adif.py"}


def test_workorders_for_file():
    g = _graph()
    assert g.workorders_for_file("tools/adif.py") == {"w71-09"}


def test_commits_touching_file():
    g = _graph()
    assert g.commits_touching_file("tools/adif.py") == ["c1", "c3"]


def test_trace():
    g = _graph()
    t = g.trace("tools/adif.py")
    assert "w71-09" in t and "tools/test_adif.py" in t
