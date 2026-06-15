---
name: ship-lighting
description: "通过 Hermes 服务端绑定的 EID 用户与记录上下文，查询和修改船舶电气、照明图纸数据。用于甲板、舱室、配电、负载、灯具、布局和照度验算等 EID 业务操作。"
license: MIT
metadata:
  hermes:
    tags: [ship, lighting, http-api, param-validation, required-params]
---

# 船舶照明智能体 v1.0

## 强制规范

**规则1：先加载 skill，再执行。** 必须先 `skill_view(name='ship-lighting')` 再看用户意图。

**规则2：仅在显式开发诊断中直接运行脚本。** 此时输出四项证据：脚本绝对路径、完整命令、退出码、关键输出前10行；不得输出 EID 身份头、环境变量值或委托令牌。

**规则3：生产环境只通过 Hermes 服务端注册的 EID 专用工具调用 API。**
- EID 专用工具负责绑定可信用户、当前会话 record 和短期委托令牌。
- `tool_dispatcher.py` + `param_validator.py` 是服务端工具内部适配器和本地开发入口，不是独立授权边界。
- 若当前运行后端没有 EID 专用工具或无法传递完整可信上下文，明确拒绝业务操作；禁止回退到通用 terminal、直接调用 `api_client` 或 `curl`。

**规则4：EID 业务上下文由 Hermes 服务端提供。**
- 不读取、猜测、缓存或要求用户提供 `record_id`、`user_id`。
- 不允许模型在 `--params` 中传入或覆盖 `record_id`、`user_id`。
- `tool_dispatcher.py` 只使用当前运行上下文中的 `HERMES_EID_SUBJECT` 和 `HERMES_EID_RECORD_ID`。
- 无可信用户上下文时停止调用并提示重新登录；无 record 上下文时停止调用并提示先打开或选择记录。
- EID 后端对每次业务数据访问执行最终授权校验；Hermes profile 只是 Agent 配置，不是用户身份。
- `SHIP_LIGHTING_RECORD_ID` 和任何固定默认 record 均不得用于生产业务调用。

**规则5：查询操作必须展示所有返回内容。** 用户明确要求：查询 API 返回的全部字段和内容都要展示给用户，不能截断或仅展示部分摘要。用结构化表格展示数据，有链接的也需要展示出来。

**规则6：参数不全时，向用户展示结构化表格。** 格式如下：

**规则8：写操作必须先获得用户确认。** 写操作前展示确认表格并调用 `clarify`。生产环境确认后调用 EID 专用写工具；仅在显式开发诊断中，才使用 `echo "y" | python3 scripts/tool_dispatcher.py ... --confirm` 的 CLI 双层确认。

**规则7：所有业务函数参数必须为必填位置参数，禁止 `**kwargs` 和 `= None` 默认值。**
- 每个 API 字段都必须有对应的显式位置参数
- docstring 中所有参数标注**必填**（不写"可选"）
- `record_id` 仅作为脚本内部必填参数，由调度器从服务端上下文注入
- 这一规则来自用户明确要求：把所有可选参数改为必填，消除隐藏默认值

```
❌ 查看灯具缺少必要参数
| 状态 | 缺少参数 | 说明 |
|:----:|---------|------|
| ❌ | deck_id | 甲板ID，必填 |
| ⚠️ | compartment_id | 可选，过滤到具体舱室 |

可用甲板：
  · DECK 4 (13.2m)
  · DECK 5 (15.0m)  
  · DECK 6 (18.0m)

请提供 deck_id
```

---

## 架构

### EID 服务端工具边界

本目录保留 Skill 的领域说明、参数规则和脚本实现，但生产执行边界必须是 Hermes
服务端注册的 EID 专用工具。公开工具参数不包含 `user_id`、`record_id` 或委托令牌；
服务端执行器在调用本目录脚本时注入 `TrustedEidContext`。

`tool_dispatcher.py` 可用于两种场景：
- EID 专用工具的内部适配层。
- 显式开启 EID development mode 的本地诊断。

它不得被当作通用 terminal 的生产授权边界。若服务端 binder 尚未部署，保持
fail-closed 并提示当前后端不支持 EID 业务工具。

```
用户自然语言
    │
    ▼
LLM（你）负责：
  ├── 意图识别     → 匹配 api_tool（57 个工具）
  ├── 参数提取     → 从用户语句中提取结构化参数
  └── 调度执行     → 调用 Hermes EID 专用工具
          │
          ▼
EidToolContextBinder 负责：
  ├── 绑定当前已鉴权用户和会话 record_id
  ├── 传递短期委托令牌
  └── 调用 tool_dispatcher.py
          │
          ▼
tool_dispatcher.py 负责：
  ├── 注入服务端授权的当前会话 record_id
  ├── param_validator 参数校验
  │     ├── 检查必填参数
  │     ├── 检查枚举值合法性
  │     └── 动态获取可用选项（如可用甲板列表）
  └── api_client HTTP 调用
          │
          ▼
    ┌──────────────────────────────────────┐
    │       HTTP API (Flask)               │
    │  http://192.168.208.23:5000/api/v1   │
    └──────────────────────────────────────┘
```

### 参数校验流程

`param_validator.py` 在每个 API 调用前执行三层检查（与 api_client 函数签名的必填参数互补）：

1. **必填参数** — 缺少时返回 `validation_error` + 缺失列表 + 可用选项（如自动获取甲板列表）
2. **枚举值** — 不合法时返回 `invalid_enum` + 允许值列表
3. **未知参数** — 提醒用户有不在已知列表中的参数（不阻塞调用）

