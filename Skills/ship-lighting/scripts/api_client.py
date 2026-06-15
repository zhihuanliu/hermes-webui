#!/usr/bin/env python3
"""
api_client.py — 完整 HTTP API 客户端（v4.0）
对接全部后端 API 接口，无 PostgreSQL 依赖。

Base URL: http://192.168.208.23:5000/api/v1
"""

import json
import os
import urllib.request
import urllib.error
import urllib.parse
from pathlib import Path

API_BASE = os.environ.get(
    "SHIP_LIGHTING_API_BASE",
    "http://192.168.208.23:5000/api/v1",
).rstrip("/")


# ═══════════════════════════════════════════════
# 通用 HTTP 方法
# ═══════════════════════════════════════════════

def _request(method: str, endpoint: str, params: dict = None, data: dict = None,
             files: dict = None) -> dict:
    """通用 HTTP 请求"""
    url = f"{API_BASE}/{endpoint}"
    headers = _eid_headers()

    # Query params
    if params:
        url += "?" + urllib.parse.urlencode({k: v for k, v in params.items() if v is not None})

    try:
        if files:
            # multipart/form-data (for file uploads)
            import io
            body, boundary = _encode_multipart(data or {}, files)
            headers["Content-Type"] = f"multipart/form-data; boundary={boundary}"
            req = urllib.request.Request(url, data=body, method=method, headers=headers)
        elif data is not None:
            body = json.dumps(data).encode("utf-8")
            headers["Content-Type"] = "application/json"
            req = urllib.request.Request(url, data=body, method=method, headers=headers)
        else:
            req = urllib.request.Request(url, method=method, headers=headers)

        with urllib.request.urlopen(req, timeout=30) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        try:
            err_body = json.loads(e.read().decode("utf-8"))
            return {"_error": f"HTTP {e.code}: {err_body.get('message', e.reason)}",
                    "_http_code": e.code, "_api_code": err_body.get("code")}
        except Exception:
            return {"_error": f"HTTP {e.code}: {e.reason}", "_http_code": e.code}
    except (urllib.error.URLError, json.JSONDecodeError, TimeoutError, OSError) as e:
        return {"_error": str(e)}

    return body


def _eid_headers() -> dict:
    """Build per-call EID identity headers from Hermes' trusted child env."""
    subject = os.environ.get("HERMES_EID_SUBJECT", "").strip()
    if not subject:
        raise RuntimeError("缺少 Hermes 服务端绑定的 EID 用户上下文")

    headers = {
        "Accept": "application/json",
        "X-EID-Subject": subject,
    }
    tenant = os.environ.get("HERMES_EID_TENANT", "").strip()
    delegation = os.environ.get("HERMES_EID_DELEGATION", "").strip()
    development_mode = os.environ.get(
        "HERMES_WEBUI_EID_DEVELOPMENT_MODE", ""
    ).strip().lower() in {"1", "true", "yes", "on"}
    if not delegation and not development_mode:
        raise RuntimeError("缺少 Hermes 服务端绑定的 EID 委托令牌")
    if tenant:
        headers["X-EID-Tenant"] = tenant
    if delegation:
        headers["Authorization"] = f"Bearer {delegation}"
    return headers


def _encode_multipart(data: dict, files: dict) -> (bytes, str):
    """编码 multipart/form-data（文件上传）"""
    import uuid, io
    boundary = uuid.uuid4().hex
    body = io.BytesIO()

    for k, v in data.items():
        body.write(f"--{boundary}\r\n".encode())
        body.write(f'Content-Disposition: form-data; name="{k}"\r\n\r\n'.encode())
        body.write(f"{v}\r\n".encode())

    for field_name, file_info in files.items():
        filename, content = file_info  # (filename, bytes)
        body.write(f"--{boundary}\r\n".encode())
        body.write(f'Content-Disposition: form-data; name="{field_name}"; filename="{filename}"\r\n'.encode())
        body.write(b"Content-Type: application/octet-stream\r\n\r\n")
        body.write(content)
        body.write(b"\r\n")

    body.write(f"--{boundary}--\r\n".encode())
    return body.getvalue(), boundary


