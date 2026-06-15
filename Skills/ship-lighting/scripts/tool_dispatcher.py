#!/usr/bin/env python3
"""
tool_dispatcher.py — 统一工具调度器 v4.0（基于 HTTP API）

工作流：
  LLM(你) → 意图识别 → 参数提取 → tool_dispatcher
    → param_validator (校验) → api_client (HTTP API) → JSON 返回
    → 校验失败 → 结构化错误提示

用法：
  python3 tool_dispatcher.py --tool <name> --params '<json>'
  python3 tool_dispatcher.py --list
  python3 tool_dispatcher.py --tool get_decks --params '{}'
  python3 tool_dispatcher.py --tool get_compartments --params '{"deck_id":"DECK 4"}'
"""

import sys
import json
import argparse
import os
from pathlib import Path

SCRIPTS_DIR = Path(__file__).parent
sys.path.insert(0, str(SCRIPTS_DIR))

import param_validator
import api_client

# ──────────────────────────────────────────────
# API 函数映射表：工具名 → (api_client 函数, 描述)
# ──────────────────────────────────────────────

def _fn(name):
    """获取 api_client 模块中的函数"""
    return getattr(api_client, name, None)

API_MAP = {
    # 图纸解析
    "primary_parse":                (_fn("primary_parse"), "一次解析：上传图纸并提取图层"),
    "submit_preview":               (_fn("submit_preview"), "提交图层映射，触发预览"),
    "secondary_parse":              (_fn("secondary_parse"), "二次解析：切分图纸提取甲板"),
    "recognition":                  (_fn("recognition"), "完成导入：识别舱室/负载"),

    # 编辑模式
    "edit_mode_start":              (_fn("edit_mode_start"), "开始编辑模式"),
    "edit_mode_exit":               (_fn("edit_mode_exit"), "结束编辑模式"),

    # 甲板
    "get_decks":                    (_fn("get_decks"), "查询甲板列表"),
    "search_deck":                  (_fn("search_deck"), "关键字搜索甲板元件"),
    "update_deck":                  (_fn("update_deck"), "编辑甲板信息"),

    # 舱室
    "get_compartments":             (_fn("get_compartments"), "查询舱室列表"),
    "get_compartment_detail":       (_fn("get_compartment_detail"), "查询舱室详情"),
    "create_compartment":           (_fn("create_compartment"), "新增舱室"),
    "update_compartment":           (_fn("update_compartment"), "编辑舱室"),
    "delete_compartment":           (_fn("delete_compartment"), "删除舱室"),

    # 主配电板
    "get_main_switchboards":        (_fn("get_main_switchboards"), "查询主配电板列表"),
    "get_main_switchboard_detail":  (_fn("get_main_switchboard_detail"), "查询主配电板详情"),
    "get_main_switchboard_connected": (_fn("get_main_switchboard_connected"), "查询主配电板关联元件"),

    # 分配电箱
    "get_distribution_boards":      (_fn("get_distribution_boards"), "查询分配电箱列表"),
    "get_distribution_board_detail":(_fn("get_distribution_board_detail"), "查询分配电箱详情"),
    "get_distribution_board_connected": (_fn("get_distribution_board_connected"), "查询分配电箱关联元件"),

    # 负载
    "get_loads":                    (_fn("get_loads"), "查询负载列表"),
    "get_load_detail":              (_fn("get_load_detail"), "查询负载详情"),
    "get_loads_with_detail":        (_fn("get_loads_with_detail"), "组合查询：查负载列表+逐条详情"),
    "update_load":                  (_fn("update_load"), "编辑负载"),

    # 灯具
    "get_light_types":              (_fn("get_light_types"), "查询灯具类型列表"),
    "get_lights":                   (_fn("get_lights"), "查询灯具列表"),
    "get_light_detail":             (_fn("get_light_detail"), "查询灯具详情"),
    "update_light":                 (_fn("update_light"), "编辑灯具"),
    "delete_lights":                (_fn("delete_lights"), "批量删除灯具"),
    "recommend_light_count":        (_fn("recommend_light_count"), "灯具数量推荐"),
    "layout_lights":                (_fn("layout_lights"), "灯具布局"),
    "verify_illuminance":           (_fn("verify_illuminance"), "灯具验算照度"),
    "update_lights_layout":         (_fn("update_lights_layout"), "灯具布局坐标更新"),

    # 梁线
    "get_beam_lines":               (_fn("get_beam_lines"), "查询梁线列表"),
    "get_beam_line_detail":         (_fn("get_beam_line_detail"), "查询梁线详情"),
    "create_beam_line":             (_fn("create_beam_line"), "新增梁线"),
    "update_beam_line":             (_fn("update_beam_line"), "编辑梁线"),
    "delete_beam_line":             (_fn("delete_beam_line"), "删除梁线"),

    # 车道线
    "get_lane_lines":               (_fn("get_lane_lines"), "查询车道线列表"),
    "get_lane_line_detail":         (_fn("get_lane_line_detail"), "查询车道线详情"),
    "create_lane_line":             (_fn("create_lane_line"), "新增车道线"),
    "update_lane_line":             (_fn("update_lane_line"), "编辑车道线"),
    "delete_lane_line":             (_fn("delete_lane_line"), "删除车道线"),

    # 接线盒
    "get_junction_boxes":           (_fn("get_junction_boxes"), "查询接线盒列表"),
    "create_junction_box":          (_fn("create_junction_box"), "新建接线盒"),

    # 绑定
    "get_unbound_compartment":      (_fn("get_unbound_compartment"), "查询未绑定舱室的负载"),
    "get_unbound_power":            (_fn("get_unbound_power"), "查询未绑定配电的负载"),
    "bind_compartment":             (_fn("bind_compartment"), "绑定负载到舱室"),
    "unbind_compartment":           (_fn("unbind_compartment"), "从舱室解绑负载"),
    "bind_power":                   (_fn("bind_power"), "绑定负载到供电设备"),
    "unbind_power":                 (_fn("unbind_power"), "从供电设备解绑负载"),

    # 导入记录
    "get_records":                  (_fn("get_records"), "查询导入记录"),
    "get_record_snapshot":          (_fn("get_record_snapshot"), "查询记录回溯"),

    # 画布
    "get_canvas_all":                (_fn("get_canvas_all"), "获取画布完整数据"),

    # 测量
    "measure_point":                (_fn("measure_point"), "点距测量"),
    "measure_compartment":          (_fn("measure_compartment"), "舱室距离测量"),

    # 组合查询
    "get_all_compartments":         (_fn("get_all_compartments"), "获取所有甲板全部舱室"),
    "get_compartment_info":         (_fn("get_compartment_info"), "按名称查找舱室"),
    "get_system_status":            (_fn("get_system_status"), "获取系统状态"),
}