> **为什么已有必填参数还需要 param_validator？**
> api_client 函数签名的必填参数会在缺少时抛出 Python `TypeError`（模糊的"missing argument"），
> 而 param_validator 能给出结构化错误（"缺少 deck_id，可用甲板：DECK 4, DECK 5, DECK 6"）。
> 它也在**调用 API 之前**拦截非法枚举值，避免浪费网络请求。

---

## 工具总览（61 项）

> **注意：** 实际可用工具 61 个（58 原子工具 + 3 组合工具），覆盖图纸解析到照度验算全流程。

### 图纸解析（4 项）
| 工具 | 功能 | 必填参数 |
|------|------|----------|
| `primary_parse` | 一次解析：上传图纸提取图层 | file_path, import_mode, pid |
| `submit_preview` | 提交图层映射触发预览 | layer_mappings |
| `secondary_parse` | 二次解析：切分图纸提取甲板 | layer_mappings |
| `recognition` | 完成导入：识别舱室/负载 | decks |

### 编辑模式（2 项）
| 工具 | 功能 | 必填参数 |
|------|------|----------|
| `edit_mode_start` | 开始编辑模式 | mode_type |
| `edit_mode_exit` | 结束编辑模式 | mode_type, is_save |

### 甲板（3 项）
| 工具 | 功能 | 必填参数 |
|------|------|----------|
| `get_decks` | 查询甲板列表 | 无 |
| `search_deck` | 关键字搜索甲板元件 | system_type, keyword, deck_id |
| `update_deck` | 编辑甲板信息 | deck_id, deck_height, deck_name |

### 舱室（5 项）
| 工具 | 功能 | 必填参数 |
|------|------|----------|
| `get_compartments` | 查询舱室列表 | deck_id |
| `get_compartment_detail` | 查询舱室详情 | deck_id, compartment_id |
| `create_compartment` | 新增舱室 | deck_id, points |
| `update_compartment` | 编辑舱室 | deck_id, compartment_id, compartment_name, compartment_function, points |
| `delete_compartment` | 删除舱室 | deck_id, compartment_id |

### 主配电板（3 项）
| 工具 | 功能 | 必填参数 |
|------|------|----------|
| `get_main_switchboards` | 查询主配电板列表 | deck_id, compartment_id |
| `get_main_switchboard_detail` | 查询主配电板详情 | msb_id |
| `get_main_switchboard_connected` | 查询主配电板关联元件 | msb_id |

### 分配电箱（3 项）
| 工具 | 功能 | 必填参数 |
|------|------|----------|
| `get_distribution_boards` | 查询分配电箱列表 | deck_id, compartment_id |
| `get_distribution_board_detail` | 查询分配电箱详情 | db_id |
| `get_distribution_board_connected` | 查询分配电箱关联元件 | db_id |

### 负载（4 项）
| 工具 | 功能 | 必填参数 | 可选参数 |
|------|------|----------|----------|
| `get_loads` | 查询负载列表 | deck_id | compartment_id |
| `get_load_detail` | 查询负载详情 | load_id | - |
| `get_loads_with_detail` | 组合查询：列表+逐条详情 | deck_id | compartment_id |
| `update_load` | 编辑负载 | load_id | load_name, type, compartment_id, supply_equipment_id |

### 灯具（9 项）
| 工具 | 功能 | 必填参数 |
|------|------|----------|
| `get_light_types` | 查询灯具类型列表 | 无 |
| `get_lights` | 查询灯具列表 | deck_id, compartment_id |
| `get_light_detail` | 查询灯具详情 | light_id |
| `update_light` | 编辑灯具 | light_id, light_name, compartment_id, light_type_id, points |
| `delete_lights` | 批量删除灯具 | light_ids |
| `recommend_light_count` | 灯具数量推荐 | compartment_id, light_type_id, illuminance, utilization, maintenance |
| `layout_lights` | 灯具布局 | compartment_id, light_type_count, layout_type |
| `verify_illuminance` | 灯具验算照度 | compartment_id, light_type_count, illuminance, utilization, maintenance |
| `update_lights_layout` | 灯具坐标更新 | compartment_id, lights_points |

> **`layout_type` 枚举：** `one_click`（一键部署）| `uniform`（均匀布局）| `lane_beam`（绕梁布灯）

### 梁线（5 项）、车道线（5 项）、接线盒（2 项）
| 工具 | 功能 | 必填参数 |
|------|------|----------|
| `get_beam_lines` | 查询梁线列表 | deck_id |
| `get_beam_line_detail` | 查询梁线详情 | beam_line_id |
| `create_beam_line` | 新增梁线 | deck_id, points |
| `update_beam_line` | 编辑梁线 | beam_line_id |
| `delete_beam_line` | 删除梁线 | beam_line_id |
| `get_lane_lines` | 查询车道线列表 | deck_id |
| `get_lane_line_detail` | 查询车道线详情 | lane_line_id |
| `create_lane_line` | 新增车道线 | deck_id, points |
| `update_lane_line` | 编辑车道线 | lane_line_id |
| `delete_lane_line` | 删除车道线 | lane_line_id |
| `get_junction_boxes` | 查询接线盒列表 | deck_id |
| `create_junction_box` | 新建接线盒 | deck_id, db_id |

### 绑定（6 项）
| 工具 | 功能 | 必填参数 |
|------|------|----------|
| `get_unbound_compartment` | 查询未绑定舱室的负载 | system_type |
| `get_unbound_power` | 查询未绑定配电的负载 | deck_id, system_type, compartment_id |
| `bind_compartment` | 绑定负载到舱室 | deck_id, compartment_id, unbound_loads |
| `unbind_compartment` | 从舱室解绑负载 | unbound_loads |
| `bind_power` | 绑定负载到供电设备 | supply_equipment_id, unbound_loads |
| `unbind_power` | 从供电设备解绑负载 | unbound_loads |

