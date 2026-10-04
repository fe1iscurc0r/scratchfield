"""academic_bridge 测试（SPEC-02 Phase 1 验收：16 项文档 + ≥5 项可调用）。

依赖：thermo / coolprop / chemformula / affine-gaps / PyniteFEA
      （缺失时对应测试跳过，registry/文档测试不受影响）
"""
import pytest

# 卷173 测试分层标注：smoke ⊂ core；未标注文件默认 full（pyproject.toml markers）
pytestmark = [pytest.mark.core]
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

ALL_PROJECTS = [
    "thermo", "CoolProp", "tespy", "pycalphad", "Clapeyron.jl", "PyXtal",
    "SLICES", "gemmi", "ChemFormula", "hyalite", "AffineGaps", "WaveBench",
    "rp2daq", "hololinked", "Pynite", "FEMcy",
]


def _skip_if_missing(import_name):
    import importlib.util
    return importlib.util.find_spec(import_name) is None


class TestDocsAndRegistry(unittest.TestCase):
    def test_16_model_interface_docs_exist(self):
        for proj in ALL_PROJECTS:
            doc = REPO_ROOT / "academic" / proj / "MODEL_INTERFACE.md"
            self.assertTrue(doc.exists(), f"缺 {proj} 的 MODEL_INTERFACE.md")
            text = doc.read_text(encoding="utf-8")
            self.assertIn("核心 API", text.replace("核心用法", "核心 API"))
            self.assertIn("数据格式", text)

    def test_registry_covers_16_and_licenses(self):
        from mcpserver.material_science.academic_bridge.registry import PROJECTS
        self.assertEqual(len(PROJECTS), 16)
        for name, meta in PROJECTS.items():
            self.assertTrue(meta["license"], f"{name} 缺许可声明")

    def test_licenses_manifest_exists(self):
        self.assertTrue((REPO_ROOT / "academic" / "LICENSES.md").exists())


class TestCalls(unittest.TestCase):
    @unittest.skipIf(_skip_if_missing("thermo"), "thermo 未安装")
    def test_thermo_property(self):
        from mcpserver.material_science.academic_bridge import academic_call
        r = academic_call("thermo", "property", name="toluene")
        self.assertAlmostEqual(r["Tb_K"], 383.75, delta=2.0)
        self.assertGreater(r["MW_g_mol"], 90)

    @unittest.skipIf(_skip_if_missing("CoolProp"), "coolprop 未安装")
    def test_coolprop_water_density(self):
        from mcpserver.material_science.academic_bridge import academic_call
        r = academic_call("CoolProp", "property", fluid="Water", output="D",
                          name1="T", value1=298.15, name2="P", value2=101325)
        self.assertAlmostEqual(r["value"], 997.0, delta=2.0)

    @unittest.skipIf(_skip_if_missing("chemformula"), "chemformula 未安装")
    def test_chemformula_parse(self):
        from mcpserver.material_science.academic_bridge import academic_call
        r = academic_call("ChemFormula", "parse", formula="H2O")
        self.assertAlmostEqual(r["formula_weight_g_mol"], 18.015, delta=0.05)
        self.assertEqual(r["elements"]["H"], 2)

    @unittest.skipIf(_skip_if_missing("affine_gaps"), "affine-gaps 未安装")
    def test_affine_gaps_alignment(self):
        from mcpserver.material_science.academic_bridge import academic_call
        r = academic_call("AffineGaps", "align",
                          seq1="GIVEQCCTSICSLYQLENYCN",
                          seq2="HSQGTFTSDYSKYLDSRAEQDFV")
        self.assertGreater(r["score"], 0)
        self.assertIn("-", r["aligned_seq1"] + r["aligned_seq2"])

    @unittest.skipIf(_skip_if_missing("Pynite"), "PyniteFEA 未安装")
    def test_pynite_cantilever_matches_theory(self):
        from mcpserver.material_science.academic_bridge import academic_call
        L, E, I, P = 10.0, 2.0e11, 1.0e-4, 1000.0
        r = academic_call("Pynite", "cantilever", L=L, E=E, I=I, P=P)
        theory = -P * L**3 / (3 * E * I)
        self.assertAlmostEqual(r["deflection_free_end"], theory,
                               delta=abs(theory) * 0.05)

    def test_call_guard_for_uncallable_project(self):
        from mcpserver.material_science.academic_bridge import academic_call
        with self.assertRaises(ValueError):
            academic_call("gemmi", "whatever")
        with self.assertRaises(KeyError):
            academic_call("no_such_project", "whatever")


class TestToolRegistration(unittest.TestCase):
    def test_register_tools_into_agent(self):
        from mcpserver.material_science.academic_bridge import register_academic_tools

        class _FakeAgent:
            tools = {}

        agent = _FakeAgent()
        register_academic_tools(agent)
        self.assertIn("academic_status", agent.tools)
        self.assertIn("academic_call", agent.tools)
        status = agent.tools["academic_status"]({})
        self.assertTrue(status["success"])
        self.assertEqual(status["total"], 16)
        # 验收线：≥5 项已装且可调用
        self.assertGreaterEqual(status["callable_installed"], 5)


if __name__ == "__main__":
    unittest.main()