# ──────────────────────────────────────────────
# 组合工具（Pipeline）：串联多个 API 调用
# ──────────────────────────────────────────────

COMPOSITE_MAP = {
    "full_illumination_design": {
        "description": "完整照明设计：灯具数量推荐 → 照度验算 → 灯具布局",
        "pipeline": [
            "recommend_light_count",
            "verify_illuminance",
            "layout_lights",
        ],
        "params": {
            "compartment_id": "舱室id",
            "light_type_id": "灯具类型id",
            "illuminance": "需求照度(lx)",
            "utilization": "照明率",
            "maintenance": "保持率",
            "layout_type": "布局方式(one_click/uniform/lane_beam)",
        },
    },
}


# ──────────────────────────────────────────────
# 主要路由
# ──────────────────────────────────────────────

def run_tool(tool: str, params: dict) -> dict:
    """执行工具：校验 → API 调用 → 返回结果"""

    # Step 0: bind server-trusted EID context. Public tool arguments must not
    # contain record_id because the model/browser is not an authority for it.
    context_error = _bind_trusted_eid_context(tool, params)
    if context_error:
        return context_error

    # Step 1: 检查是否为组合工具
    if tool in COMPOSITE_MAP:
        return run_composite(tool, params)

    # Step 2: 标准化工具名
    api_tool = param_validator.get_tool_name(tool)

    # Step 2: 参数校验
    validation = param_validator.validate(tool, params)
    if not validation["valid"]:
        return _build_validation_error(tool, validation)

    # Step 3: 查找 API 函数
    api_func_info = API_MAP.get(api_tool)
    if not api_func_info:
        # 尝试直接查找旧名
        api_func_info = API_MAP.get(tool)
    if not api_func_info:
        return {
            "tool": tool,
            "error": f"未知工具: {api_tool}",
            "hint": "使用 --list 查看所有可用工具",
            "status": "error",
        }

    api_func, description = api_func_info
    if api_func is None:
        return {
            "tool": tool,
            "error": f"工具 {api_tool} 的 API 函数未实现",
            "status": "error",
        }

    # Step 4: 调用 API
    try:
        clean_params = validation.get("params", params)
        result = api_func(**clean_params)
    except TypeError as e:
        return {
            "tool": tool,
            "error": f"API 调用参数错误: {e}",
            "hint": f"工具 {api_tool} 期望的参数: {_get_api_params(api_func)}",
            "status": "error",
        }
    except Exception as e:
        return {
            "tool": tool,
            "error": f"API 调用异常: {e}",
            "status": "error",
        }

    # Step 5: 格式化返回
    # Step 5: 格式化返回
    return {
        "tool": tool,
        "api_tool": api_tool,
        "status": "success" if not (isinstance(result, dict) and "_error" in result) else "error",
        "data": result,
        "description": description,
    }