def _get(endpoint: str, params: dict = None) -> dict:
    """HTTP GET"""
    return _request("GET", endpoint, params=params)


def _post(endpoint: str, data: dict = None, params: dict = None) -> dict:
    """HTTP POST"""
    return _request("POST", endpoint, params=params, data=data)


def _put(endpoint: str, data: dict = None) -> dict:
    """HTTP PUT"""
    return _request("PUT", endpoint, data=data)


def _delete(endpoint: str, params: dict = None, data: dict = None) -> dict:
    """HTTP DELETE（支持 query params 和 body）
    
    DELETE 可以带 body（如 /decks/lights 批量删除灯具），
    通过 data 参数传入 JSON 请求体。
    """
    return _request("DELETE", endpoint, params=params, data=data)


def _ok(resp: dict) -> bool:
    """检查 API 响应码是否为 0 或 1（成功）"""
    return resp.get("code") in (0, 1)


def _data(resp: dict) -> dict:
    """安全提取 data 字段，失败时返回包含 _error 的 dict"""
    if _ok(resp):
        return resp.get("data", {})
    return {"_error": resp.get("message", "API 请求失败")}


def _list(resp: dict, key: str) -> list:
    """从响应中提取列表"""
    d = _data(resp)
    if "_error" in d:
        return d
    return d.get(key, [])


# ═══════════════════════════════════════════════
# 图纸解析 (Drawings)
# ═══════════════════════════════════════════════

def primary_parse(file_path: str, import_mode: str, pid: str) -> dict:
    """一次解析：上传图纸并解析图层"""
    with open(file_path, "rb") as f:
        file_bytes = f.read()
    filename = Path(file_path).name
    data = {}
    if import_mode:
        data["import_mode"] = import_mode
    if pid:
        data["pid"] = pid
    return _post("drawings/primary-parse",
                 data=data,
                 files={"file": (filename, file_bytes)})


def submit_preview(record_id: str, layer_mappings: list) -> dict:
    """提交图层映射，触发预览图纸生成"""
    return _post("drawings/preview", data={
        "record_id": record_id,
        "layer_mappings": layer_mappings,
    })


def secondary_parse(record_id: str, layer_mappings: list) -> dict:
    """二次解析：切分图纸提取甲板"""
    return _post("drawings/secondary-parse", data={
        "record_id": record_id,
        "layer_mappings": layer_mappings,
    })


def recognition(record_id: str, decks: list) -> dict:
    """完成导入：识别舱室、负载"""
    return _post("drawings/recognition", data={
        "record_id": record_id,
        "decks": decks,
    })


# ═══════════════════════════════════════════════
# 编辑模式
# ═══════════════════════════════════════════════

def edit_mode_start(record_id: str, mode_type: int) -> dict:
    """开始编辑模式（0=舱室编辑，1=元件编辑）"""
    return _post("edit-mode/start", data={"record_id": record_id, "type": mode_type})


def edit_mode_exit(record_id: str, mode_type: int, is_save: bool) -> dict:
    """结束编辑模式"""
    return _post("edit-mode/exit", data={
        "record_id": record_id, "type": mode_type, "isSave": is_save,
    })


# ═══════════════════════════════════════════════
# 甲板 (Decks)
# ═══════════════════════════════════════════════

def get_decks(record_id: str) -> list:
    """查询甲板列表"""
    r = _get("decks", params={"record_id": record_id})
    decks = _list(r, "decks")
    if isinstance(decks, dict) and "_error" in decks:
        return decks
    return decks


def search_deck(record_id: str, system_type: str, deck_id: str,
                keyword: str = "") -> dict:
    """关键字搜索甲板元件（舱室/配电/负载/灯具/梁线/车道线）"""
    return _data(_get("decks/search", params={
        "record_id": record_id,
        "system_type": system_type,
        "deck_id": deck_id,
        "keyword": keyword,
    }))


