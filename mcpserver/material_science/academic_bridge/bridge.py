"""academic 项目本地调用包装（SPEC-02 Phase 1）。

每个 call_xxx 函数都是延迟导入 + 统一返回 dict，缺失依赖时抛 ImportError
由上层（academic_tools）降级。许可合规见仓库根目录 academic/LICENSES.md。
"""

from __future__ import annotations


def call_thermo(action: str, **kwargs) -> dict:
    """thermo (ChEDL)：化学品物性速查。

    action='property': name=化学品名/式，返回关键常数与默认工况物性
    action='vapor_pressure_temp': name, pressure_Pa → 反解饱和温度
    """
    from thermo.chemical import Chemical

    if action == "property":
        name = kwargs.get("name") or kwargs.get("chemical")
        if not name:
            raise ValueError("thermo property 需要 name 参数")
        c = Chemical(str(name), T=kwargs.get("T", 298.15), P=kwargs.get("P", 101325))
        return {
            "name": str(name),
            "phase": c.phase,
            "Tm_K": c.Tm, "Tb_K": c.Tb, "Tc_K": c.Tc, "Pc_Pa": c.Pc,
            "MW_g_mol": c.MW,
            "rho_kg_m3": c.rho, "Cp_J_mol_K": c.Cp,
            "k_W_m_K": c.k, "mu_Pa_s": c.mu,
        }
    if action == "vapor_pressure_temp":
        c = Chemical(str(kwargs["name"]))
        return {"name": str(kwargs["name"]),
                "T_at_P_K": c.VaporPressure.solve_property(float(kwargs["pressure_Pa"]))}
    raise ValueError(f"thermo 不支持的 action: {action}")


def call_coolprop(action: str, **kwargs) -> dict:
    """CoolProp：高精度工质热物性。

    action='property': fluid + 两个状态变量（name1/value1/name2/value2）+ output
      例: fluid='Water', output='D', name1='T', value1=300, name2='P', value2=101325
    action='critical': fluid → 临界点参数
    """
    from CoolProp.CoolProp import PropsSI

    if action == "property":
        value = PropsSI(kwargs["output"], kwargs["name1"], float(kwargs["value1"]),
                        kwargs["name2"], float(kwargs["value2"]), kwargs["fluid"])
        return {"fluid": kwargs["fluid"], "output": kwargs["output"], "value": value,
                "condition": f"{kwargs['name1']}={kwargs['value1']}, "
                             f"{kwargs['name2']}={kwargs['value2']}"}
    if action == "critical":
        fluid = kwargs["fluid"]
        return {"fluid": fluid,
                "Tcrit_K": PropsSI("Tcrit", "", 0, "", 0, fluid),
                "pcrit_Pa": PropsSI("pcrit", "", 0, "", 0, fluid),
                "rhocrit_kg_m3": PropsSI("rhomass_critical", "", 0, "", 0, fluid)}
    raise ValueError(f"coolprop 不支持的 action: {action}")


def call_chemformula(action: str, **kwargs) -> dict:
    """ChemFormula：化学式解析与计量。

    action='parse': formula → 式量/元素组成/质量分数
    action='reaction_mass': formulas=[...], coefficients=[...] → 加权和（配平辅助）
    """
    from chemformula import ChemFormula

    if action == "parse":
        cf = ChemFormula(str(kwargs["formula"]))
        return {
            "formula": cf.formula,
            "formula_weight_g_mol": round(cf.formula_weight, 4),
            "elements": dict(cf.element),
            "mass_fractions": {k: round(v, 4) for k, v in cf.mass_fraction.items()},
            "charged": cf.charged,
        }
    if action == "reaction_mass":
        total = sum(ChemFormula(f).formula_weight * c
                    for f, c in zip(kwargs["formulas"], kwargs["coefficients"]))
        return {"total_formula_weight_g_mol": round(total, 4)}
    raise ValueError(f"chemformula 不支持的 action: {action}")


def call_affine_gaps(action: str, **kwargs) -> dict:
    """AffineGaps：Gotoh 仿射空位比对。

    action='align': seq1, seq2 → 对齐结果与得分（默认 BLOSUM62）
    action='score': seq1, seq2 → 仅得分
    """
    if action == "align":
        from affine_gaps import needleman_wunsch_gotoh_alignment
        a1, a2, score = needleman_wunsch_gotoh_alignment(
            str(kwargs["seq1"]), str(kwargs["seq2"]))
        return {"aligned_seq1": a1, "aligned_seq2": a2, "score": score}
    if action == "score":
        from affine_gaps import needleman_wunsch_gotoh_score
        return {"score": needleman_wunsch_gotoh_score(
            str(kwargs["seq1"]), str(kwargs["seq2"]))}
    raise ValueError(f"affine_gaps 不支持的 action: {action}")


def call_pynite(action: str, **kwargs) -> dict:
    """Pynite：结构有限元（内置悬臂梁快算）。

    action='cantilever': L=跨长, E=弹性模量, I=惯性矩, P=端部集中力
      → 自由端挠度与根部弯矩（教科书解，用于快速校核）
    """
    if action != "cantilever":
        raise ValueError(f"Pynite 不支持的 action: {action}")
    from Pynite import FEModel3D

    L = float(kwargs["L"]); E = float(kwargs["E"])
    I = float(kwargs["I"]); P = float(kwargs["P"])
    n_nodes = 11  # 10 单元足够收敛；Pynite 3.x 需先定义材料与截面
    model = FEModel3D()
    model.add_material("Mat", E, E / 2.6, 0.3, 7850)
    model.add_section("Sec", 0.01, I, I, I * 2)
    dx = L / (n_nodes - 1)
    for i in range(n_nodes):
        model.add_node(f"N{i}", i * dx, 0, 0)
    for i in range(n_nodes - 1):
        model.add_member(f"M{i}", f"N{i}", f"N{i + 1}", "Mat", "Sec")
    model.def_support("N0", True, True, True, True, True, True)
    # P 沿全局 -Y（悬臂梁下挠），作用于末单元末端（自由端）
    model.add_member_pt_load(f"M{n_nodes - 2}", "FY", -P, dx, "Case1")
    model.add_load_combo("Combo1", {"Case1": 1.0})
    model.analyze()
    deflection = float(model.nodes[f"N{n_nodes - 1}"].DY["Combo1"])
    return {
        "L": L, "E": E, "I": I, "P": P,
        "deflection_free_end": deflection,
        "deflection_theory": -P * L**3 / (3 * E * I),
    }


# 项目名 → 调用函数分派表（键与 academic/ 目录名一致）
CALLERS = {
    "thermo": call_thermo,
    "CoolProp": call_coolprop,
    "ChemFormula": call_chemformula,
    "AffineGaps": call_affine_gaps,
    "Pynite": call_pynite,
}


def academic_call(project: str, action: str, **kwargs) -> dict:
    """统一调用入口：project 限定在 registry 中标记 call=True 的项目。"""
    from mcpserver.material_science.academic_bridge.registry import PROJECTS

    meta = PROJECTS.get(project)
    if meta is None:
        raise KeyError(f"未知项目: {project}（可用: {', '.join(PROJECTS)}）")
    if not meta["call"]:
        raise ValueError(f"项目 {project} 未启用本地调用（{meta['label']}："
                         f"见 academic/{project}/MODEL_INTERFACE.md）")
    caller = CALLERS.get(project)
    if caller is None:
        raise NotImplementedError(f"{project} 的调用包装尚未实现")
    return caller(action, **kwargs)
