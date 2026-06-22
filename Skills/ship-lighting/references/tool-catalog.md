# 工具完整目录（61 项）

> 58 原子工具 + 3 组合工具。所有工具通过 `tool_dispatcher.py --tool <name> --params '<JSON>'` 调用，`record_id` 自动注入。

## 图纸解析（4 项）

| 工具 | 功能 | 必填参数 |
|------|------|----------|
| `primary_parse` | 一次解析：上传图纸提取图层 | file_path, import_mode, pid |
| `submit_preview` | 提交图层映射触发预览 | record_id, layer_mappings |
| `secondary_parse` | 二次解析：切分图纸提取甲板 | record_id, layer_mappings |
| `recognition` | 完成导入：识别舱室/负载 | record_id, decks |

## 编辑模式（2 项）

| 工具 | 功能 | 必填参数 |
|------|------|----------|
| `edit_mode_start` | 开始编辑模式 | record_id, mode_type |
| `edit_mode_exit` | 结束编辑模式 | record_id, mode_type, is_save |

## 甲板（3 项）

| 工具 | 功能 | 必填参数 |
|------|------|----------|
| `get_decks` | 查询甲板列表 | record_id |
| `search_deck` | 关键字搜索甲板元件 | record_id, system_type, keyword, deck_id |
| `update_deck` | 编辑甲板信息 | record_id, deck_id, deck_height, deck_name |

## 舱室（5 项）

| 工具 | 功能 | 必填参数 |
|------|------|----------|
| `get_compartments` | 查询舱室列表 | record_id, deck_id |
| `get_compartment_detail` | 查询舱室详情 | record_id, deck_id, compartment_id |
| `create_compartment` | 新增舱室 | record_id, deck_id, points |
| `update_compartment` | 编辑舱室 | record_id, deck_id, compartment_id, compartment_name, compartment_function, points |
| `delete_compartment` | 删除舱室 | record_id, deck_id, compartment_id |

## 主配电板（3 项）

| 工具 | 功能 | 必填参数 |
|------|------|----------|
| `get_main_switchboards` | 查询主配电板列表 | record_id, deck_id, compartment_id |
| `get_main_switchboard_detail` | 查询主配电板详情 | record_id, msb_id |
| `get_main_switchboard_connected` | 查询主配电板关联元件 | record_id, msb_id |

## 分配电箱（3 项）

| 工具 | 功能 | 必填参数 |
|------|------|----------|
| `get_distribution_boards` | 查询分配电箱列表 | record_id, deck_id, compartment_id |
| `get_distribution_board_detail` | 查询分配电箱详情 | record_id, db_id |
| `get_distribution_board_connected` | 查询分配电箱关联元件 | record_id, db_id |

## 负载（4 项）

| 工具 | 功能 | 必填参数 |
|------|------|----------|
| `get_loads` | 查询负载列表 | record_id, deck_id, compartment_id |
| `get_load_detail` | 查询负载详情 | record_id, load_id |
| `get_loads_with_detail` | 组合查询：列表+逐条详情 | record_id, deck_id, compartment_id |
| `update_load` | 编辑负载 | record_id, load_id, load_name, type, compartment_id, supply_equipment_id |

> 查整个甲板时 `compartment_id=""`。`update_load` 不支持电气参数（rated_*）。

## 灯具（9 项）

| 工具 | 功能 | 必填参数 |
|------|------|----------|
| `get_light_types` | 查询灯具类型列表 | record_id |
| `get_lights` | 查询灯具列表 | record_id, deck_id, compartment_id |
| `get_light_detail` | 查询灯具详情 | record_id, light_id |
| `update_light` | 编辑灯具 | record_id, light_id, light_name, compartment_id, light_type_id, points |
| `delete_lights` | 批量删除灯具 | record_id, light_ids |
| `recommend_light_count` | 灯具数量推荐 | record_id, compartment_id, light_type_id, illuminance, utilization, maintenance |
| `layout_lights` | 灯具布局 | record_id, compartment_id, light_type_count, layout_type |
| `verify_illuminance` | 灯具验算照度 | record_id, compartment_id, light_type_count, illuminance, utilization, maintenance |
| `update_lights_layout` | 灯具坐标更新 | record_id, compartment_id, lights_points |