> **`system_type` 枚举：** `primary`（一次系统）| `secondary`（二次系统）| `lighting`（照明系统）

### 组合工具（1 项）
| 工具 | 功能 | pipeline | 必填参数 |
|------|------|----------|----------|
| `full_illumination_design` | 完整照明设计 | `recommend_light_count` → `verify_illuminance` → `layout_lights` | compartment_id, light_type_id, illuminance, utilization, maintenance, layout_type |

组合工具自动串联多个 API 调用，每步结果注入下一步：
- Step 1: `recommend_light_count` → 返回推荐灯数 `count`
- Step 2: `verify_illuminance` ← 收到上一步的 `count`，组装为 `light_type_count`
- Step 3: `layout_lights` ← 收到上一步的 `count`，生成灯具位置

### 导入记录（2 项）、画布（1 项）、测量（2 项）、组合查询（3 项）
| 工具 | 功能 | 必填参数 |
|------|------|----------|
| `get_records` | 查询导入记录 | 无 |
| `get_record_snapshot` | 查询记录回溯 | 无 |
| `get_canvas_all` | 获取画布完整数据 | 无 |
| `measure_point` | 点距测量 | deck_id, start_point, end_point |
| `measure_compartment` | 舱室距离测量 | start_deck_id, start_compartment_id, end_deck_id, end_compartment_id |
| `get_all_compartments` | 获取所有甲板全部舱室 | 无 |
| `get_compartment_info` | 按名称查找舱室 | compartment_name |
| `get_system_status` | 获取系统状态 | 无 |

---

## 本地开发调用方式

以下命令只用于显式开启 EID development mode 的诊断，或由服务端 EID 工具执行器
内部调用。生产对话不得通过通用 terminal 复制执行这些命令。

```bash
# 单个工具（record_id 由 Hermes 服务端上下文注入，不出现在参数中）
python3 scripts/tool_dispatcher.py --tool <名称> --params '<JSON>'

# 查询甲板列表
python3 scripts/tool_dispatcher.py --tool get_decks --params '{}'

# 查询舱室列表（DECK 4）
python3 scripts/tool_dispatcher.py --tool get_compartments --params '{"deck_id":"DECK 4"}'

# 查询灯具列表
python3 scripts/tool_dispatcher.py --tool get_lights --params '{"deck_id":"DECK 5"}'

# 写操作（修改数据库），加 --confirm，用 echo "y" | 管道传 y
# （terminal 命令不支持交互式 stdin，必须用管道注入）
echo "y" | python3 scripts/tool_dispatcher.py --tool update_deck --params '{"deck_id":"DECK 5","deck_name":"新名称"}' --confirm

# 仅校验参数（不调用 API）
python3 scripts/tool_dispatcher.py --tool get_lights --params '{"deck_id":"DECK 4"}' --validate-only

# 查看工具帮助
python3 scripts/tool_dispatcher.py --tool-help get_lights

# 列出所有工具
python3 scripts/tool_dispatcher.py --list
```

运行时上下文契约：
- `HERMES_EID_SUBJECT` 和 `HERMES_EID_RECORD_ID` 必须由 Hermes 服务端为当前调用注入。
- `HERMES_EID_TENANT` 可选；生产调用必须有 `HERMES_EID_DELEGATION`，委托令牌只进入请求头。
- 只有显式开启 `HERMES_WEBUI_EID_DEVELOPMENT_MODE` 时，才允许在无委托令牌的本地开发流程中调用。
- 不在命令行、日志、提示词或输出中打印上述环境变量的值。
- `--params` 中出现 `record_id`、`user_id`、`eid_subject`、`eid_tenant` 或 `delegation_token` 时，调度器必须拒绝调用。

---

## 旧名兼容映射

以下旧工具名会自动映射到新 API 工具：

| 旧名（v2-v3） | 新 API 工具 | 说明 |
|---------------|-------------|------|
| `query_compartment_info` | `get_compartment_info` | 按名称查舱室 |
| `query_current_system_status` | `get_system_status` | 系统状态 |
| `query_light_library_count` | `get_light_types` | 灯具类型 |
| `calculate_lamp_count` | `recommend_light_count` | 灯具数量推荐 |
| `check_illuminance` | `verify_illuminance` | 照度验算 |
| `auto_layout` | `layout_lights` | 灯具布局 |
| `modify_compartment_info` | `update_compartment` | 编辑舱室 |
| `delete_compartment` | `delete_compartment` | 删除舱室 |
| `get_all_compartments` | `get_all_compartments` | 全部舱室 |

> **注意：** 旧工具的 `compartment_name` 在新 API 中变为 `compartment_id`（唯一ID）。如需按名称查找，使用 `get_compartment_info` 先通过名称定位。

---

## LLM 路由逻辑

1. 理解用户意图 → 匹配上表中的工具
2. 提取参数（从用户自然语言中提取 deck_id、compartment_id 等）
3. **写操作判断：** 如果工具为目标写操作（update_*/create_*/delete_*/bind_*/unbind_*/layout_*），先向用户展示确认表格，再用 `clarify(choices=["✅ Allow (确认执行)", "❌ Reject (取消操作)"])` 工具弹出现代化选择列表获取确认，确认后再调用。详见「写操作用户确认机制」
4. 生产环境调用对应的 Hermes EID 专用工具；服务端内部适配器再调用 `tool_dispatcher.py`。本地开发写操作必须加 `--confirm`
5. 如果返回 `validation_error`：
   - 向用户展示结构化表格：缺失参数 + 可用选项
   - 引导用户补充后重试
