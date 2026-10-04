"""木质素相关合成路线示例数据（I-02 内置，标注为示例）。

重要：以下 5 条为**示例数据**（is_example=True，source 标注「示例数据·待真机采集」），
数值为木质素常见工艺的近似量级，供 schema/store/retrieve/validator 演示与测试用，
**不可作为科研引用依据**。真实合成路线数据留真机（天选7 陆墨环境）导入。
"""
from __future__ import annotations

from .schema import Conditions, Property, Reactant, Route

# 5 条木质素相关合成路线（示例，来源留真机）
EXAMPLE_ROUTES: list[Route] = [
    Route(
        name="碱木质素碱溶酸析提取",
        product="碱木质素",
        method="碱溶酸析法",
        yield_min=40.0,
        yield_max=60.0,
        source="示例数据·待真机采集",
        is_example=True,
        description="造纸黑液加碱溶出木质素，再酸化沉淀分离（示例量级）",
        reactants=[
            Reactant(name="造纸黑液", amount=1.0, unit="L", role="原料"),
            Reactant(name="氢氧化钠", amount=20.0, unit="g", role="碱"),
            Reactant(name="硫酸", amount=0.0, unit="mL", role="酸化"),
        ],
        conditions=Conditions(temp_min_c=60.0, temp_max_c=90.0,
                              pressure_bar=1.0, time_h=3.0, atmosphere="空气"),
        properties=[Property(name="decomposition_temp_c", value=250.0, unit="℃")],
    ),
    Route(
        name="木质素磺化制木质素磺酸钠",
        product="木质素磺酸钠",
        method="磺甲基化",
        yield_min=80.0,
        yield_max=90.0,
        source="示例数据·待真机采集",
        is_example=True,
        description="碱木质素在亚硫酸盐/甲醛体系中磺化（示例量级）",
        reactants=[
            Reactant(name="碱木质素", amount=100.0, unit="g", role="原料"),
            Reactant(name="亚硫酸钠", amount=30.0, unit="g", role="磺化剂"),
            Reactant(name="甲醛", amount=20.0, unit="mL", role="交联剂"),
        ],
        conditions=Conditions(temp_min_c=150.0, temp_max_c=170.0,
                              pressure_bar=5.0, time_h=5.0, atmosphere="氮气"),
        properties=[Property(name="density_g_cm3", value=1.35, unit="g/cm³")],
    ),
    Route(
        name="木质素基多孔碳 KOH 活化",
        product="木质素基多孔碳",
        method="碳化 + KOH 活化",
        yield_min=30.0,
        yield_max=45.0,
        source="示例数据·待真机采集",
        is_example=True,
        description="木质素高温碳化后 KOH 活化制多孔碳（示例量级）",
        reactants=[
            Reactant(name="木质素", amount=10.0, unit="g", role="原料"),
            Reactant(name="氢氧化钾", amount=20.0, unit="g", role="活化剂"),
        ],
        conditions=Conditions(temp_min_c=700.0, temp_max_c=900.0,
                              pressure_bar=1.0, time_h=2.0, atmosphere="氮气"),
        properties=[Property(name="specific_surface_area_m2_g", value=1500.0, unit="m²/g")],
    ),
    Route(
        name="木质素纳米颗粒反溶剂沉淀",
        product="木质素纳米颗粒",
        method="反溶剂沉淀法",
        yield_min=50.0,
        yield_max=75.0,
        source="示例数据·待真机采集",
        is_example=True,
        description="碱木质素溶液注入乙醇反溶剂成核（示例量级）",
        reactants=[
            Reactant(name="碱木质素", amount=1.0, unit="g", role="原料"),
            Reactant(name="乙醇", amount=50.0, unit="mL", role="反溶剂"),
        ],
        conditions=Conditions(temp_min_c=20.0, temp_max_c=30.0,
                              pressure_bar=1.0, time_h=1.0, atmosphere="空气"),
        properties=[Property(name="density_g_cm3", value=1.30, unit="g/cm³")],
    ),
    Route(
        name="木质素催化加氢解聚",
        product="芳香单体混合物",
        method="催化加氢解聚",
        yield_min=20.0,
        yield_max=35.0,
        source="示例数据·待真机采集",
        is_example=True,
        description="木质素在镍基催化剂上加氢解聚为芳香单体（示例量级）",
        reactants=[
            Reactant(name="木质素", amount=5.0, unit="g", role="原料"),
            Reactant(name="氢气", amount=0.0, unit="L", role="还原剂"),
            Reactant(name="Ni/Al2O3", amount=0.5, unit="g", role="催化剂"),
        ],
        conditions=Conditions(temp_min_c=250.0, temp_max_c=300.0,
                              pressure_bar=40.0, time_h=6.0, atmosphere="氢气"),
        properties=[Property(name="yield_percent", value=28.0, unit="%")],
    ),
]


def seed_examples(store) -> int:
    """把示例路线入库（幂等：已存在同名则跳过），返回本次插入条数。"""
    existing = {r.name for r in store.list_routes()}
    n = 0
    for route in EXAMPLE_ROUTES:
        if route.name in existing:
            continue
        store.add_route(route)
        n += 1
    return n
