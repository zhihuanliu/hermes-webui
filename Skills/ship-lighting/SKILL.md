---
name: ship-lighting
description: 船舶电气图纸智能体——查询/编辑甲板、舱室、配电板、负载、灯具、梁线、车道线，
  执行照明设计（推荐数量/验算照度/布局灯具）。触发场景：用户提到 DECK/甲板/舱室/灯具/
  配电板/照明设计/船舶图纸/record_id，或要求查询/编辑/绑定/解绑这些船舶电气元件时使用。
version: 4.1
author: Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [ship, lighting, deck, compartment, load, switchboard, illumination-design]
---

# 船舶照明智能体 v4.1

> 入口文档。详细内容在 [references/](references/) 按需加载。

---

## ⚠️ 元规则（最高优先级）

**不要主动修复 `api_client.py` / `param_validator.py` / `tool_dispatcher.py` 代码。**
报告问题、不要动手，等用户明确提出修改需求。

---

## 强制规范

1. **先加载 skill 再执行** — `skill_view(name='ship-lighting')` 后再处理用户意图。
2. **terminal 调用四项证据** — 脚本绝对路径、完整命令、退出码、关键输出前 10 行。
3. **统一走 dispatcher** — 所有 API 调用必须通过 `tool_dispatcher.py`。**禁止**直接 curl，也禁止直接 import api_client。
4. **EID 集成只使用当前会话绑定的 record。**
  - Hermes 服务端从 iframe 上下文绑定当前会话的 `record_id`。
  - `tool_dispatcher.py` + `param_validator.py` 使用该 record 调用 EID API。
  - 当前运行后端无法传递 record 上下文时，明确拒绝业务操作。

5. **record_id 由 Hermes 服务端提供。**
  - 不猜测、缓存或要求用户在对话中提供 `record_id`。
  - 不允许模型在 `--params` 中传入或覆盖 `record_id`。
  - `tool_dispatcher.py` 只使用当前运行上下文中的 `HERMES_EID_RECORD_ID`。
  - 无 record 上下文时停止调用并提示先打开或选择记录。
  - Hermes profile 只是 Agent 配置，不决定业务 record。
  - `SHIP_LIGHTING_RECORD_ID` 和任何固定默认 record 均不得用于生产业务调用。

6. **查询全量展示** — 所有字段、所有链接结构化表格呈现，不截断、不挑选。大量条目（如 220 盏灯）先展示前 10 条 + 汇总统计。
7. **写操作双层确认** — `clarify(["✅ Allow","❌ Reject"])` → `echo "y" | dispatcher ... --confirm`。详见 [references/write-confirmation.md](references/write-confirmation.md)。
8. **缺参数返回结构化表格** — 引导用户补全：

   ```
   ❌ 查看灯具缺少必要参数
   | 状态 | 缺少参数 | 说明 |
   |:----:|---------|------|
   | ❌ | deck_id | 甲板ID，必填 |

   可用甲板：
     · DECK 4 (13.2m)
     · DECK 5 (15.0m)
     · DECK 6 (18.0m)

   请提供 deck_id
   ```

9. **shell 转义** — 参数含 `&` / `$` / `!` 等特殊字符时（如舱室 ID `CHAIN LOCKER & MUD BOX ...`），先把 JSON 写入 `/tmp/params.json` 再 `--params "$(cat /tmp/params.json)"`，否则 bash 解释为后台符导致命令失败。
10. **大返回中转** — 预期返回 > 50KB 时（如整甲板灯具列表），先 `> /tmp/xxx.json` 重定向到文件，再用 `execute_code` + Python 解析。terminal stdout 约 50KB 截断后 JSON 不可解析。

11. **禁用get_records** - **不允许**使用 `get_records` 获取所有记录。

> 工具参数级别的约定（`compartment_id=""`、`light_type_id` 用 ID、`points` 闭合等）见 [references/tool-catalog.md](references/tool-catalog.md) 的注释和 [references/troubleshooting.md](references/troubleshooting.md)。**调用任何工具前必须查 tool-catalog 确认参数。**

---

## 工具速查（61 项）

按类别。**详细参数表见 [references/tool-catalog.md](references/tool-catalog.md)**。