6. 如果返回 `invalid_enum`：
   - 告知用户参数值不合法 + 显示允许值
   - 引导用户选择正确的值
7. 如果返回 `success`：
   - 展示数据（优先结构化表格）

### 参数校验响应模板

```json
// 缺参数
{
  "status": "validation_error",
  "missing": ["deck_id"],
  "missing_details": ["  · deck_id — 甲板ID"],
  "available_decks": [
    {"deck_id": "DECK 4", "deck_height": 13.2},
    {"deck_id": "DECK 5", "deck_height": 15.0}
  ]
}

// 枚举值错误
{
  "status": "validation_error",
  "message": "参数值不在有效范围内: system_type=invalid，允许值: ['primary', 'secondary', 'lighting']"
}
```

### 常用 system_type 说明

| 值 | 说明 | 包含元素 |
|:---|:-----|:---------|
| `primary` | 一次系统 | 主配电板、分配电箱、大功率负载 |
| `secondary` | 二次系统 | 分配电箱、小功率负载 |
| `lighting` | 照明系统 | 灯具、车道线、梁线 |
| 不传 | 全部 | 三个系统合并 |

## 组合工具说明

组合工具（如 `full_illumination_design`）在 `tool_dispatcher.py` 的 `COMPOSITE_MAP` 中定义，通过 `run_composite()` 串联多个原子 API 调用。

参数传递规则：
- 用户传入的参数（compartment_id, light_type_id 等）每步共享
- 上一步 API 返回的关键值（如 `count`）自动注入下一步
- 任一步返回错误则终止 pipeline

当前组合工具：

| 工具 | pipeline |
|------|----------|
| `full_illumination_design` | `recommend_light_count` → `verify_illuminance` → `layout_lights` |

## 写操作用户确认机制

所有涉及数据库修改的操作都必须先取得用户确认。生产环境确认后调用 EID 专用写工具；
下面的终端双层确认只适用于显式 development mode 或服务端工具适配器测试。

### 第1层：LLM 通过 clarify 工具确认

LLM 调用工具前，先向用户展示操作摘要，然后使用 `clarify` 工具弹出现代化选择列表：

```
🖊 即将执行写入操作 — 请确认

| 项目 | 内容 |
|:----|:------|
| 操作 | update_deck — 编辑甲板信息 |
| 目标 | DECK 5 |
| 变更 | deck_name: DECK 5 → 新名称 |
```

`clarify` 的 choices 设置为 `["✅ Allow (确认执行)", "❌ Reject (取消操作)"]`。

用户选择：
- **Allow** → LLM 执行第2层 + 实际调用
- **Reject** → LLM 告知用户操作已取消

### 第2层：tool_dispatcher.py 终端确认（管道传 y）

用户通过 clarify 确认后，LLM 调用 tool 时使用 `echo "y" |` 管道传 `y` 给 `--confirm` 提示符：

```bash
echo "y" | python3 scripts/tool_dispatcher.py --tool update_deck \
  --params '{"deck_id":"DECK 5","deck_name":"新名称"}' --confirm
```

- termial 命令不支持交互式 stdin，所以必须用 `echo "y" |` 管道注入
- dispatcher 的 `--confirm` 会读取 stdin 中的 `y` 自动确认
- 管道写法固定为标准操作方式

### 完整确认流程示例

```
用户: 删除WATERMIST VALVE CENTER MACHINERY_hermes这个舱室

助手: 🖊 即将执行写入操作 — 请确认
      | 项目 | 内容 |
      | 操作 | delete_compartment — 删除舱室 |
      | 甲板 | DECK 4 |
      | 目标 | WATERMIST VALVE CENTER MACHINERY_hermes |
      
      [调用 clarify(choices=["✅ Allow", "❌ Reject"])]

用户: ✅ Allow

助手: [执行 echo "y" | python3 ... --confirm]
      ✅ 删除成功！
```

### 涉及工具

| 类别 | 工具 |
|:----|:------|
| 甲板 | update_deck |
| 舱室 | create_compartment, update_compartment, delete_compartment |
| 负载 | update_load |
| 灯具 | update_light, delete_lights, layout_lights, update_lights_layout |
| 绑定 | bind_compartment, unbind_compartment, bind_power, unbind_power |
| 梁线 | create_beam_line, update_beam_line, delete_beam_line |
| 车道线 | create_lane_line, update_lane_line, delete_lane_line |
| 接线盒 | create_junction_box |
| 编辑模式 | edit_mode_start, edit_mode_exit |
| 图纸解析 | primary_parse, submit_preview, secondary_parse, recognition |
| 组合工具 | full_illumination_design（内部含 layout_lights） |

### 例外（只读，不需要确认）

`get_*`、`search_*`、`recommend_light_count`、`verify_illuminance`、`measure_*` — 即使传了 `--confirm` 也会自动跳过确认。

---

## 已知问题与陷阱

### 1. 参数含 `&` 符号时 shell 解释为后台任务

舱室 ID 中可能包含 `&`（如 `CHAIN LOCKER & MUD BOX ACCESS_...`），直接内联 JSON 传给 `--params` 时，`&` 会被 bash 解释为后台运行符号，导致命令失败或退出码为 -1。

**应对策略：** 将参数写入临时 JSON 文件，再用 `$(cat ...)` 传入：
```bash
echo '{"deck_id":"DECK 4","compartment_id":"CHAIN LOCKER & MUD BOX ACCESS_..."}' > /tmp/params.json
python3 scripts/tool_dispatcher.py --tool get_lights --params "$(cat /tmp/params.json)"
```
或使用 `execute_code` + `terminal` 工具写文件再读。

