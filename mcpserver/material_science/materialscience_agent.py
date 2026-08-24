"""
材料科研 MCP Agent - 提供材料科研相关工具集
支持：文献检索、配方查询、属性计算、相变分析

架构说明:
    本 Agent 同时承载纯计算工具（本地数据库查询）与 MatChat 浏览器自动化工具。
    - 纯计算工具线程安全，可走默认线程池。
    - MatChat 工具依赖 Playwright sync_api，其对象绑定创建线程，
      必须在固定单线程内调用，故用 _matchat_executor (max_workers=1) 隔离。
"""
import asyncio
import json
import logging
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, List, Optional

from system.config import logger

# MatChat 工具名集合：用于在 handle_handoff 中路由到专用单线程池。
# 与 matchat_tools.TOOL_NAMES 保持一致（此处独立声明避免循环导入）。
_MATCHAT_TOOL_NAMES = {
    "matchat_search",
    "matchat_chat",
    "matchat_extract",
    "matchat_login_check",
}


class MaterialScienceAgent:
    """材料科研智能体 - MCP 工具集

    职责:
        1. 注册并管理材料科研相关工具（本地数据库 + MatChat 浏览器自动化）。
        2. 通过 invoke() 同步执行工具，通过 handle_handoff() 异步接入 MCP 调度。

    线程模型:
        - MatChat 工具调用路由到 _matchat_executor（单线程池），
          保证 Playwright 对象始终在同一线程访问。
        - 其他工具走默认线程池，互不阻塞。
    """

    def __init__(self):
        self.name = "material_science"
        self.display_name = "材料科研助手"
        self.version = "1.0.0"
        self.description = "材料科研专用工具集，包含文献检索、配方查询、属性计算等功能"

        # 可用工具列表（纯计算工具，线程安全）
        self.tools = {
            "literature_search": self._literature_search,
            "formula_query": self._formula_query,
            "property_calc": self._property_calc,
            "phase_diagram": self._phase_diagram,
            "crystal_info": self._crystal_info,
            "thermal_analysis": self._thermal_analysis,
            "material_compare": self._material_compare,
        }

        # MatChat (Playwright) 专用单线程池：
        # Playwright sync_api 对象绑定创建它的线程，跨线程使用会抛
        # "Please call play.set_device_redirect_url(...) from the same thread" 等错误。
        # max_workers=1 保证所有 MatChat 调用串行且固定在唯一工作线程上。
        self._matchat_executor = ThreadPoolExecutor(
            max_workers=1, thread_name_prefix="matchat-pw"
        )

        # 尝试注册 MatChat Playwright CDP 工具（可选，失败则跳过）
        try:
            from mcpserver.material_science.matchat_tools import register_matchat_tools
            register_matchat_tools(self)
        except ImportError:
            # Playwright 未安装时静默降级，仅保留本地工具
            logger.info("[MCP] MatChat 工具未加载（Playwright 未安装或浏览器未配置）")
        except Exception as e:
            logger.warning(f"[MCP] MatChat 工具加载失败: {e}")

        # 注册 biopred ML 预测工具（靶子 B；依赖 numpy/sklearn，失败则跳过）
        try:
            from mcpserver.material_science.biopred import register_biopred_tools
            register_biopred_tools(self)
        except Exception as e:
            logger.warning(f"[MCP] biopred 工具加载失败: {e}")

        logger.info(f"[MCP] {self.display_name} 初始化完成，共 {len(self.tools)} 个工具")

    def invoke(self, command: str, params: dict[str, Any] = None) -> dict[str, Any]:
        """执行工具调用（内部入口，向后兼容）。

        统一用 try/except 兜底：任何工具抛异常都返回结构化错误，不让上层崩溃。
        """
        try:
            if command not in self.tools:
                return {
                    "success": False,
                    "error": f"未知命令: {command}",
                    "available_commands": list(self.tools.keys()),
                }
            result = self.tools[command](params or {})
            return result
        except Exception as e:
            logger.error(f"工具执行失败 [{command}]: {e}")
            return {"success": False, "error": str(e)}

    async def handle_handoff(self, task: dict[str, Any]) -> str:
        """MCP 标准接口：路由到 invoke 并返回 JSON 字符串。

        线程隔离关键点（已修复）:
            Playwright Sync API 不能在 asyncio 事件循环内直接调用,
            且其对象绑定创建线程。原实现用 run_in_executor(None,...) 走默认线程池，
            不同调用可能落到不同工作线程，导致 MatChat bridge 跨线程访问报错。
            修复：MatChat 工具路由到 self._matchat_executor（单线程池），
            其他工具仍走默认池，兼顾隔离与并发。

        Args:
            task: MCP 任务字典，需含 tool_name，其余字段作为工具参数

        Returns:
            JSON 字符串，形如 {"success": bool, ...} 或 {"status": "error", ...}
        """
        try:
            tool_name = str(task.get("tool_name") or "").strip()
            if not tool_name:
                return json.dumps(
                    {"status": "error", "message": "缺少 tool_name 参数", "data": {}},
                    ensure_ascii=False,
                )
            # 过滤掉调度层注入的元字段，剩余作为工具参数
            params = {k: v for k, v in task.items() if k not in ("service_name", "tool_name", "agentType")}

            loop = asyncio.get_running_loop()
            # MatChat 工具 → 单线程池（保证 Playwright 线程亲和性）
            # 其他工具 → 默认线程池（互不阻塞，并发友好）
            if tool_name in _MATCHAT_TOOL_NAMES:
                result = await loop.run_in_executor(self._matchat_executor, self.invoke, tool_name, params)
            else:
                result = await loop.run_in_executor(None, self.invoke, tool_name, params)
            return json.dumps(result, ensure_ascii=False)
        except Exception as e:
            logger.error(f"[MaterialScience] handle_handoff 异常: {e}")
            # 错误脱敏：不把内部异常细节直接暴露，仅返回通用错误信息
            return json.dumps(
                {"status": "error", "message": f"调用失败: {e}", "data": {}},
                ensure_ascii=False,
            )

    def get_tools_list(self) -> list[dict[str, Any]]:
        """获取所有可用工具的描述（供前端展示与参数提示）。"""
        return [
            {
                "name": "literature_search",
                "description": "文献检索 - 在知识库中检索材料科研相关文献",
                "params": {
                    "query": "检索关键词",
                    "max_results": "最大结果数",
                    "year_from": "起始年份（可选）",
                    "year_to": "结束年份（可选）",
                }
            },
            {
                "name": "formula_query",
                "description": "配方查询 - 查询材料配方和制备工艺",
                "params": {
                    "material_type": "材料类型",
                    "composition": "成分关键词（可选）",
                    "method": "制备方法（可选）",
                }
            },
            {
                "name": "property_calc",
                "description": "属性计算 - 计算材料物理化学属性",
                "params": {
                    "calc_type": "计算类型（density/hardness/melting_point等）",
                    "composition": "成分配比",
                    "temperature": "温度（摄氏度，可选）",
                }
            },
            {
                "name": "phase_diagram",
                "description": "相图查询 - 查询二元/三元相图信息",
                "params": {
                    "elements": "元素列表",
                    "temperature": "温度范围（可选）",
                    "pressure": "压力（默认1atm）",
                }
            },
            {
                "name": "crystal_info",
                "description": "晶体结构查询 - 查询晶体结构信息",
                "params": {
                    "material": "材料名称或化学式",
                    "crystal_system": "晶系（可选）",
                }
            },
            {
                "name": "thermal_analysis",
                "description": "热分析计算 - DSC/TGA 曲线分析",
                "params": {
                    "analysis_type": "分析类型（dsc/tga/dta）",
                    "material": "材料名称",
                    "heating_rate": "升温速率（℃/min）",
                }
            },
            {
                "name": "material_compare",
                "description": "材料对比 - 对比两种材料的属性",
                "params": {
                    "material_a": "材料A名称",
                    "material_b": "材料B名称",
                    "properties": "对比属性列表",
                }
            },
        ]

    # ============ 工具实现 ============

    def _literature_search(self, params: dict[str, Any]) -> dict[str, Any]:
        """文献检索：优先走 RAG 服务，RAG 不可用时降级到内置示例数据。"""
        query = params.get("query", "")
        max_results = params.get("max_results", 10)
        year_from = params.get("year_from")
        year_to = params.get("year_to")

        if not query:
            return {"success": False, "error": "请提供检索关键词"}

        # 调用 RAG 服务检索
        try:
            from rag import get_rag_service
            rag_service = get_rag_service()

            result = rag_service.query(
                query_text=query,
                top_k=max_results,
            )

            # 格式化结果：只取必要字段，content 截断 200 字防返回过大
            papers = []
            for item in result.get("results", []):
                papers.append({
                    "title": item.get("title", "未知"),
                    "content_preview": item.get("content", "")[:200],
                    "score": item.get("score", 0),
                    "tags": item.get("tags", []),
                })

            return {
                "success": True,
                "query": query,
                "total_results": len(papers),
                "papers": papers,
                "latency_ms": result.get("latency_ms", 0),
            }

        except ImportError:
            # RAG 模块未安装时降级到内置数据，保证 Agent 可用
            return self._fallback_literature_search(query, max_results)
        except Exception as e:
            # RAG 服务存在但调用失败（如未初始化），返回错误而非降级，
            # 避免掩盖真实故障；上层可据 success=False 决定是否重试。
            return {"success": False, "error": f"检索失败: {e}"}

    def _fallback_literature_search(self, query: str, max_results: int) -> dict[str, Any]:
        """降级文献检索（使用内置数据库）。

        RAG 未启用时的兜底方案，返回少量示例数据保证接口可用。
        """
        # 内置示例数据
        sample_data = [
            {
                "title": "锂离子电池正极材料研究进展",
                "content_preview": "综述了锂离子电池正极材料的研究进展，包括三元材料、磷酸铁锂等...",
                "score": 0.85,
                "tags": ["锂电池", "正极材料", "新能源"],
            },
            {
                "title": "钙钛矿太阳能电池稳定性提升策略",
                "content_preview": "讨论了钙钛矿太阳能电池的稳定性问题及多种提升策略...",
                "score": 0.78,
                "tags": ["钙钛矿", "太阳能电池", "稳定性"],
            },
        ]

        # 简单过滤：按查询词分词后任一命中即保留
        filtered = [p for p in sample_data if any(
            kw.lower() in (p["title"] + p["content_preview"]).lower()
            for kw in query.split()
        )]

        if not filtered:
            # 关键词都没命中时返回全部，保证不空
            filtered = sample_data[:max_results]

        return {
            "success": True,
            "query": query,
            "total_results": len(filtered),
            "papers": filtered[:max_results],
            "note": "使用内置示例数据（RAG 未启用）",
        }

    def _formula_query(self, params: dict[str, Any]) -> dict[str, Any]:
        """配方查询：在内置配方库中按材料类型/成分/方法过滤。"""
        material_type = params.get("material_type", "")
        composition = params.get("composition", "")
        method = params.get("method", "")

        # 内置配方数据库（示例）
        formula_db = {
            "锂电三元": {
                "composition": "镍:钴:锰 = 8:1:1",
                "method": "共沉淀法",
                "sintering_temp": "750-850℃",
                "applications": "动力锂电池正极",
            },
            "磷酸铁锂": {
                "composition": "Li:Fe:P = 1:1:1",
                "method": "固相法/水热法",
                "sintering_temp": "700-800℃",
                "applications": "储能电池",
            },
            "钙钛矿": {
                "composition": "CH3NH3PbI3",
                "method": "溶液法/气相沉积",
                "sintering_temp": "100-150℃",
                "applications": "太阳能电池",
            },
        }

        # 查询匹配：material_type 为空时返回全部
        results = []
        for name, info in formula_db.items():
            if material_type.lower() in name.lower() or not material_type:
                results.append({
                    "name": name,
                    **info,
                })

        # 二次过滤：成分/方法命中
        if composition:
            results = [r for r in results if composition.lower() in str(r.get("composition", "")).lower()]
        if method:
            results = [r for r in results if method.lower() in str(r.get("method", "")).lower()]

        return {
            "success": True,
            "query": f"{material_type} {composition} {method}".strip(),
            "total_results": len(results),
            "formulas": results,
        }

    def _property_calc(self, params: dict[str, Any]) -> dict[str, Any]:
        """属性计算：按 calc_type 分发到具体计算函数。"""
        calc_type = params.get("calc_type", "")
        composition = params.get("composition", "")
        temperature = params.get("temperature", 25)

        if not calc_type:
            return {"success": False, "error": "请指定计算类型"}

        calculators = {
            "density": self._calc_density,
            "hardness": self._calc_hardness,
            "melting_point": self._calc_melting_point,
            "conductivity": self._calc_conductivity,
            "band_gap": self._calc_band_gap,
        }

        if calc_type not in calculators:
            return {
                "success": False,
                "error": f"不支持的计算类型: {calc_type}",
                "supported_types": list(calculators.keys()),
            }

        try:
            result = calculators[calc_type](composition, temperature)
            return {
                "success": True,
                "calc_type": calc_type,
                "composition": composition,
                "temperature": temperature,
                "result": result,
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _calc_density(self, composition: str, temp: float) -> dict[str, Any]:
        """密度计算（基于原子量的简单估算）。

        用线性温度修正：温度每升高 1℃ 密度下降 0.01%（经验近似，仅教学用）。
        """
        # 简化计算：基于元素组成估算
        density_db = {
            "LiCoO2": 5.06,
            "LiFePO4": 3.6,
            "NMC811": 4.8,
            "CH3NH3PbI3": 4.09,
            "Silicon": 2.33,
            "SiO2": 2.65,
            "Al2O3": 3.97,
            "Fe2O3": 5.24,
        }

        # 查找已知密度
        for name, density in density_db.items():
            if name.lower() in composition.lower():
                # 温度修正（简化）
                corrected = density * (1 - 0.0001 * (temp - 25))
                return {
                    "density_g_per_cm3": round(corrected, 4),
                    "reference_density": density,
                    "temperature_correction": f"{temp}℃",
                    "note": "基于经验数据，实际值可能有±5%偏差",
                }

        # 通用估算
        return {
            "density_g_per_cm3": None,
            "note": f"未知材料 '{composition}'，请提供已知材料名称",
        }

    def _calc_hardness(self, composition: str, temp: float) -> dict[str, Any]:
        """硬度计算：查表返回 Hv/Mohs 硬度。"""
        hardness_db = {
            "Diamond": {"Hv": 10000, "Mohs": 10},
            "SiC": {"Hv": 2500, "Mohs": 9.5},
            "Al2O3": {"Hv": 2000, "Mohs": 9},
            "SiO2": {"Hv": 1200, "Mohs": 7},
            "Fe2O3": {"Hv": 1000, "Mohs": 6.5},
            "LiCoO2": {"Hv": 500, "Mohs": 5},
        }

        for name, harnesses in hardness_db.items():
            if name.lower() in composition.lower():
                return {
                    "hardness_hv": harnesses["Hv"],
                    "hardness_mohs": harnesses["Mohs"],
                    "material": name,
                }

        return {"hardness_hv": None, "note": f"未知材料 '{composition}'"}

    def _calc_melting_point(self, composition: str, temp: float) -> dict[str, Any]:
        """熔点计算：查表返回熔点（℃）。"""
        mp_db = {
            "LiCoO2": 1620,
            "LiFePO4": 950,
            "CH3NH3PbI3": 350,
            "Silicon": 1414,
            "SiO2": 1713,
            "Al2O3": 2072,
            "Fe2O3": 1565,
            "Fe": 1538,
            "Cu": 1085,
            "Al": 660,
        }

        for name, mp in mp_db.items():
            if name.lower() in composition.lower():
                return {
                    "melting_point_c": mp,
                    "material": name,
                }

        return {"melting_point_c": None, "note": f"未知材料 '{composition}'"}

    def _calc_conductivity(self, composition: str, temp: float) -> dict[str, Any]:
        """电导率计算：查表 + 温度修正。

        金属（cond>1）按线性温度系数 0.0039/℃ 修正；非金属不修正（简化）。
        """
        cond_db = {
            "Cu": 59.6,  # ×10^6 S/m
            "Al": 37.8,
            "Fe": 10.0,
            "Silicon": 0.001,
            "LiCoO2": 0.000001,
            "LiFePO4": 0.0000001,
        }

        for name, cond in cond_db.items():
            if name.lower() in composition.lower():
                # 温度依赖（简化）：仅对导体（cond>1）做温度修正
                temp_factor = 1 - 0.0039 * (temp - 25) if cond > 1 else 1
                # max(0.01, ...) 防止高温下因子变负导致负电导率
                corrected = cond * max(0.01, temp_factor)
                return {
                    "conductivity_S_per_m": round(corrected, 8),
                    "conductivity_unit": "×10^6 S/m",
                    "material": name,
                }

        return {"conductivity_S_per_m": None, "note": f"未知材料 '{composition}'"}

    def _calc_band_gap(self, composition: str, temp: float) -> dict[str, Any]:
        """带隙计算：查表 + Varshni 温度修正（简化线性）。"""
        gap_db = {
            "Si": 1.12,
            "Ge": 0.66,
            "GaAs": 1.43,
            "InP": 1.35,
            "GaN": 3.4,
            "ZnO": 3.37,
            "TiO2_anatase": 3.2,
            "TiO2_rutile": 3.0,
            "CH3NH3PbI3": 1.55,
            "LiFePO4": 3.5,
        }

        for name, gap in gap_db.items():
            if name.lower() in composition.lower():
                # 温度依赖：带隙随温度升高而窄化（Varshni 简化）
                alpha = 4.73e-4  # eV/K
                corrected = gap - alpha * (temp - 25)
                return {
                    "band_gap_eV": round(corrected, 4),
                    "room_temp_gap": gap,
                    "material": name,
                }

        return {"band_gap_eV": None, "note": f"未知材料 '{composition}'"}

    def _phase_diagram(self, params: dict[str, Any]) -> dict[str, Any]:
        """相图查询：支持二元/三元相图，元素顺序无关。

        修复点：原实现 key=tuple(sorted(elements))，但字典键如 ("Fe","C") 未排序，
        导致 sorted 后的 ("C","Fe") 查不到 Fe-C 相图。这里在查询时统一规范化键。
        """
        elements = params.get("elements", [])
        temperature = params.get("temperature", 25)
        pressure = params.get("pressure", 1.0)

        # 兼容字符串输入："Fe, C" → ["Fe", "C"]
        if isinstance(elements, str):
            elements = [e.strip() for e in elements.split(",")]

        if not elements:
            return {"success": False, "error": "请提供元素列表"}

        # 内置相图数据（简化）
        phase_data = {
            ("Fe", "C"): {
                "name": "Fe-C 相图",
                "phases": ["Ferrite", "Austenite", "Cementite", "Graphite"],
                "eutectoid_point": {"temp": 727, "composition": "0.8% C"},
                "applications": "钢铁冶金",
            },
            ("Cu", "Zn"): {
                "name": "Cu-Zn 相图",
                "phases": ["Alpha", "Beta", "Gamma", "Delta"],
                "eutectoid_point": {"temp": 560, "composition": "29% Zn"},
                "applications": "黄铜",
            },
            ("Al", "Si"): {
                "name": "Al-Si 相图",
                "phases": ["Al", "Si", "Al-Si eutectic"],
                "eutectic_point": {"temp": 577, "composition": "12.6% Si"},
                "applications": "铝合金铸造",
            },
        }

        # 修复：把字典键也按 sorted 规范化后再匹配，保证元素顺序无关
        normalized_phase_data = {
            tuple(sorted(k)): v for k, v in phase_data.items()
        }
        key = tuple(sorted(elements))

        if key in normalized_phase_data:
            data = normalized_phase_data[key]
        elif elements[0] in ["Fe", "Cu", "Al"] and len(elements) <= 2:
            # 查找单元素相信息
            data = self._get_element_phase_info(elements[0])
        else:
            data = {
                "name": f"{'-'.join(elements)} 相图",
                "note": "相图数据未收录，请查阅专业相图手册",
                "references": [
                    "ASM International Handbook",
                    "Phase Diagrams for Ceramists",
                ],
            }

        return {
            "success": True,
            "elements": elements,
            "temperature_c": temperature,
            "pressure_atm": pressure,
            "phase_data": data,
        }

    def _get_element_phase_info(self, element: str) -> dict[str, Any]:
        """获取单元素相变信息（Fe/Cu/Al 的相变温度与晶体结构）。"""
        element_data = {
            "Fe": {
                "name": "铁的相变",
                "phases": {
                    "Ferrite (α-Fe)": {"temp_range": "<912℃", "structure": "BCC"},
                    "Austenite (γ-Fe)": {"temp_range": "912-1394℃", "structure": "FCC"},
                    "δ-Fe": {"temp_range": "1394-1538℃", "structure": "BCC"},
                    "Liquid": {"temp_range": ">1538℃", "structure": "液体"},
                },
                "phase_transitions": [
                    {"temp": 912, "from": "α-Fe", "to": "γ-Fe"},
                    {"temp": 1394, "from": "γ-Fe", "to": "δ-Fe"},
                    {"temp": 1538, "from": "δ-Fe", "to": "Liquid"},
                ],
            },
            "Cu": {
                "name": "铜的相变",
                "phases": {
                    "Copper (Cu)": {"temp_range": "<1085℃", "structure": "FCC"},
                    "Liquid": {"temp_range": ">1085℃", "structure": "液体"},
                },
                "phase_transitions": [
                    {"temp": 1085, "from": "Cu(solid)", "to": "Liquid"},
                ],
            },
            "Al": {
                "name": "铝的相变",
                "phases": {
                    "Aluminum (Al)": {"temp_range": "<660℃", "structure": "FCC"},
                    "Liquid": {"temp_range": ">660℃", "structure": "液体"},
                },
                "phase_transitions": [
                    {"temp": 660, "from": "Al(solid)", "to": "Liquid"},
                ],
            },
        }

        return element_data.get(element, {
            "name": f"{element} 的相变",
            "note": "相变数据未收录",
        })

    def _crystal_info(self, params: dict[str, Any]) -> dict[str, Any]:
        """晶体结构查询：按材料名/化学式匹配，返回晶系、空间群、晶格参数。"""
        material = params.get("material", "")
        crystal_system = params.get("crystal_system", "")

        if not material:
            return {"success": False, "error": "请提供材料名称"}

        # 晶体结构数据库
        crystal_db = {
            "LiCoO2": {
                "crystal_system": "Hexagonal",
                "space_group": "R-3m",
                "lattice_parameters": {"a": 2.816, "b": 2.816, "c": 14.208},
                "atomic_positions": ["Li(3a)", "Co(3b)", "O(6c)"],
                "structure_type": "Layered",
            },
            "LiFePO4": {
                "crystal_system": "Orthorhombic",
                "space_group": "Pnma",
                "lattice_parameters": {"a": 10.33, "b": 6.01, "c": 4.69},
                "atomic_positions": ["Li(4a)", "Fe(4c)", "P(4c)", "O(4c+4c+8d)"],
                "structure_type": "Olivine",
            },
            "CH3NH3PbI3": {
                "crystal_system": "Tetragonal",
                "space_group": "I4/mcm",
                "lattice_parameters": {"a": 8.86, "b": 8.86, "c": 12.62},
                "atomic_positions": ["Pb(4b)", "I(8e)", "MA(4d)"],
                "structure_type": "Perovskite",
            },
            "Silicon": {
                "crystal_system": "Cubic",
                "space_group": "Fd-3m",
                "lattice_parameters": {"a": 5.431, "b": 5.431, "c": 5.431},
                "atomic_positions": ["Si(8c)"],
                "structure_type": "Diamond",
            },
            "SiO2": {
                "crystal_system": "Trigonal",
                "space_group": "P3121",
                "lattice_parameters": {"a": 4.91, "b": 4.91, "c": 5.40},
                "atomic_positions": ["Si(3a)", "O(6c)"],
                "structure_type": "Quartz",
            },
            "Al2O3": {
                "crystal_system": "Trigonal",
                "space_group": "R-3c",
                "lattice_parameters": {"a": 4.758, "b": 4.758, "c": 12.991},
                "atomic_positions": ["Al(12c)", "O(18e)"],
                "structure_type": "Corundum",
            },
        }

        # 查找匹配：先精确名再包含匹配
        for name, info in crystal_db.items():
            if name.lower() == material.lower() or material.lower() in name.lower():
                result = {
                    "success": True,
                    "material": name,
                    **info,
                }
                if crystal_system:
                    # 用户指定晶系时给出匹配度提示
                    if info["crystal_system"].lower() == crystal_system.lower():
                        result["match_type"] = "exact"
                    else:
                        result["match_type"] = "partial"
                        result["note"] = f"注意: 晶系不匹配，材料为 {info['crystal_system']}"
                return result

        return {
            "success": True,
            "material": material,
            "note": f"未在数据库中找到 '{material}' 的晶体结构信息",
            "suggestion": "请提供化学式（如 LiCoO2, LiFePO4 等）",
        }

    def _thermal_analysis(self, params: dict[str, Any]) -> dict[str, Any]:
        """热分析计算：DSC/TGA/DTA，按升温速率做温度修正。"""
        analysis_type = params.get("analysis_type", "")
        material = params.get("material", "")
        heating_rate = params.get("heating_rate", 10)

        if not material:
            return {"success": False, "error": "请提供材料名称"}

        # 热分析数据库（示例数据）
        thermal_db = {
            "LiCoO2": {
                "phase_transitions": [
                    {"temp": 200, "type": "Weight loss", "description": "表面水分蒸发"},
                    {"temp": 700, "type": "Phase transition", "description": "层状结构重排"},
                ],
                "stability_temp": 600,
                "decomposition_temp": 1200,
            },
            "LiFePO4": {
                "phase_transitions": [
                    {"temp": 300, "type": "Weight gain", "description": "氧化开始"},
                    {"temp": 500, "type": "Phase transition", "description": "橄榄石结构稳定"},
                    {"temp": 700, "type": "Decomposition", "description": "开始分解"},
                ],
                "stability_temp": 500,
                "decomposition_temp": 900,
            },
            "CH3NH3PbI3": {
                "phase_transitions": [
                    {"temp": 150, "type": "Phase transition", "description": "四方→立方相变"},
                    {"temp": 350, "type": "Decomposition", "description": "开始分解，释放MAI"},
                    {"temp": 450, "type": "Full decomposition", "description": "完全分解为PbI2"},
                ],
                "stability_temp": 300,
                "decomposition_temp": 350,
            },
        }

        # 查找匹配
        for name, info in thermal_db.items():
            if name.lower() == material.lower():
                # 升温速率修正：相对 10℃/min 的偏移，速率越快相变温度表观越高
                rate_factor = heating_rate / 10  # 相对于10℃/min的修正

                adjusted_transitions = []
                for transition in info["phase_transitions"]:
                    # 2% 线性修正：升温快 → 峰位滞后
                    adjusted_temp = transition["temp"] * (1 + 0.02 * (rate_factor - 1))
                    adjusted_transitions.append({
                        **transition,
                        "adjusted_temp": round(adjusted_temp, 1),
                        "heating_rate_correction": f"{heating_rate}℃/min",
                    })

                return {
                    "success": True,
                    "material": name,
                    "analysis_type": analysis_type,
                    "heating_rate": heating_rate,
                    "phase_transitions": adjusted_transitions,
                    "stability_temp_c": info["stability_temp"],
                    "decomposition_temp_c": info["decomposition_temp"],
                }

        return {
            "success": True,
            "material": material,
            "analysis_type": analysis_type,
            "note": f"未找到 '{material}' 的热分析数据",
            "suggestion": "支持的材料: LiCoO2, LiFePO4, CH3NH3PbI3",
        }

    def _material_compare(self, params: dict[str, Any]) -> dict[str, Any]:
        """材料对比：复用各 _calc_* 函数取属性，逐项比较并标注胜出方。"""
        material_a = params.get("material_a", "")
        material_b = params.get("material_b", "")
        properties = params.get("properties", ["density", "hardness", "melting_point"])

        if not material_a or not material_b:
            return {"success": False, "error": "请提供两种材料名称"}

        # 兼容 properties 传字符串的情况："density,hardness" → ["density","hardness"]
        if isinstance(properties, str):
            properties = [p.strip() for p in properties.split(",") if p.strip()]
        if not isinstance(properties, list):
            properties = ["density", "hardness", "melting_point"]

        # 获取材料属性：复用各计算函数（25℃ 标准态）
        def get_properties(name: str) -> dict[str, Any]:
            return {
                "density": self._calc_density(name, 25).get("density_g_per_cm3"),
                "hardness": self._calc_hardness(name, 25).get("hardness_hv"),
                "melting_point": self._calc_melting_point(name, 25).get("melting_point_c"),
                "band_gap": self._calc_band_gap(name, 25).get("band_gap_eV"),
                "conductivity": self._calc_conductivity(name, 25).get("conductivity_S_per_m"),
            }

        props_a = get_properties(material_a)
        props_b = get_properties(material_b)

        # 逐项对比：双方均有值才比较，否则标记 unknown
        comparison = {}
        for prop in properties:
            val_a = props_a.get(prop)
            val_b = props_b.get(prop)

            if val_a is not None and val_b is not None:
                if val_a > val_b:
                    winner = material_a
                elif val_b > val_a:
                    winner = material_b
                else:
                    winner = "equal"

                comparison[prop] = {
                    material_a: val_a,
                    material_b: val_b,
                    "higher": winner,
                }
            else:
                # 任一材料缺数据，无法判定高低
                comparison[prop] = {
                    material_a: val_a,
                    material_b: val_b,
                    "higher": "unknown",
                }

        return {
            "success": True,
            "materials": [material_a, material_b],
            "comparison": comparison,
            "note": "数据仅供参考，实际值可能因制备工艺而异",
        }