# ──────────────────────────────────────────────
# 组合工具执行
# ──────────────────────────────────────────────

def run_composite(tool: str, params: dict) -> dict:
    """执行组合工具（串联多个 API 调用）"""
    definition = COMPOSITE_MAP.get(tool)
    if not definition:
        return {"tool": tool, "error": f"未定义组合工具: {tool}", "status": "error"}

    pipeline = definition["pipeline"]
    steps = []
    context = dict(params)  # 拷贝参数，每步可以修改

    for step_name in pipeline:
        api_func_info = API_MAP.get(step_name)
        if not api_func_info:
            steps.append({"step": step_name, "error": f"API 函数未注册: {step_name}"})
            break

        api_func, desc = api_func_info
        if api_func is None:
            steps.append({"step": step_name, "error": "API 函数未实现"})
            break

        # 为当前步骤准备参数
        step_params = _prepare_composite_params(step_name, context)

        try:
            result = api_func(**step_params)
        except Exception as e:
            steps.append({"step": step_name, "error": str(e), "params_used": step_params})
            break

        steps.append({"step": step_name, "result": result, "description": desc})

        # 检查错误
        if isinstance(result, dict) and "_error" in result:
            steps[-1]["error"] = result["_error"]
            break

        # 将上一步结果注入 context，供后续步骤使用
        if isinstance(result, dict):
            if "count" in result:
                context["_recommended_count"] = result["count"]
            if "lights_points" in result:
                context["_lights_points"] = result["lights_points"]
            if "cal_illuminance" in result:
                context["_cal_illuminance"] = result["cal_illuminance"]

    status = "completed" if len(steps) == len(pipeline) else "partial"
    return {
        "tool": tool,
        "description": definition.get("description", ""),
        "pipeline": pipeline,
        "status": status,
        "steps": steps,
        "final_output": steps[-1]["result"] if steps and "error" not in steps[-1] else None,
    }


def _prepare_composite_params(step_name: str, context: dict) -> dict:
    """为组合工具中的每一步准备参数（只传当前步骤需要的字段）"""
    params = {
        "record_id": context.get("record_id"),
    }

    if step_name == "recommend_light_count":
        # 只需要灯具推荐相关参数
        for k in ["compartment_id", "light_type_id", "illuminance",
                  "utilization", "maintenance"]:
            if k in context:
                params[k] = context[k]

    elif step_name == "verify_illuminance":
        # 需要 light_type_count（从上一步的推荐数量构建）
        for k in ["compartment_id", "illuminance", "utilization", "maintenance"]:
            if k in context:
                params[k] = context[k]
        if "_recommended_count" in context:
            params["light_type_count"] = [
                {"light_type_id": context.get("light_type_id", ""),
                 "count": context["_recommended_count"]}
            ]

    elif step_name == "layout_lights":
        # 需要 light_type_count + layout_type
        params["compartment_id"] = context.get("compartment_id")
        if "_recommended_count" in context:
            params["light_type_count"] = [
                {"light_type_id": context.get("light_type_id", ""),
                 "count": context["_recommended_count"]}
            ]
        params["layout_type"] = context.get("layout_type", "uniform")

    return params