### 2. param_validator 与 api_client 签名不一致

部分工具的 `param_validator.py` 中标注为**可选**的参数，在 `api_client.py` 的函数签名中却是**必填位置参数**（无默认值），导致调用时出现 `missing X required positional arguments` 错误。

当前受影响的工具：
| 工具 | param_validator 标注 | api_client 要求 |
|------|:-------------------:|:---------------:|
| `get_lights` | compartment_id=可选 | compartment_id=必填 |
| `get_loads` | compartment_id=可选 | compartment_id=必填 |
| `update_light` | light_name/compart-ment_id/light_type_id/points=可选 | 全部必填 |

**应对策略：** 调用这些工具时显式传入空字符串 `""` 作为可选参数的值，绕过签名限制。**不要主动修复 api_client/param_validator 代码** — 用户会自己提出修改需求。

### 3. 旧参数名不适配新 API

旧工具使用 `compartment_name`（舱室名称字符串），新 API 使用 `compartment_id`（唯一标识符）。`get_compartment_info` 提供了按名称查找的封装，但返回数据的结构不同。在从旧工作流迁移时需注意参数名变更。

### 4. DECK 4 舱室数量较多（36个）

DECK 4 有 36 个舱室、DECK 5 有 6 个、DECK 6 有 27 个。批量查询时注意输出过大。

### 5. 部分 API 端点标注为"未完成"

接口文档中标注"未完成"的端点（如梁线/车道线增删改、接线盒等）虽然 api_client 已封装函数，但后端可能尚未实现，调用可能返回 4002。

### 6. DELETE 操作带 body 是合法的

`DELETE` 请求可以携带 JSON body。后端 API 明确支持 `DELETE /decks/lights` 带 `{record_id, light_ids}`。`api_client.py` 的 `_delete()` 函数已支持 `data=` 参数，调用时传 body 即可：

```python
_delete("decks/lights", data={"record_id": "xxx", "light_ids": [...]})
```

不要在 DELETE 上走 POST 绕路（如 `POST .../delete` 模式）。

### 7. 查询返回必须全量展示

用户对查询操作的要求：API 返回的**所有字段**都要展示，不要截断、不要只展示部分摘要、不要挑着显示。用结构化表格呈现数据。如果数据量特别大（如 DECK 4 的 36 个舱室），可以先总览计数再逐项展示。

### 8. 全参必填后无隐藏默认值陷阱

v4.1 起所有业务函数参数均为必填位置参数，无 `= None`、`**kwargs`、默认值。这消除了之前因 validator 标记为可选而 api_client 要求必填导致的不一致问题。所有参数必须显式传入，包括 `compartment_id`、`system_type` 等。

查询甲板全部负载时传空字符串作为 compartment_id：
```bash
python3 scripts/tool_dispatcher.py --tool get_loads --params '{"deck_id":"DECK 4","compartment_id":""}'
```

### 9. create_compartment 的 points 参数需构成有效封闭多边形

`create_compartment` 的 `points` 参数定义舱室轮廓。如果传入的点坐标形成的是**对角线**（每步同时增减 X 和 Y，如 `[[10,20],[30,40],[50,60],[70,80]]`），这些点**不围成任何面积**，结果 `compartment_area: 0.0`。

**正确做法 — 矩形舱室应提供四个角点（闭合回路）：**

```bash
# ✅ 四角矩形（按顺序环绕）
python3 scripts/tool_dispatcher.py --tool create_compartment --params '{
  "deck_id":"DECK 4",
  "points":[[10,20],[70,20],[70,80],[10,80]]
}'
```

**对比：**
| points 示例 | 形状 | 结果 |
|:-----------|:----:|:----:|
| `[[10,20],[70,20],[70,80],[10,80]]` | 矩形 60×60 | 面积 ✅ |
| `[[10,20],[30,40],[50,60],[70,80]]` | 斜线（无包围区域） | 面积 = 0.0 ❌ |

口诀：**先固 X 后动 Y 才是矩形，X 和 Y 一起动是斜线。**

### 10. create_compartment 不支持自定义 compartment_id

`create_compartment` 只接受 `record_id`, `deck_id`, `points` 三个参数，**不支持**用户自定义 `compartment_id`。后端自动生成 ID（格式如 `WATERMIST VALVE CENTER MACHINERY_DECK 4_FR40+1_P1790`）。

如果用户需要指定自定义舱室ID，需先在 `api_client.py` 和 `param_validator.py` 中扩展该工具。

### 11. search_deck 拒绝空字符串 keyword

`search_deck` 的 `keyword` 参数在 param_validator 中标记为必填，且校验逻辑使用 Python 真值检查。传空字符串 `""` 会被判定为"缺少必填参数"。

**解决办法：** 使用通配符 `"*"` 代替空字符串搜索全部：
```bash
python3 scripts/tool_dispatcher.py --tool search_deck --params '{"system_type":"primary","keyword":"*","deck_id":"DECK 4"}'
```

注意：即使用 `"*"`，search_deck 也只能搜索到舱室列表（带名称），主配电板、分配电箱、负载等更细粒度的元件不一定返回。如需完整的设备数据，用单独的 `get_main_switchboards` / `get_distribution_boards` / `get_loads` 查询。

### 12. 删除舱室后关联引用可能仍然存在

使用 `delete_compartment` 删除舱室后，该舱室仍可能出现在 `get_distribution_board_connected` 的返回结果中。这是因为后端不会级联清理舱室→分配电箱→负载的绑定关系，被删除舱室的负载ID和供电关系成为"孤儿引用"。