def update_deck(record_id: str, deck_id: str,
                deck_height: float, deck_name: str) -> dict:
    """编辑甲板信息
    API: PUT /decks
    请求体:
    {
        "record_id": "123",        # 必填
        "deck_id": "1",            # 必填 - 甲板id
        "deck_height": "3",        # 必填 - 甲板高度
        "deck_name": "new_name"    # 必填 - 甲板名称
    }
    响应: {code: 0, data: {record_id, deck_id}}
    """
    data = {
        "record_id": record_id,
        "deck_id": deck_id,
        "deck_height": deck_height,
        "deck_name": deck_name,
    }
    return _data(_put("decks", data=data))


# ═══════════════════════════════════════════════
# 舱室 (Compartments)
# ═══════════════════════════════════════════════

def get_compartments(deck_id: str, record_id: str) -> list:
    """查询甲板的舱室列表"""
    r = _get("decks/compartments", params={
        "record_id": record_id,
        "deck_id": deck_id,
    })
    comps = _list(r, "compartments")
    if isinstance(comps, dict) and "_error" in comps:
        return comps
    return comps


def get_compartment_detail(record_id: str, deck_id: str, compartment_id: str) -> dict:
    """查询舱室详情（面积、轮廓、设备数量等）"""
    return _data(_get("decks/compartments/detail", params={
        "record_id": record_id,
        "deck_id": deck_id,
        "compartment_id": compartment_id,
    }))


def create_compartment(record_id: str, deck_id: str, points: list) -> dict:
    """新增舱室
    API: POST /decks/compartments
    请求体:
    {
        "record_id": "123",          # 必填
        "deck_id": "111",            # 必填
        "points": [[1,2],[3,4],...]  # 必填 - 顶点坐标（四边形4个点，多边形多个点）
    }
    响应:
    {
        code: 0,
        data: {record_id, deck_id, deck_name, compartment_id, compartment_name,
               compartment_function, compartment_area, center_point, points,
               main_switch_board_count, distribution_board_count, load_count,
               light_count, light_total_power, total_luminous_flux}
    }
    """
    return _data(_post("decks/compartments", data={
        "record_id": record_id,
        "deck_id": deck_id,
        "points": points,
    }))


def update_compartment(record_id: str, deck_id: str, compartment_id: str,
                       compartment_name: str, compartment_function: str,
                       points: list) -> dict:
    """编辑舱室属性
    API: PUT /decks/compartments
    请求体:
    {
        "record_id": "123",                    # 必填
        "deck_id": "1",                        # 必填 - 舱室所在甲板id
        "compartment_id": "3",                 # 必填 - 舱室id
        "compartment_name": "...",             # 必填 - 舱室名称
        "compartment_function": "无功能区",      # 必填 - 功能区
        "points": [[1,2],[3,4],...]            # 必填 - 顶点坐标列表
    }
    响应: {code: 0, data: {record_id, deck_id, compartment_id}}
    示例:
        update_compartment("<server-bound-record-id>", "DECK 4", "comp_123",
                          "新舱室", "居住舱室",
                          [[10,20],[30,20],[30,60],[10,60]])
    """
    data = {
        "record_id": record_id,
        "deck_id": deck_id,
        "compartment_id": compartment_id,
        "compartment_name": compartment_name,
        "compartment_function": compartment_function,
        "points": points,
    }
    return _data(_put("decks/compartments", data=data))


def delete_compartment(record_id: str, deck_id: str, compartment_id: str) -> dict:
    """删除舱室
    API: DELETE /decks/compartments?record_id=xxx&deck_id=xxx&compartment_id=xxx
    请求参数（query params）:
        record_id      - 必填 - 记录id
        deck_id        - 必填 - 甲板id
        compartment_id - 必填 - 舱室id
    响应: {code: 0, data: {record_id, deck_id, compartment_id}}
    """
    return _data(_delete("decks/compartments", params={
        "record_id": record_id,
        "deck_id": deck_id,
        "compartment_id": compartment_id,
    }))


# ═══════════════════════════════════════════════
# 主配电板 (Main Switchboards)
# ═══════════════════════════════════════════════