def _build_validation_error(tool: str, validation: dict) -> dict:
    """构建参数校验失败的结构化错误响应"""
    missing = validation.get("missing", [])
    missing_hints = validation.get("missing_hints", [])
    result = {
        "tool": tool,
        "status": "validation_error",
        "message": validation.get("hint", "参数校验失败"),
    }

    if missing:
        result["missing"] = missing
        result["missing_details"] = missing_hints

    if "invalid_params" in validation:
        result["invalid_params"] = validation["invalid_params"]

    # 对常见缺失参数，附带可用的可选值提示
    if "deck_id" in missing or "deck" in str(missing).lower():
        try:
            decks = api_client.get_decks(os.environ["HERMES_EID_RECORD_ID"])
            if isinstance(decks, list) and decks:
                result["available_decks"] = [
                    {"deck_id": d["deck_id"], "deck_name": d.get("deck_name", d["deck_id"]),
                     "deck_height": d.get("deck_height")} for d in decks
                ]
        except Exception:
            pass

    return result


def _bind_trusted_eid_context(tool: str, params: dict) -> dict | None:
    """Inject the authorized session record and reject caller-controlled IDs."""
    protected = sorted({
        "record_id", "user_id", "eid_subject", "eid_tenant",
        "delegation_token",
    }.intersection(params))
    if protected:
        return {
            "tool": tool,
            "status": "context_error",
            "error_type": "caller_supplied_eid_context",
            "protected_params": protected,
            "message": "EID 用户与 record 上下文由 Hermes 服务端绑定，工具参数不得提供或覆盖",
        }

    subject = os.environ.get("HERMES_EID_SUBJECT", "").strip()
    if not subject:
        return {
            "tool": tool,
            "status": "context_error",
            "error_type": "missing_eid_identity",
            "message": "当前没有可信的 EID 登录上下文，请重新登录后再试",
        }

    record_id = os.environ.get("HERMES_EID_RECORD_ID", "").strip()
    if not record_id:
        return {
            "tool": tool,
            "status": "context_error",
            "error_type": "missing_record_context",
            "message": "当前会话未绑定 EID 记录，请先打开或选择记录",
        }

    delegation = os.environ.get("HERMES_EID_DELEGATION", "").strip()
    development_mode = os.environ.get(
        "HERMES_WEBUI_EID_DEVELOPMENT_MODE", ""
    ).strip().lower() in {"1", "true", "yes", "on"}
    if not delegation and not development_mode:
        return {
            "tool": tool,
            "status": "context_error",
            "error_type": "missing_eid_delegation",
            "message": "当前运行后端未提供 EID 委托令牌，已拒绝业务工具调用",
        }

    api_tool = param_validator.get_tool_name(tool)
    rules = param_validator.TOOL_RULES.get(api_tool, {})
    fields = rules.get("required", []) + rules.get("optional", [])
    if tool in COMPOSITE_MAP or "record_id" in fields:
        params["record_id"] = record_id
    return None


def _get_api_params(func) -> str:
    """获取函数的参数签名"""
    import inspect
    sig = inspect.signature(func)
    params = []
    for name, param in sig.parameters.items():
        if param.default is inspect.Parameter.empty:
            params.append(name)
        else:
            params.append(f"{name}(可选)")
    return ", ".join(params)


def list_tools() -> dict:
    """列出所有可用工具"""
    tools = []
    for name, (fn, desc) in sorted(API_MAP.items()):
        if fn:
            tools.append({
                "name": name,
                "description": desc,
                "params": param_validator.get_tool_help(name),
                "type": "atomic",
            })

    for name, defn in sorted(COMPOSITE_MAP.items()):
        tools.append({
            "name": name,
            "description": defn.get("description", ""),
            "pipeline": defn.get("pipeline", []),
            "params": defn.get("params", {}),
            "type": "composite",
        })

    return {
        "total": len(tools),
        "tools": tools,
    }


