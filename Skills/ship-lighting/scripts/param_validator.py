#!/usr/bin/env python3
"""
param_validator.py — HTTP API 参数校验模块（v4.0）
工作流：LLM(你) → tool_dispatcher → param_validator → api_client → HTTP API

每个工具定义：
  required: [必填参数列表]
  optional: [可选参数列表]
  types: {参数名: "类型说明"}
  enums: {参数名: [有效值列表]}  # 枚举约束
  hints: {参数名: "提示说明"}

校验失败返回结构化信息供 LLM 展示给用户。
"""

import json
import sys
from pathlib import Path

# 将同级目录加入 path，方便导入 api_client
SCRIPTS_DIR = Path(__file__).parent
sys.path.insert(0, str(SCRIPTS_DIR))

# ──────────────────────────────────────────────
# 工具 → API 函数映射 + 参数规则
# ──────────────────────────────────────────────

TOOL_RULES = {
    # ═══════════════════════════════
    # 图纸解析
    # ═══════════════════════════════
    "primary_parse": {
        "required": ["file_path"],
        "optional": ["import_mode", "pid"],
        "types": {"file_path": "文件路径（.dwg/.dxf）", "import_mode": "cover|increment", "pid": "项目ID"},
        "enums": {"import_mode": ["cover", "increment"]},
        "hints": {"file_path": "需要上传的 DWG/DXF 图纸路径", "import_mode": "导入模式：cover(覆盖) / increment(增量)"},
    },
    "submit_preview": {
        "required": ["record_id", "layer_mappings"],
        "optional": [],
        "types": {"record_id": "记录ID", "layer_mappings": "图层映射列表 [{'layer_id','layer_name','layer_tag'}]"},
        "hints": {"layer_mappings": "每个元素需包含 layer_id, layer_name, layer_tag"},
    },
    "secondary_parse": {
        "required": ["record_id", "layer_mappings"],
        "optional": [],
        "types": {"record_id": "记录ID", "layer_mappings": "图层映射列表"},
    },
    "recognition": {
        "required": ["record_id", "decks"],
        "optional": [],
        "types": {"record_id": "记录ID", "decks": "甲板列表 [{'deck_id','deck_name','deck_height'}]"},
    },

    # ═══════════════════════════════
    # 编辑模式
    # ═══════════════════════════════
    "edit_mode_start": {
        "required": ["record_id", "type"],
        "optional": [],
        "types": {"record_id": "记录ID", "type": "int: 0(舱室编辑) / 1(元件编辑)"},
        "enums": {"type": [0, 1]},
    },
    "edit_mode_exit": {
        "required": ["record_id", "type"],
        "optional": ["is_save"],
        "types": {"record_id": "记录ID", "type": "int: 0/1", "is_save": "bool: 是否保存"},
    },

    # ═══════════════════════════════
    # 甲板
    # ═══════════════════════════════
    "get_decks": {
        "required": ["record_id"],
        "optional": [],
        "types": {"record_id": "记录ID"},
    },
    "search_deck": {
        "required": ["record_id", "system_type", "keyword"],
        "optional": ["deck_id"],
        "types": {"record_id": "记录ID", "system_type": "primary|secondary|lighting", "keyword": "搜索关键词", "deck_id": "甲板ID(可选，缩小范围)"},
        "enums": {"system_type": ["primary", "secondary", "lighting"]},
        "hints": {"system_type": "primary=一次系统, secondary=二次系统, lighting=照明系统"},
    },
    "update_deck": {
        "required": ["record_id", "deck_id"],
        "optional": ["deck_height", "deck_name"],
        "types": {"record_id": "记录ID", "deck_id": "甲板ID", "deck_height": "甲板高度(米)", "deck_name": "甲板名称"},
    },

    # ═══════════════════════════════
    # 舱室
    # ═══════════════════════════════
    "get_compartments": {
        "required": ["record_id", "deck_id"],
        "optional": [],
        "types": {"record_id": "记录ID", "deck_id": "甲板ID"},
    },
    "get_compartment_detail": {
        "required": ["record_id", "deck_id", "compartment_id"],
        "optional": [],
        "types": {"record_id": "记录ID", "deck_id": "甲板ID", "compartment_id": "舱室ID"},
    },
    "create_compartment": {
        "required": ["record_id", "deck_id", "points"],
        "optional": [],
        "types": {"record_id": "记录ID", "deck_id": "甲板ID", "points": "坐标点列表 [[x,y],...]"},
    },
    "update_compartment": {
        "required": ["record_id", "deck_id", "compartment_id"],
        "optional": ["compartment_name", "compartment_function", "points"],
        "types": {"record_id": "记录ID", "deck_id": "甲板ID", "compartment_id": "舱室ID", "compartment_name": "新舱室名", "compartment_function": "功能区", "points": "新坐标"},
    },
    "delete_compartment": {
        "required": ["record_id", "deck_id", "compartment_id"],
        "optional": [],
        "types": {"record_id": "记录ID", "deck_id": "甲板ID", "compartment_id": "舱室ID"},
    },

    # ═══════════════════════════════
    # 主配电板
    # ═══════════════════════════════
    "get_main_switchboards": {
        "required": ["record_id", "deck_id"],
        "optional": ["compartment_id"],
        "types": {"record_id": "记录ID", "deck_id": "甲板ID", "compartment_id": "舱室ID(可选)"},
    },
    "get_main_switchboard_detail": {
        "required": ["record_id", "msb_id"],
        "optional": [],
        "types": {"record_id": "记录ID", "msb_id": "主配电板ID"},
    },
    "get_main_switchboard_connected": {
        "required": ["record_id", "msb_id"],
        "optional": [],
        "types": {"record_id": "记录ID", "msb_id": "主配电板ID"},
    },

    # ═══════════════════════════════
    # 分配电箱
    # ═══════════════════════════════
    "get_distribution_boards": {
        "required": ["record_id", "deck_id"],
        "optional": ["compartment_id"],
        "types": {"record_id": "记录ID", "deck_id": "甲板ID", "compartment_id": "舱室ID(可选)"},
    },
    "get_distribution_board_detail": {
        "required": ["record_id", "db_id"],
        "optional": [],
        "types": {"record_id": "记录ID", "db_id": "分配电箱ID"},
    },
    "get_distribution_board_connected": {
        "required": ["record_id", "db_id"],
        "optional": [],
        "types": {"record_id": "记录ID", "db_id": "分配电箱ID"},
    },

    # ═══════════════════════════════
    # 负载
    # ═══════════════════════════════
    "get_loads": {
        "required": ["record_id", "deck_id"],
        "optional": ["compartment_id"],
        "types": {"record_id": "记录ID", "deck_id": "甲板ID", "compartment_id": "舱室ID(可选)"},
    },
    "get_load_detail": {
        "required": ["record_id", "load_id"],
        "optional": [],
        "types": {"record_id": "记录ID", "load_id": "负载ID"},
    },
    "get_loads_with_detail": {
        "required": ["record_id", "deck_id"],
        "optional": ["compartment_id"],
        "types": {"record_id": "记录ID", "deck_id": "甲板ID", "compartment_id": "舱室ID(可选)"},
    },
    "update_load": {
        "required": ["record_id", "load_id"],
        "optional": ["load_name", "type", "compartment_id", "supply_equipment_id", "rated_power", "power_factor"],
        "types": {"record_id": "记录ID", "load_id": "负载ID", "load_name": "负载名", "type": "负载类型", "compartment_id": "所属舱室", "supply_equipment_id": "供电设备ID", "rated_power": "额定功率(kW)", "power_factor": "功率因数"},
    },

    # ═══════════════════════════════
    # 灯具
    # ═══════════════════════════════
    "get_light_types": {
        "required": ["record_id"],
        "optional": [],
    },
    "get_lights": {
        "required": ["record_id", "deck_id"],
        "optional": ["compartment_id"],
        "types": {"record_id": "记录ID", "deck_id": "甲板ID", "compartment_id": "舱室ID(可选)"},
    },
    "get_light_detail": {
        "required": ["record_id", "light_id"],
        "optional": [],
        "types": {"record_id": "记录ID", "light_id": "灯具ID"},
    },
    "update_light": {
        "required": ["record_id", "light_id"],
        "optional": ["light_name", "compartment_id", "light_type_id", "points"],
        "types": {"record_id": "记录ID", "light_id": "灯具ID", "light_name": "灯具名", "compartment_id": "所在舱室", "light_type_id": "灯具类型ID", "points": "位置坐标 [x,y]"},
    },
    "delete_lights": {
        "required": ["record_id", "light_ids"],
        "optional": [],
        "types": {"record_id": "记录ID", "light_ids": "灯具ID列表 [\"id1\",\"id2\"]"},
    },
    "recommend_light_count": {
        "required": ["record_id", "compartment_id", "light_type_id"],
        "optional": ["illuminance", "utilization", "maintenance"],
        "types": {"record_id": "记录ID", "compartment_id": "舱室ID", "light_type_id": "灯具类型ID", "illuminance": "需求照度(lx,默认200)", "utilization": "照明率(默认0.8)", "maintenance": "保持率(默认1.0)"},
    },
    "layout_lights": {
        "required": ["record_id", "compartment_id", "light_type_count", "layout_type"],
        "optional": [],
        "types": {"record_id": "记录ID", "compartment_id": "舱室ID", "light_type_count": "灯具类型数量列表 [{\"light_type_id\",\"count\"}]", "layout_type": "布局方式"},
        "enums": {"layout_type": ["one_click", "uniform", "lane_beam"]},
        "hints": {"layout_type": "one_click=一键部署, uniform=均匀布局, lane_beam=绕梁布灯"},
    },
    "verify_illuminance": {
        "required": ["record_id", "compartment_id", "light_type_count"],
        "optional": ["illuminance", "utilization", "maintenance"],
        "types": {"record_id": "记录ID", "compartment_id": "舱室ID", "light_type_count": "灯具类型数量列表", "illuminance": "需求照度(默认200)", "utilization": "照明率(默认0.8)", "maintenance": "保持率(默认1.0)"},
    },
    "update_lights_layout": {
        "required": ["record_id", "compartment_id", "lights_points"],
        "optional": [],
        "types": {"record_id": "记录ID", "compartment_id": "舱室ID", "lights_points": "灯具坐标列表 [{\"light_id\",\"points\"}]"},
    },

    # ═══════════════════════════════
    # 梁线
    # ═══════════════════════════════
    "get_beam_lines": {
        "required": ["record_id", "deck_id"],
        "optional": ["compartment_id"],
    },
    "get_beam_line_detail": {
        "required": ["record_id", "beam_line_id"],
        "optional": [],
    },
    "create_beam_line": {
        "required": ["record_id", "deck_id", "points"],
        "optional": [],
    },
    "update_beam_line": {
        "required": ["record_id", "beam_line_id"],
        "optional": ["beam_line_name", "length", "width", "points"],
    },
    "delete_beam_line": {
        "required": ["record_id", "beam_line_id"],
        "optional": [],
    },

    # ═══════════════════════════════
    # 车道线
    # ═══════════════════════════════
    "get_lane_lines": {
        "required": ["record_id", "deck_id"],
        "optional": ["compartment_id"],
    },
    "get_lane_line_detail": {
        "required": ["record_id", "lane_line_id"],
        "optional": [],
    },
    "create_lane_line": {
        "required": ["record_id", "deck_id", "points"],
        "optional": [],
    },
    "update_lane_line": {
        "required": ["record_id", "lane_line_id"],
        "optional": ["lane_line_name", "length", "width", "points"],
    },
    "delete_lane_line": {
        "required": ["record_id", "lane_line_id"],
        "optional": [],
    },

    # ═══════════════════════════════
    # 接线盒
    # ═══════════════════════════════
    "get_junction_boxes": {
        "required": ["record_id", "deck_id"],
        "optional": [],
    },
    "create_junction_box": {
        "required": ["record_id", "deck_id", "db_id"],
        "optional": [],
    },

    # ═══════════════════════════════
    # 绑定
    # ═══════════════════════════════
    "get_unbound_compartment": {
        "required": ["record_id", "system_type"],
        "optional": [],
        "enums": {"system_type": ["primary", "secondary"]},
    },
    "get_unbound_power": {
        "required": ["record_id", "deck_id", "system_type"],
        "optional": ["compartment_id"],
        "enums": {"system_type": ["primary", "secondary"]},
    },
    "bind_compartment": {
        "required": ["record_id", "deck_id", "compartment_id", "unbound_loads"],
        "optional": [],
        "types": {"record_id": "记录ID", "deck_id": "甲板ID", "compartment_id": "舱室ID", "unbound_loads": "负载ID列表 [\"id1\",\"id2\"]"},
    },
    "unbind_compartment": {
        "required": ["record_id", "unbound_loads"],
        "optional": [],
    },
    "bind_power": {
        "required": ["record_id", "supply_equipment_id", "unbound_loads"],
        "optional": [],
    },
    "unbind_power": {
        "required": ["record_id", "unbound_loads"],
        "optional": [],
    },

    # ═══════════════════════════════
    # 导入记录
    # ═══════════════════════════════
    "get_records": {
        "required": [],
        "optional": [],
    },
    "get_record_snapshot": {
        "required": ["record_id"],
        "optional": [],
    },

    # ═══════════════════════════════
    # 画布渲染
    # ═══════════════════════════════
    "get_canvas_all": {
        "required": ["record_id"],
        "optional": ["system_type"],
        "enums": {"system_type": ["primary", "secondary", "lighting"]},
    },

    # ═══════════════════════════════
    # 测量工具
    # ═══════════════════════════════
    "measure_point": {
        "required": ["record_id", "deck_id", "start_point", "end_point"],
        "optional": [],
        "types": {"start_point": "[x, y] 起点坐标", "end_point": "[x, y] 终点坐标"},
    },
    "measure_compartment": {
        "required": ["record_id", "start_deck_id", "start_compartment_id", "end_deck_id", "end_compartment_id"],
        "optional": [],
    },

    # ═══════════════════════════════
    # 组合查询
    # ═══════════════════════════════
    "get_all_compartments": {
        "required": [],
        "optional": ["record_id"],
    },
    "get_compartment_info": {
        "required": ["compartment_name"],
        "optional": ["record_id"],
    },
    "get_system_status": {
        "required": [],
        "optional": ["record_id"],
    },
}