def get_main_switchboards(record_id: str, deck_id: str,
                          compartment_id: str = None) -> list:
    """查询主配电板列表
    API: GET /decks/main-switchboards?record_id=xxx&deck_id=xxx[&compartment_id=xxx]
    参数:
        record_id      - 必填
        deck_id        - 必填 - 甲板id
        compartment_id - 可选 - 舱室id，传则只查该舱室内的主配电板
    """
    r = _get("decks/main-switchboards", params={
        "record_id": record_id,
        "deck_id": deck_id,
        "compartment_id": compartment_id,
    })
    return _list(r, "main_switchboards")


def get_main_switchboard_detail(record_id: str, msb_id: str) -> dict:
    """查询主配电板详情"""
    return _data(_get("decks/main-switchboards/detail", params={
        "record_id": record_id,
        "msb_id": msb_id,
    }))


def get_main_switchboard_connected(record_id: str, msb_id: str) -> dict:
    """查询与主配电板关联的元件"""
    return _data(_get("decks/main-switchboards/connected", params={
        "record_id": record_id,
        "msb_id": msb_id,
    }))


# ═══════════════════════════════════════════════
# 分配电箱 (Distribution Boards)
# ═══════════════════════════════════════════════

def get_distribution_boards(record_id: str, deck_id: str,
                            compartment_id: str = None) -> list:
    """查询分配电箱列表
    API: GET /decks/distribution-boards?record_id=xxx&deck_id=xxx[&compartment_id=xxx]
    参数:
        record_id      - 必填
        deck_id        - 必填 - 甲板id
        compartment_id - 可选 - 舱室id，传则只查该舱室内的分配电箱
    """
    r = _get("decks/distribution-boards", params={
        "record_id": record_id,
        "deck_id": deck_id,
        "compartment_id": compartment_id,
    })
    return _list(r, "distribution_boards")


def get_distribution_board_detail(record_id: str, db_id: str) -> dict:
    """查询分配电箱详情"""
    return _data(_get("decks/distribution-boards/detail", params={
        "record_id": record_id,
        "db_id": db_id,
    }))


def get_distribution_board_connected(record_id: str, db_id: str) -> dict:
    """查询分配电箱关联的元件"""
    return _data(_get("decks/distribution-boards/connected", params={
        "record_id": record_id,
        "db_id": db_id,
    }))


# ═══════════════════════════════════════════════
# 负载 (Loads)
# ═══════════════════════════════════════════════

def get_loads(record_id: str, deck_id: str, compartment_id: str) -> list:
    """查询负载列表
    API: GET /decks/loads?record_id=xxx&deck_id=xxx[&compartment_id=xxx]
    参数:
        record_id      - 必填 - 记录id
        deck_id        - 必填 - 甲板id
        compartment_id - 可选 - 舱室id，传则只查该舱室内的负载，不传查甲板全部负载
    """
    r = _get("decks/loads", params={
        "record_id": record_id,
        "deck_id": deck_id,
        "compartment_id": compartment_id,
    })
    return _list(r, "loads")


def get_load_detail(record_id: str, load_id: str) -> dict:
    """查询负载详情"""
    return _data(_get("decks/loads/detail", params={
        "record_id": record_id,
        "load_id": load_id,
    }))


def get_loads_with_detail(record_id: str, deck_id: str, compartment_id: str = "") -> dict:
    """组合查询：先查负载列表，再逐条查负载详情
    API: GET /decks/loads (列表) → GET /decks/loads/detail (逐条详情)
    参数:
        record_id      - 必填 - 记录id
        deck_id        - 必填 - 甲板id
        compartment_id - 可选 - 舱室id，传则只查该舱室内的负载
    返回:
        {
            "total": N,
            "loads": [
                {
                    "load_id": "...",
                    "load_name": "...",
                    ... (所有详情字段)
                },
                ...
            ]
        }
    """
    # Step 1: 查负载列表
    load_list = get_loads(record_id, deck_id, compartment_id)

    # Step 2: 逐条查详情
    detailed_loads = []
    for load in load_list:
        load_id = load.get("load_id")
        if load_id:
            detail = get_load_detail(record_id, load_id)
            detailed_loads.append(detail)

    return {
        "total": len(detailed_loads),
        "loads": detailed_loads,
    }