# ──────────────────────────────────────────────
# 写操作确认机制
# ──────────────────────────────────────────────

WRITE_TOOLS = frozenset({
    # 编辑/写操作工具（修改数据库）
    "update_deck", "create_compartment", "update_compartment",
    "delete_compartment", "update_load", "update_light",
    "delete_lights", "layout_lights", "update_lights_layout",
    "unbind_compartment", "bind_compartment", "unbind_power",
    "bind_power", "create_beam_line", "update_beam_line",
    "delete_beam_line", "create_lane_line", "update_lane_line",
    "delete_lane_line", "create_junction_box",
    "edit_mode_start", "edit_mode_exit",
    "primary_parse", "submit_preview", "secondary_parse", "recognition",
})


def _is_write_tool(tool: str) -> bool:
    """判断工具是否为写操作（修改数据库）"""
    # 检查是否为组合工具（内部含有写操作步骤）
    if tool in COMPOSITE_MAP:
        steps = COMPOSITE_MAP[tool]["pipeline"]
        return any(s in WRITE_TOOLS for s in steps)
    return tool in WRITE_TOOLS


def _prompt_confirm(tool: str, params: dict) -> None:
    """在终端输出操作摘要并等待用户确认"""
    import sys

    # 构建操作摘要
    lines = [
        "",
        "=" * 56,
        "  ⚠️  即将执行数据库写入操作",
        "=" * 56,
        f"  工具: {tool}",
    ]

    # 工具中文描述
    api_info = API_MAP.get(tool)
    if api_info:
        lines.append(f"  说明: {api_info[1]}")

    # 关键参数摘要
    lines.append(f"  参数:")
    for key, val in params.items():
        v = json.dumps(val, ensure_ascii=False) if isinstance(val, (list, dict)) else str(val)
        if len(v) > 60:
            v = v[:57] + "..."
        lines.append(f"    {key}: {v}")

    lines.extend([
        "-" * 56,
        "  确认执行？(y/N): ",
    ])

    # 追加写入（不换行，方便 input 在同一行）
    print("\n".join(lines), end="")
    sys.stdout.flush()

    answer = sys.stdin.readline().strip().lower()
    if answer not in ("y", "yes"):
        print("  操作已取消。")
        sys.exit(0)
    print("  操作已确认，继续执行...\n")


def main():
    parser = argparse.ArgumentParser(
        description="船舶照明工具统一调度器 v4.0 (HTTP API)",
        epilog="LLM 负责意图路由+参数提取，本调度器负责校验+API调用"
    )
    parser.add_argument("--tool", type=str, required=False, help="工具名称")
    parser.add_argument("--params", type=str, default="{}", help="参数 JSON 字符串")
    parser.add_argument("--list", action="store_true", help="列出所有可用工具")
    parser.add_argument("--validate-only", action="store_true", help="仅校验参数，不调用 API")
    parser.add_argument("--confirm", action="store_true", help="写操作前要求终端确认")
    args = parser.parse_args()

    if not args.list and not args.tool:
        parser.error("请提供 --tool 或 --list")

    if args.list:
        result = list_tools()
    else:
        params = json.loads(args.params)
        api_tool = param_validator.get_tool_name(args.tool)

        # --confirm: 写操作前要求用户确认
        if args.confirm and _is_write_tool(args.tool):
            context_error = _bind_trusted_eid_context(args.tool, dict(params))
            if context_error:
                print(json.dumps(context_error, ensure_ascii=False, indent=2))
                return
            _prompt_confirm(args.tool, params)

        if args.validate_only:
            context_error = _bind_trusted_eid_context(args.tool, params)
            result = context_error or param_validator.validate(args.tool, params)
            if not context_error and result.get("valid"):
                result["params"].pop("record_id", None)
        else:
            result = run_tool(args.tool, params)

    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