**应对：** 删除舱室后，如有必要，需手动解绑该舱室下的负载（使用 `unbind_compartment` / `unbind_power`），再通过 `update_load` 将负载的 `compartment_id` 重新指向有效舱室。

### 13. get_canvas_all 输出量极大（可能 >4MB）

`get_canvas_all` 返回画布全部嵌套数据，包含所有甲板、舱室顶点坐标（每个舱室数十到上百个坐标点）。DECK 6 的一个大舱室（如最右侧轮廓）就有数百个点坐标，总输出可超过 4MB。

**应对策略：**
- 如只需特定类型数据（主配电板、负载等），优先使用对应的独立查询工具
- 如确实需要全量数据，使用 `execute_code` + `json_parse` 提取摘要，不要在 terminal 中直接输出
- 示例：先 `get_canvas_all` 获取数据 → 用 Python 脚本按甲板/类型汇总展示

### 14. terminal 输出截断（~50KB 上限）

**问题：** `terminal` 工具对 stdout/stderr 有约 50KB 的上限。当查询返回大量 JSON 数据时（如 `get_lights` 返回 220 盏灯 ~89KB），输出会被截断，截断后的 JSON 无法用 `json_parse` 直接解析。

**表现：** `json.decoder.JSONDecodeError` 或输出末尾标记 `[OUTPUT TRUNCATED - N chars omitted]`。

**应对策略：**
- 把完整 JSON 写入临时文件，再用 `execute_code` + Python 脚本读取并汇总

```bash
# 写入临时文件
python3 scripts/tool_dispatcher.py --tool get_lights --params '{"deck_id":"DECK 4","compartment_id":""}' > /tmp/deck4_lights.json

# 在 execute_code 中用 Python 读取汇总
# 见 references/batch-querying-pattern.md
```

- 该文件中转方式仅用于本地开发诊断；生产环境禁止用 `execute_code` 或通用 `terminal` 绕过 EID 专用工具

### 15. light_type_id 使用 ID 而非显示名称

`get_light_types` 返回灯具类型中，`light_type_id` 是唯一标识符（如 `type_02`），`type` 是显示名称（如"泛光灯B"）。

**所有需要指定灯具类型的地方必须使用 `light_type_id`（ID），不是 `type`（名称）。**

```bash
# ✅ 正确 — 用 ID
python3 scripts/tool_dispatcher.py --tool recommend_light_count --params '{
  "compartment_id":"xxx","light_type_id":"type_02","illuminance":200
}'

# ❌ 错误 — 用名称导致"灯具类型不存在"
python3 scripts/tool_dispatcher.py --tool recommend_light_count --params '{
  "compartment_id":"xxx","light_type_id":"泛光灯B","illuminance":200
}'
```

可用灯具类型通过 `get_light_types` 实时查询，不要硬编码名称或 ID。

### 16. composite 工具每步只传需要的参数

`full_illumination_design` 的 `_prepare_composite_params` 按步骤分别构造参数：

| 步骤 | 传入参数 | 来源 |
|------|----------|------|
| `recommend_light_count` | `record_id, compartment_id, light_type_id, illuminance, utilization, maintenance` | 服务端 record + 用户参数 |
| `verify_illuminance` | `record_id, compartment_id, illuminance, utilization, maintenance, light_type_count` | 服务端 record + 用户参数 + 上一步 count |
| `layout_lights` | `record_id, compartment_id, light_type_count, layout_type` | 服务端 record + 用户参数 + 上一步 count |

不共享参数（如 `layout_type` 不传给第一步，`light_type_id` 不传给后两步），避免"unexpected keyword argument"。

### 17. full_illumination_design 实测参考

已有两个实测案例：

**案例 A — CHAIN LOCKER**（107盏泛光灯B）
详情见 `references/full-illumination-design-example.md`。
```
Step 1: recommend_light_count → 107盏
Step 2: verify_illuminance → 201.16lx ≥ 200lx ✅
Step 3: layout_lights → 107盏灯位置（uniform布局）
```

**案例 B — WATERMIST VALVE CENTER MACHINERY**（399盏泛光灯B）
详情见 `references/full-illumination-design-watermist-example.md`。
```
Step 1: recommend_light_count → 399盏
Step 2: verify_illuminance → 200.3lx ≥ 200lx ✅
Step 3: layout_lights → 399盏灯位置（uniform布局）
```

### 18. update_light 需传入所有字段，即使只改一个字段

`update_light` 的函数签名要求**所有字段**作为位置参数传入：
```python
def update_light(record_id, light_id, light_name, compartment_id, light_type_id, points):
```

即使只改 `light_name`，也必须传入 `compartment_id`、`light_type_id` 和 `points`（带上现有值）。

**正确做法：**
```bash
python3 scripts/tool_dispatcher.py --tool update_light --params '{
  "light_id":"xxx",
  "light_name":"新名称",
  "compartment_id":"原舱室ID",
  "light_type_id":"type_02",
  "points":[4696.0, 431.0]
}'
```

先查 `get_light_detail` 获取当前值，再填入不变字段。

### 19. get_lights 和 get_loads 传入空字符串 "" 作为 compartment_id

`param_validator` 中 `get_lights`/`get_loads` 的 `compartment_id` 标记为可选，但因遵循"全参必填"规则，`api_client` 将其设为必填位置参数。

**查询甲板所有灯具/负载时，传空字符串 `""` 作为 compartment_id：**
```bash
python3 scripts/tool_dispatcher.py --tool get_lights --params '{"deck_id":"DECK 4","compartment_id":""}'
python3 scripts/tool_dispatcher.py --tool get_loads --params '{"deck_id":"DECK 4","compartment_id":""}'
```