# ──────────────────────────────────────────────
# 旧工具名 → 新 API 工具名映射（向后兼容）
# ──────────────────────────────────────────────
OLD_TO_NEW = {
    # 查询类
    "query_import_info": "get_records",
    "query_compartment_info": "get_compartment_info",
    "query_bound_loads_overview": "get_unbound_compartment",
    "query_load_topology": "get_main_switchboard_connected",
    "query_unbound_loads": "get_unbound_power",
    "query_unbound_load_detail": "get_load_detail",
    "query_load_supply_info": "get_load_detail",
    "query_current_system_status": "get_system_status",
    "query_process_log": "get_records",
    "query_light_library_count": "get_light_types",
    "query_layouted_compartments": "get_all_compartments",
    "query_compartment_layout_detail": "get_compartment_detail",
    "query_compartment_layout_type": "get_compartment_detail",
    "query_compartment_light_topology": "get_compartment_detail",
    "query_unlayouted_compartments": "get_all_compartments",
    "query_compartment_distance": "measure_compartment",
    # 操作类
    "modify_compartment_info": "update_compartment",
    "delete_compartment": "delete_compartment",
    "batch_bind_compartment": "bind_compartment",
    "batch_bind_distribution": "bind_power",
    "modify_load_binding": "update_load",
    "bind_unbound_load": "bind_power",
    "refresh_loads": "get_records",
    "switch_mode": "edit_mode_start",
    "calculate_lamp_count": "recommend_light_count",
    "check_illuminance": "verify_illuminance",
    "auto_layout": "layout_lights",
    "save_drawing": "update_lights_layout",
    # 画布
    "compartment_full_query": "get_canvas_all",
    "load_full_query": "get_load_detail",
    "full_illumination_design": "layout_lights",
}