| 类别 | 数量 | 主要工具 |
|------|:---:|----------|
| 图纸解析 | 4 | `primary_parse`, `submit_preview`, `secondary_parse`, `recognition` |
| 编辑模式 | 2 | `edit_mode_start`, `edit_mode_exit` |
| 甲板 | 3 | `get_decks`, `search_deck`, `update_deck` |
| 舱室 | 5 | `get/create/update/delete_compartment`, `get_compartment_detail` |
| 主配电板 | 3 | `get_main_switchboards` (+ `_detail` / `_connected`) |
| 分配电箱 | 3 | `get_distribution_boards` (+ `_detail` / `_connected`) |
| 负载 | 4 | `get_loads`, `get_load_detail`, `get_loads_with_detail`, `update_load` |
| 灯具 | 9 | `get_lights`, `get_light_types`, `update/delete_light(s)`, `recommend/verify_illuminance`, `layout_lights`, `update_lights_layout` |
| 梁线 | 5 | `get/create/update/delete_beam_line` (+ `_detail`) |
| 车道线 | 5 | `get/create/update/delete_lane_line` (+ `_detail`) |
| 接线盒 | 2 | `get_junction_boxes`, `create_junction_box` |
| 绑定 | 6 | `bind/unbind_compartment`, `bind/unbind_power`, `get_unbound_compartment/_power` |
| 测量 | 2 | `measure_point`, `measure_compartment` |
| 记录/画布/查询 | 7 | `get_records`, `get_record_snapshot`, `get_canvas_all`, `get_all_compartments`, `get_compartment_info`, `get_system_status` |
| 组合 | 1 | `full_illumination_design` |

### 枚举速记

| 参数 | 枚举值 |
|------|--------|
| `system_type` | `primary`(一次) \| `secondary`(二次) \| `lighting`(照明) \| 不传=全部 |
| `layout_type` | `one_click` \| `uniform` \| `lane_beam` |

> **注意：** `get_unbound_compartment` 的 `system_type` **不接受 `lighting`**。

---

## LLM 路由

1. **意图识别** → 从 [tool-catalog.md](references/tool-catalog.md) 匹配工具
2. **参数提取** → 从自然语言抽取 `deck_id`、`compartment_id` 等
3. **写操作判断** → 工具名为 `update_*`/`create_*`/`delete_*`/`bind_*`/`unbind_*`/`layout_*` 时走 [write-confirmation.md](references/write-confirmation.md) 双层确认
4. **调用 dispatcher**（自动注入 record_id；写操作加 `--confirm` 且管道传 `y`）
5. **解析返回：**
   - `validation_error` → 展示缺失参数 + 可用选项引导补全
   - `invalid_enum` → 展示允许值
   - `success` → 结构化表格全量呈现

---

## 文件索引

### 脚本（活跃）

| 文件 | 作用 |
|------|------|
| `scripts/api_client.py` | HTTP 客户端（v4.1 全参必填） |
| `scripts/param_validator.py` | 参数三层校验 |
| `scripts/tool_dispatcher.py` | 统一调度器（校验→API→返回，含 composite） |

### 参考文档（按需）

| 文件 | 何时读 |
|------|--------|
| [references/tool-catalog.md](references/tool-catalog.md) | 调用工具前查参数（强制规范要求） |
| [references/troubleshooting.md](references/troubleshooting.md) | 遇到错误 / 调用前排查陷阱（含批量查询、按甲板过滤未绑定负载等） |
| [references/write-confirmation.md](references/write-confirmation.md) | 任何写操作前 |
| [references/api-reference.md](references/api-reference.md) | 排查 API 行为 / 新增端点（HTTP 路径、Schema、嵌套规则） |
| [references/architecture.md](references/architecture.md) | 调度链 / 校验流程 / composite 机制 / Skill vs Plugin |
| [references/examples.md](references/examples.md) | `full_illumination_design` 实测案例（CHAIN LOCKER 107 盏 + WATERMIST 399 盏） |
| [references/legacy-tool-mapping.md](references/legacy-tool-mapping.md) | 用户用了旧工具名 / 从旧工作流迁移 |
| [references/coding-conventions.md](references/coding-conventions.md) | 维护脚本代码时（docstring 规范、全参必填） |