def update_load(record_id: str, load_id: str,
                load_name: str, type: str,
                compartment_id: str, supply_equipment_id: str) -> dict:
    """编辑负载
    API: PUT /decks/loads
    请求体:
    {
        "record_id": "123",                    # 必填
        "load_id": "load_001",                 # 必填 - 负载id
        "load_name": "负载1",                   # 必填 - 负载名称
        "type": "PC",                           # 必填 - 负载类型
        "compartment_id": "1",                  # 必填 - 所在舱室id
        "supply_equipment_id": "msb_002"        # 必填 - 供电设备id
    }
    响应: {code: 0, data: {record_id, load_id}}
    示例:
        update_load("<server-bound-record-id>", "load_001",
                    "主引擎", "PC",
                    "comp_123", "msb_001")
    """
    data = {
        "record_id": record_id,
        "load_id": load_id,
        "load_name": load_name,
        "type": type,
        "compartment_id": compartment_id,
        "supply_equipment_id": supply_equipment_id,
    }
    return _data(_put("decks/loads", data=data))


# ═══════════════════════════════════════════════
# 灯具 (Lights)
# ═══════════════════════════════════════════════

def get_light_types(record_id: str) -> list:
    """查询可用灯具类型"""
    r = _get("decks/lights/type", params={"record_id": record_id})
    if _ok(r):
        return r.get("data", [])
    return []


def get_lights(record_id: str, deck_id: str, compartment_id: str) -> list:
    """查询灯具列表
    API: GET /decks/lights?record_id=xxx&deck_id=xxx[&compartment_id=xxx]
    参数:
        record_id      - 必填
        deck_id        - 必填 - 甲板id
        compartment_id - 可选 - 舱室id，传则只查该舱室内的灯具
    """
    r = _get("decks/lights", params={
        "record_id": record_id,
        "deck_id": deck_id,
        "compartment_id": compartment_id,
    })
    return _list(r, "lights")


def get_light_detail(record_id: str, light_id: str) -> dict:
    """查询灯具详情"""
    return _data(_get("decks/lights/detail", params={
        "record_id": record_id,
        "light_id": light_id,
    }))


def update_light(record_id: str, light_id: str,
                 light_name: str, compartment_id: str,
                 light_type_id: str, points: list) -> dict:
    """编辑灯具
    API: PUT /decks/lights
    请求体:
    {
        "record_id": "123",                    # 必填
        "light_id": "light_001",               # 必填 - 灯具id
        "light_name": "灯具1",                  # 必填 - 灯具名称
        "compartment_id": "1",                  # 必填 - 所在舱室id
        "light_type_id": "筒灯_001",            # 必填 - 灯具类型id
        "points": [1, 2]                        # 必填 - 位置坐标[x, y]
    }
    响应: {code: 0, data: {record_id, compartment_id, light_id}}
    """
    data = {
        "record_id": record_id,
        "light_id": light_id,
        "light_name": light_name,
        "compartment_id": compartment_id,
        "light_type_id": light_type_id,
        "points": points,
    }
    return _data(_put("decks/lights", data=data))


def delete_lights(record_id: str, light_ids: list) -> dict:
    """批量删除灯具"""
    return _data(_delete("decks/lights", data={
        "record_id": record_id,
        "light_ids": light_ids,
    }))


def recommend_light_count(record_id: str, compartment_id: str, light_type_id: str,
                          illuminance: float, utilization: float,
                          maintenance: float) -> dict:
    """灯具数量推荐"""
    return _data(_post("decks/lights/count-recommendation", data={
        "record_id": record_id,
        "compartment_id": compartment_id,
        "light_type_id": light_type_id,
        "illuminance": illuminance,
        "utilization": utilization,
        "maintenance": maintenance,
    }))