def _str_param_val(v):
    """将参数值转为可读字符串（用于提示信息）"""
    if isinstance(v, list):
        return f"[{len(v)} 项]"
    if isinstance(v, dict):
        return "{" + ", ".join(f"{k}:{v[k]}" for k in list(v.keys())[:3]) + ("..." if len(v) > 3 else "") + "}"
    return str(v)


def get_tool_name(tool: str) -> str:
    """解析工具名：支持旧名和新名，返回标准化的 API 工具名"""
    if tool in TOOL_RULES:
        return tool
    if tool in OLD_TO_NEW:
        return OLD_TO_NEW[tool]
    return tool  # 不认识的也传过去，让调用层报错


def validate(tool: str, params: dict) -> dict:
    """
    校验参数。返回 dict:
      - 成功: {"valid": True, "tool": tool, "params": params}
      - 失败: {"valid": False, "tool": tool, "missing": [...], "hint": str, ...}
    """
    api_tool = get_tool_name(tool)
    rules = TOOL_RULES.get(api_tool)

    if not rules:
        return {
            "valid": True,
            "tool": tool,
            "api_tool": api_tool,
            "params": params,
            "_note": f"无校验规则: {api_tool}，直接传递",
        }

    required = rules.get("required", [])
    optional = rules.get("optional", [])
    enums = rules.get("enums", {})
    types = rules.get("types", {})
    hints = rules.get("hints", {})

    # 1. 检查必填参数
    missing = []
    missing_hints = []
    for k in required:
        if k not in params or params[k] is None or params[k] == "" or params[k] == []:
            missing.append(k)
            hint = hints.get(k, types.get(k, ""))
            if hint:
                missing_hints.append(f"  · {k} — {hint}")
            else:
                missing_hints.append(f"  · {k}")

    if missing:
        result = {
            "valid": False,
            "tool": tool,
            "api_tool": api_tool,
            "missing": missing,
            "missing_hints": missing_hints,
            "hint": f"缺少必填参数: {', '.join(missing)}",
            "param_details": {k: types.get(k, "") for k in missing},
        }

        # 动态获取可选值（默认 record_id 自动补）
        if "record_id" in missing:
            result["default_record_id"] = "ed18461b23884c568e2366c228378825"
            result["hint"] += "\n提示：record_id 可默认使用 ed18461b23884c569e2366c228378825"

        return result

    # 2. 检查枚举值合法性
    invalid_enums = {}
    for k, valid_values in enums.items():
        if k in params and params[k] is not None:
            # 对 int 枚举做类型处理
            if all(isinstance(v, int) for v in valid_values):
                try:
                    val = int(params[k]) if not isinstance(params[k], int) else params[k]
                    if val not in valid_values:
                        invalid_enums[k] = {"given": params[k], "valid": valid_values}
                except (ValueError, TypeError):
                    invalid_enums[k] = {"given": params[k], "valid": valid_values}
            elif params[k] not in valid_values:
                invalid_enums[k] = {"given": params[k], "valid": valid_values}

    if invalid_enums:
        return {
            "valid": False,
            "tool": tool,
            "api_tool": api_tool,
            "error_type": "invalid_enum",
            "invalid_params": invalid_enums,
            "hint": "参数值不在有效范围内: " + "; ".join(
                f"{k}={v['given']}，允许值: {v['valid']}" for k, v in invalid_enums.items()
            ),
        }

    # 3. 检查不认识的参数（给出提示）
    all_known = set(required + optional)
    unknown = [k for k in params if k not in all_known and k != "record_id"]
    unknown_note = ""
    if unknown:
        unknown_note = f"\n注意：以下参数不在已知列表中: {', '.join(unknown)}"

    return {
        "valid": True,
        "tool": tool,
        "api_tool": api_tool,
        "params": {k: v for k, v in params.items() if k in all_known or k == "record_id"},
        "_note": unknown_note if unknown_note else None,
    }