### 20. get_unbound_compartment 无 deck_id 过滤且只接受 primary/secondary

`get_unbound_compartment` 有两个限制：

**限制 A — 只接受 primary/secondary：** `system_type` 只接受 `primary`（一次系统）和 `secondary`（二次系统），**不接受 `lighting`（照明系统）**。传入 `"lighting"` 时返回 `validation_error`。

> 与 `get_unbound_power`（同时接受 primary/secondary/lighting）不同。

**限制 B — 无 deck_id 参数：** 返回**所有甲板**的未绑定负载，无法直接按甲板过滤。

**应对策略 — 交叉引用法：**
1. 用 `get_loads(deck_id="DECK X", compartment_id="")` 获取该甲板所有负载ID
2. 用 `get_unbound_compartment(system_type="...")` 获取所有未绑定舱室的负载ID
3. 取交集：哪些未绑定负载在目标甲板上

详见 `references/deck-level-unbound-crossref.md`。

### 21. 大量数据先展示前N条，等用户进一步指示

当查询返回大量条目时（如 220 盏灯），不要直接全部输出。先展示**前 10 条**的详细表格，再给出按类型/舱室的汇总统计，让用户决定是否需要查看更多。

### 22. update_load 不支持修改电气参数

`update_load` 只支持编辑：`load_name`, `type`, `compartment_id`, `supply_equipment_id`。

**不支持修改的电气参数（API 无对应字段）：**
- `rated_current`（额定电流）
- `rated_power`（额定功率）
- `rated_voltage`（额定电压）
- `power_factor`（功率因数）

用户要求改这些时，告知当前 API 限制。按用户偏好，**不要主动提议修复代码** — 等用户自己提出。

```
用户: 把这个负载的额定电流改成12.8A
助手: update_load 不支持修改 rated_current，当前仅支持编辑：load_name, type, compartment_id, supply_equipment_id
```

### 23. 更换布局方式需先删除旧灯具再重新生成

`layout_lights` 是 **POST 操作**，每次调用会**创建新灯具**而非替换旧灯。没有独立的"更新布局类型"API。

**如需更改布局类型（如 uniform → one_click）：**

1. 查询该舱室当前所有灯具 ID
2. 用 `delete_lights` 批量删除所有灯具
3. 再用 `layout_lights` 以新布局类型重新生成

**实测示例（399盏 uniform → one_click）：**
```bash
# 获取灯具ID
python3 scripts/tool_dispatcher.py --tool get_lights \
  --params '{"deck_id":"DECK 4","compartment_id":"<舱室ID>"}' > /tmp/lights.json

# 提取ID并写入文件（避免shell参数过长）
python3 -c "
import json
with open('/tmp/lights.json') as f:
    d = json.loads(f.read())
ids = [l['light_id'] for l in d.get('data',[])]
with open('/tmp/ids.json','w') as f:
    json.dump({'light_ids':ids}, f)
print(f'共{len(ids)}盏灯')
"

# 删除旧灯
python3 scripts/tool_dispatcher.py --tool delete_lights \
  --params "$(cat /tmp/ids.json)"

# 重新布局
python3 scripts/tool_dispatcher.py --tool layout_lights \
  --params '{"compartment_id":"<舱室ID>","light_type_count":[{"light_type_id":"type_02","count":399}],"layout_type":"one_click"}'
```

### 24. 本地开发中 `--confirm` 的非交互式用法

`tool_dispatcher.py` 的 `--confirm` 标志会等待终端标准输入（`input()` 或 `sys.stdin.readline()`）来确认写操作。在 Hermes 的 `terminal` 工具环境下：

**错误做法 — 用 background + submit 方式：**
`terminal(background=true)` 启动的进程在打印提示后立即退出，来不及通过 `process(action='submit', data='y')` 发送确认。因为 `--confirm` 内部调用 `input()` 等待键盘输入，但 `process(action='submit')` 发送得太慢，进程已经退出了。

**正确做法 — 管道传 `y`：**
```bash
echo "y" | python3 scripts/tool_dispatcher.py --tool <tool_name> --params '<json>' --confirm
```

实测示例（删除舱室）：
```bash
echo "y" | python3 scripts/tool_dispatcher.py --tool delete_compartment \
  --params '{"deck_id":"DECK 4","compartment_id":"WATERMIST VALVE CENTER MACHINERY_DECK 4_FR40+1_P1790"}' \
  --confirm
```

`echo "y"` 将字符 `y` + 换行符通过管道传递给 Python 的 `input()`，触发确认流程继续执行。

### 25. update_load 在无舱室负载时因 API 校验拒绝空字符串

`update_load` 通过 `PUT /decks/loads` 调用，后端 API 使用 Pydantic 校验 `compartment_id` 字段要求 `min_length=1`（不能为空字符串 `\"\"`）。但当负载未绑定舱室时出现三层困境：

**三层困境：**
1. `get_load_detail` 返回 `compartment_name: null` — 无舱室
2. `get_load_detail` **不返回** `compartment_id` 或 `supply_equipment_id`（只返回名称，不返回ID）
3. 后端 API 拒绝空字符串 `compartment_id: ""`（`4001: String should have at least 1 character`）
4. 传不存在的 ID（如 `"none"`）也不行（`4002: 舱室不存在`）

**典型错误链路：**
```
用户：把ST/318.014的名称改成xxx
  → update_load 报 missing 3 required: type, compartment_id, supply_equipment_id
  → 补全参数 → API 4001: "compartment_id: String should have at least 1 character"
  → 换虚假ID → API 4002: "舱室不存在: none"
```