def layout_lights(record_id: str, compartment_id: str, light_type_count: list,
                  layout_type: str = "uniform") -> dict:
    """灯具布局（获取灯具位置）"""
    return _data(_post("decks/lights/lights-layout", data={
        "record_id": record_id,
        "compartment_id": compartment_id,
        "light_type_count": light_type_count,
        "layout_type": layout_type,
    }))


def verify_illuminance(record_id: str, compartment_id: str, light_type_count: list,
                       illuminance: float = 200, utilization: float = 0.8,
                       maintenance: float = 1.0) -> dict:
    """灯具验算照度"""
    return _data(_post("decks/lights/verify-illuminance", data={
        "record_id": record_id,
        "compartment_id": compartment_id,
        "light_type_count": light_type_count,
        "illuminance": illuminance,
        "utilization": utilization,
        "maintenance": maintenance,
    }))


def update_lights_layout(record_id: str, compartment_id: str, lights_points: list) -> dict:
    """灯具布局更新（更新坐标）"""
    return _data(_post("decks/lights/layout-update", data={
        "record_id": record_id,
        "compartment_id": compartment_id,
        "lights_points": lights_points,
    }))


# ═══════════════════════════════════════════════
# 梁线 (Beam Lines)
# ═══════════════════════════════════════════════

def get_beam_lines(record_id: str, deck_id: str, compartment_id: str) -> list:
    r = _get("decks/beam-lines", params={
        "record_id": record_id,
        "deck_id": deck_id,
        "compartment_id": compartment_id,
    })
    return _list(r, "beam_lines")


def get_beam_line_detail(record_id: str, beam_line_id: str) -> dict:
    return _data(_get("decks/beam-lines/detail", params={
        "record_id": record_id,
        "beam_line_id": beam_line_id,
    }))


def create_beam_line(record_id: str, deck_id: str, points: list) -> dict:
    return _data(_post("decks/beam-lines", data={
        "record_id": record_id,
        "deck_id": deck_id,
        "points": points,
    }))


def update_beam_line(record_id: str, beam_line_id: str,
                     beam_line_name: str, length: float,
                     width: float, points: list,
                     deck_id: str) -> dict:
    """编辑梁线
    API: PUT /decks/beam-lines
    请求体:
    {
        "record_id": "123",                    # 必填
        "beam_line_id": "001",                 # 必填 - 梁线id
        "beam_line_name": "梁线1",              # 必填 - 梁线名称
        "length": 15,                           # 必填 - 长度
        "width": 15,                            # 必填 - 宽度
        "points": [[10,20],[30,20]],            # 必填 - 端点坐标
        "deck_id": "deck_id"                    # 必填 - 所属甲板
    }
    响应: {code: 0, data: {record_id, beam_line_id}}
    """
    data = {
        "record_id": record_id,
        "beam_line_id": beam_line_id,
        "beam_line_name": beam_line_name,
        "length": length,
        "width": width,
        "points": points,
        "deck_id": deck_id,
    }
    return _data(_put("decks/beam-lines", data=data))


def delete_beam_line(record_id: str, beam_line_id: str) -> dict:
    return _data(_delete("decks/beam-lines", params={
        "record_id": record_id,
        "beam_line_id": beam_line_id,
    }))


# ═══════════════════════════════════════════════
# 车道线 (Lane Lines)
# ═══════════════════════════════════════════════

def get_lane_lines(record_id: str, deck_id: str, compartment_id: str) -> list:
    r = _get("decks/lane-lines", params={
        "record_id": record_id,
        "deck_id": deck_id,
        "compartment_id": compartment_id,
    })
    return _list(r, "lane_lines")


def get_lane_line_detail(record_id: str, lane_line_id: str) -> dict:
    return _data(_get("decks/lane-lines/detail", params={
        "record_id": record_id,
        "lane_line_id": lane_line_id,
    }))


def create_lane_line(record_id: str, deck_id: str, points: list) -> dict:
    return _data(_post("decks/lane-lines", data={
        "record_id": record_id,
        "deck_id": deck_id,
        "points": points,
    }))