> `light_type_id` 用 ID（如 `type_02`）不用名称。`layout_type` 枚举：`one_click` | `uniform` | `lane_beam`。

## 梁线（5 项）

| 工具 | 功能 | 必填参数 |
|------|------|----------|
| `get_beam_lines` | 查询梁线列表 | record_id, deck_id |
| `get_beam_line_detail` | 查询梁线详情 | record_id, beam_line_id |
| `create_beam_line` | 新增梁线 | record_id, deck_id, points |
| `update_beam_line` | 编辑梁线 | record_id, beam_line_id |
| `delete_beam_line` | 删除梁线 | record_id, beam_line_id |

## 车道线（5 项）

| 工具 | 功能 | 必填参数 |
|------|------|----------|
| `get_lane_lines` | 查询车道线列表 | record_id, deck_id |
| `get_lane_line_detail` | 查询车道线详情 | record_id, lane_line_id |
| `create_lane_line` | 新增车道线 | record_id, deck_id, points |
| `update_lane_line` | 编辑车道线 | record_id, lane_line_id |
| `delete_lane_line` | 删除车道线 | record_id, lane_line_id |

## 接线盒（2 项）

| 工具 | 功能 | 必填参数 |
|------|------|----------|
| `get_junction_boxes` | 查询接线盒列表 | record_id, deck_id |
| `create_junction_box` | 新建接线盒 | record_id, deck_id, db_id |

## 绑定（6 项）

| 工具 | 功能 | 必填参数 |
|------|------|----------|
| `get_unbound_compartment` | 查询未绑定舱室的负载 | record_id, system_type |
| `get_unbound_power` | 查询未绑定配电的负载 | record_id, deck_id, system_type, compartment_id |
| `bind_compartment` | 绑定负载到舱室 | record_id, deck_id, compartment_id, unbound_loads |
| `unbind_compartment` | 从舱室解绑负载 | record_id, unbound_loads |
| `bind_power` | 绑定负载到供电设备 | record_id, supply_equipment_id, unbound_loads |
| `unbind_power` | 从供电设备解绑负载 | record_id, unbound_loads |

> `system_type` 枚举：`primary` | `secondary` | `lighting`。**但 `get_unbound_compartment` 不接受 `lighting`**。

## 导入记录 / 画布 / 测量 / 组合查询（8 项）

| 工具 | 功能 | 必填参数 |
|------|------|----------|
| `get_records` | 查询导入记录 | （无） |
| `get_record_snapshot` | 查询记录回溯 | record_id |
| `get_canvas_all` | 获取画布完整数据 | record_id |
| `measure_point` | 点距测量 | record_id, deck_id, start_point, end_point |
| `measure_compartment` | 舱室距离测量 | record_id, start_deck_id, start_compartment_id, end_deck_id, end_compartment_id |
| `get_all_compartments` | 获取所有甲板全部舱室 | （无） |
| `get_compartment_info` | 按名称查找舱室 | compartment_name |
| `get_system_status` | 获取系统状态 | （无） |

> `get_canvas_all` 输出可超 4MB，慎用——优先用独立查询工具。

## 组合工具（1 项）

| 工具 | pipeline | 必填参数 |
|------|----------|----------|
| `full_illumination_design` | `recommend_light_count` → `verify_illuminance` → `layout_lights` | compartment_id, light_type_id, illuminance, utilization, maintenance, layout_type |

机制详见 [composite-pipeline.md](composite-pipeline.md) 与 [composite-pipeline-behavior.md](composite-pipeline-behavior.md)。

实测案例：
- [full-illumination-design-example.md](full-illumination-design-example.md) — CHAIN LOCKER，107 盏泛光灯B
- [full-illumination-design-watermist-example.md](full-illumination-design-watermist-example.md) — WATERMIST，399 盏泛光灯B