**应对策略：** 先绑定舱室再更新。让用户选一个舱室绑定，然后调用 update_load（带上有效的 compartment_id）同时完成绑定和改名。绑定前通过 `get_compartments` 查可用舱室列表供用户选择。

```bash
# 1. 查舱室列表让用户选
python3 scripts/tool_dispatcher.py --tool get_compartments --params '{"deck_id":"DECK 4"}'

# 2. 绑定+改名一步到位（用所选舱室的 compartment_id）
echo "y" | python3 scripts/tool_dispatcher.py --tool update_load \
  --params '{"load_id":"xxx","load_name":"新名称","type":"默认类型","compartment_id":"<有效舱室ID>","supply_equipment_id":"<有效供电设备ID>"}' --confirm
```

> 注意：`supply_equipment_id` 也需要从 `get_distribution_boards` / `get_main_switchboards` 先查到，`get_load_detail` 只返回名称不返回ID。

### 26. get_load_detail / get_compartment_detail 不返回关联资源 ID

`get_load_detail` 返回 `supply_equipment_name`（如 `"Power Board"`）但不返回 `supply_equipment_id`；返回 `compartment_name` 但不返回 `compartment_id`。

`get_compartment_detail` 返回 `light_count`、`distribution_board_count`、`main_switch_board_count` 等计数，但不返回具体的 ID 列表。

**影响：** 调用 `update_load`、`update_light` 等需要 ID 参数的写操作时，仅靠 detail 查询无法获取 ID（只有名称），必须额外调用对应的**列表查询工具**来获取 ID。

**需要反向查 ID 的场景：**

| 工具 | 需要的 ID | 从哪查（名称→ID） |
|:------------|:---------|:-------|
| `update_load` 的 `supply_equipment_id` | 供电设备 ID | `get_distribution_boards` → 按名称匹配 |
| `update_load` 的 `compartment_id` | 舱室 ID | `get_compartments` → 按名称匹配 |
| `update_light` 的 `compartment_id` | 舱室 ID | `get_compartments` → 按名称匹配 |

**示例：获取 "Power Board" 的 ID（PB1011）：**
```bash
python3 scripts/tool_dispatcher.py --tool get_distribution_boards \
  --params '{"deck_id":"DECK 4","compartment_id":""}'
# → PB1011 | Power Board | EL. EQ.  ← 从名称匹配到 ID
```

### 用户偏好：不要主动修复脚本/代码

用户明确表示不希望 AI 主动提出修复

旧版基于 PostgreSQL + approval_log 的审批流程（approve_pending/reject_pending）已废弃。新 API 的写入操作（POST/PUT/DELETE）直接由后端处理，不再需要本地审批流程。LLM 应在执行写操作前向用户确认。

---

### api_client.py 文档规范

每个 API 封装函数的 docstring 必须包含以下内容：

```python
def update_compartment(record_id: str, deck_id: str, compartment_id: str,
                       compartment_name: str, compartment_function: str,
                       points: list) -> dict:
    """
    API: PUT /decks/compartments
    请求体:
    {
        "record_id": "123",                    # 必填 - 记录id
        "deck_id": "1",                        # 必填 - 甲板id
        "compartment_id": "3",                 # 必填 - 舱室id
        "compartment_name": "新舱室",           # 必填 - 舱室名称
        "compartment_function": "居住舱室",     # 必填 - 功能区
        "points": [[10,20],[30,20],[30,60],[10,60]]  # 必填 - 顶点坐标
    }
    响应: {code: 0, data: {record_id, deck_id, compartment_id}}
    """
```

格式要求：
- 第一行: `API: {METHOD} /{path}`
- 请求体/参数: **所有参数标注 `必填`**（不接受"可选"、"非必填"等表述），每行一个字段名 + 中文说明
- 响应: 简要说明返回结构
- 函数签名必须使用**显式位置参数**列出每个 API 字段，禁止使用 `**kwargs` 或 `= None` 默认值

**重要规则：所有业务函数的参数必须为必填位置参数，不允许使用 `= None` 默认值或 `**kwargs`。**
内部调用显式传入由调度器绑定的 `HERMES_EID_RECORD_ID`，不得使用隐藏默认值或模型提供的记录 ID。

**API 路径探测规则：** 当 API 返回 404 时，不要假设资源是扁平路径。
必须尝试嵌套路径格式：`/{领域}/{资源}`。
正确: `GET /decks/compartments`、`GET /decks/lights`
错误: `GET /compartments`、`GET /lights`

---

## 文件说明

| 文件 | 作用 |
|------|------|
| `scripts/api_client.py` | **【活跃】** HTTP API 客户端：封装所有 API 调用，v4.1 全参数必填 |
| `scripts/param_validator.py` | **【活跃】** 参数校验模块 |
| `scripts/tool_dispatcher.py` | **【活跃】** 统一调度器：校验 → API → 返回 |
| `references/test-reporting.md` | **【参考】** 全量测试报告生成指南 |
| `references/deck-level-unbound-crossref.md` | **【参考】** get_unbound_compartment 按甲板过滤的交叉引用方案 |
| `references/full-illumination-design-example.md` | **【参考】** 完整照明设计实测记录（CHAIN LOCKER, 107盏泛光灯B） |
| `references/full-illumination-design-watermist-example.md` | **【参考】** WATERMIST VALVE CENTER 完整照明设计实测记录 |
| `SKILL.md` | 本文档 |

> **新增端点时只需在 `api_client.py` 添加函数 + `param_validator.py` 添加校验规则 + `tool_dispatcher.py` 添加映射。** 无需修改废弃文件。