def get_tool_help(tool: str) -> dict:
    """获取工具的详细帮助信息（参数说明）"""
    api_tool = get_tool_name(tool)
    rules = TOOL_RULES.get(api_tool)
    if not rules:
        return {"error": f"未知工具: {tool}", "hint": "请检查工具名称"}

    return {
        "tool": tool,
        "api_tool": api_tool,
        "required": rules.get("required", []),
        "optional": rules.get("optional", []),
        "types": rules.get("types", {}),
        "enums": rules.get("enums", {}),
        "hints": rules.get("hints", {}),
    }


def list_tools() -> dict:
    """列出所有可用工具"""
    return {
        "count": len(TOOL_RULES),
        "tools": sorted(TOOL_RULES.keys()),
    }


# ──────────────────────────────────────────────
# CLI 入口（供调试）
# ──────────────────────────────────────────────
if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="参数校验工具")
    parser.add_argument("--tool", required=True, help="工具名称")
    parser.add_argument("--params", default="{}", help="参数字符串")
    parser.add_argument("--tool-help", action="store_true", dest="show_help", help="显示工具参数说明")
    args = parser.parse_args()

    if args.show_help:
        result = get_tool_help(args.tool)
    else:
        params = json.loads(args.params)
        result = validate(args.tool, params)

    print(json.dumps(result, ensure_ascii=False, indent=2))