def update_lane_line(record_id: str, lane_line_id: str,
                     lane_line_name: str, length: float,
                     width: float, points: list,
                     deck_id: str) -> dict:
    """编辑车道线
    API: PUT /decks/lane-lines
    请求体:
    {
        "record_id": "123",                    # 必填
        "lane_line_id": "001",                 # 必填 - 车道线id
        "lane_line_name": "车道线1",            # 必填 - 车道线名称
        "length": 15,                           # 必填 - 长度
        "width": 15,                            # 必填 - 宽度
        "points": [[10,20],[30,20]],            # 必填 - 端点坐标
        "deck_id": "deck_1"                     # 必填 - 所属甲板
    }
    响应: {code: 0, data: {record_id, lane_line_id}}
    """
    data = {
        "record_id": record_id,
        "lane_line_id": lane_line_id,
        "lane_line_name": lane_line_name,
        "length": length,
        "width": width,
        "points": points,
        "deck_id": deck_id,
    }
    return _data(_put("decks/lane-lines", data=data))


def delete_lane_line(record_id: str, lane_line_id: str) -> dict:
    return _data(_delete("decks/lane-lines", params={
        "record_id": record_id,
        "lane_line_id": lane_line_id,
    }))


# ═══════════════════════════════════════════════
# 接线盒 (Junction Boxes)
# ═══════════════════════════════════════════════

def get_junction_boxes(record_id: str, deck_id: str) -> list:
    """查询接线盒列表（按分配电箱分组）"""
    r = _get("decks/junction-boxes", params={
        "record_id": record_id,
        "deck_id": deck_id,
    })
    return _list(r, "distribution_boards")


def create_junction_box(record_id: str, deck_id: str, db_id: str) -> dict:
    """新建接线盒"""
    return _data(_post("decks/junction-boxes", data={
        "record_id": record_id,
        "deck_id": deck_id,
        "db_id": db_id,
    }))


# ═══════════════════════════════════════════════unbound-power
# 绑定 (Allocation)
# ═══════════════════════════════════════════════

def get_unbound_compartment(record_id: str, system_type: str) -> dict:
    """查询未绑定舱室的负载"""
    return _data(_get("allocation/unbound-compartment", params={
        "record_id": record_id,
        "system_type": system_type,
    }))


def get_unbound_power(record_id: str, deck_id: str, system_type: str,
                      compartment_id: str = None) -> dict:
    """查询未绑定配电的负载"""
    return _data(_get("allocation/unbound-power", params={
        "record_id": record_id,
        "deck_id": deck_id,
        "system_type": system_type,
        "compartment_id": compartment_id,
    }))


def bind_compartment(record_id: str, deck_id: str, compartment_id: str,
                     unbound_loads: list) -> dict:
    """绑定负载到舱室"""
    return _data(_post("allocation/bind-compartment", data={
        "record_id": record_id,
        "deck_id": deck_id,
        "compartment_id": compartment_id,
        "unbound_loads": unbound_loads,
    }))


def unbind_compartment(record_id: str, unbound_loads: list) -> dict:
    """从舱室解绑负载"""
    return _data(_post("allocation/unbind-compartment", data={
        "record_id": record_id,
        "unbound_loads": unbound_loads,
    }))


def bind_power(record_id: str, supply_equipment_id: str, unbound_loads: list) -> dict:
    """绑定负载到供电设备"""
    return _data(_post("allocation/bind-power", data={
        "record_id": record_id,
        "supply_equipment_id": supply_equipment_id,
        "unbound_loads": unbound_loads,
    }))


def unbind_power(record_id: str, unbound_loads: list) -> dict:
    """从供电设备解绑负载"""
    return _data(_post("allocation/unbind-power", data={
        "record_id": record_id,
        "unbound_loads": unbound_loads,
    }))


# ═══════════════════════════════════════════════
# 导入记录 (Records)
# ═══════════════════════════════════════════════

def get_records(record_id: str) -> list:
    """查询导入记录列表"""
    r = _get("records")
    recs = _list(r, "records")
    if isinstance(recs, dict) and "_error" in recs:
        return recs
    return recs


def get_record_snapshot(record_id: str) -> dict:
    """查询记录回溯"""
    return _data(_get("records/snapshot", params={"record_id": record_id}))


# ═══════════════════════════════════════════════
# 画布渲染 (Canvas) — 核心嵌套数据
# ═══════════════════════════════════════════════

def get_canvas_all(record_id: str, system_type: str) -> dict:
    """获取画布完整数据（核心接口）
    API: GET /canvas/all?record_id=xxx[&system_type=primary/secondary/lighting]
    参数:
        record_id   - Hermes 服务端绑定的当前会话记录 ID
        system_type - 系统类型过滤: primary(一次系统) / secondary(二次系统) / lighting(照明系统)
                      不传则返回全部（此时数据在 primary/secondary/lighting 三个子对象中）
    响应结构:
        data.decks[].compartments[].{
            compartment_id, compartment_name, center_point, points,
            primary: {main_switchboards[], distribution_boards[], loads[]},
            secondary: {distribution_boards[], loads[]},
            lighting: {lights[], beam_lines[], lane_lines[]}
        }"""
    params = {"record_id": record_id}
    if system_type:
        params["system_type"] = system_type
    return _data(_get("canvas/all", params=params))


# ═══════════════════════════════════════════════
# 工具 (Tools)
# ═══════════════════════════════════════════════

def measure_point(record_id: str, deck_id: str, start_point: list,
                  end_point: list) -> dict:
    """点距测量"""
    return _data(_post("tools/measure-point", data={
        "record_id": record_id,
        "deck_id": deck_id,
        "start_point": start_point,
        "end_point": end_point,
    }))


def measure_compartment(record_id: str, start_deck_id: str, start_compartment_id: str,
                        end_deck_id: str, end_compartment_id: str) -> dict:
    """舱室距离测量"""
    return _data(_post("tools/measure-compartment", data={
        "record_id": record_id,
        "start_deck_id": start_deck_id,
        "start_compartment_id": start_compartment_id,
        "end_deck_id": end_deck_id,
        "end_compartment_id": end_compartment_id,
    }))


# ═══════════════════════════════════════════════
# 组合查询（快捷函数）
# ═══════════════════════════════════════════════

def get_all_compartments(record_id: str) -> list:
    """获取所有甲板的全部舱室"""
    decks = get_decks(record_id)
    if isinstance(decks, dict) and "_error" in decks:
        return decks

    all_comps = []
    for deck in decks:
        comps = get_compartments(deck["deck_id"], record_id)
        if isinstance(comps, list):
            for c in comps:
                c["deck_id"] = deck["deck_id"]
                all_comps.append(c)
    return all_comps


def get_compartment_info(compartment_name: str, record_id: str) -> dict:
    """按名称查找舱室"""
    all_comps = get_all_compartments(record_id)
    if isinstance(all_comps, dict) and "_error" in all_comps:
        return all_comps
    for c in all_comps:
        if c.get("compartment_name", "").lower() == compartment_name.lower():
            return c
    return {"_error": f"未找到舱室: {compartment_name}"}


def get_system_status(record_id: str) -> dict:
    """获取系统状态"""
    decks = get_decks(record_id)
    records = get_records(record_id)

    decks_list = decks if isinstance(decks, list) else []
    records_list = records if isinstance(records, list) else []

    # 舱室统计
    total_compartments = 0
    decks_with_comps = []
    for deck in decks_list:
        comps = get_compartments(deck["deck_id"], record_id)
        if isinstance(comps, list):
            total_compartments += len(comps)
            decks_with_comps.append({"deck_id": deck["deck_id"], "count": len(comps)})

    return {
        "_source": "api",
        "decks": decks_list,
        "compartments": {"total": total_compartments, "by_deck": decks_with_comps},
        "records_count": len(records_list),
        "last_import": records_list[0].get("file_name") if records_list else None,
    }
