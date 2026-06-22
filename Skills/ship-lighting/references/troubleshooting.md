# 已知问题与陷阱

按主题分组。SKILL.md "高频陷阱" 节有快速速记；本文档是完整版。

---

## A. Shell / 传参

### A1. 参数含 `&` 时 shell 解释为后台任务

舱室 ID 中可能包含 `&`（如 `CHAIN LOCKER & MUD BOX ACCESS_...`），直接内联 JSON 传给 `--params` 时，`&` 会被 bash 解释为后台运行符号，导致命令失败或退出码为 -1。

**应对：** 将参数写入临时 JSON 文件，再用 `$(cat ...)` 传入：
```bash
echo '{"deck_id":"DECK 4","compartment_id":"CHAIN LOCKER & MUD BOX ACCESS_..."}' > /tmp/params.json
python3 scripts/tool_dispatcher.py --tool get_lights --params "$(cat /tmp/params.json)"
```

### A2. terminal stdout ~50KB 截断

`terminal` 工具对 stdout/stderr 有约 50KB 的上限。返回大量 JSON 时（如 `get_lights` 返回 220 盏灯 ~89KB）会被截断，无法 `json_parse`。

**表现：** `json.decoder.JSONDecodeError` 或末尾标记 `[OUTPUT TRUNCATED - N chars omitted]`。

**应对：** 写入文件中转，再用 `execute_code` + Python 解析。

```bash
# 写文件
python3 scripts/tool_dispatcher.py --tool get_lights --params '{"deck_id":"DECK 4","compartment_id":""}' > /tmp/deck4_lights.json
```

```python
# execute_code 里读取
from hermes_tools import terminal
import json
with open('/tmp/deck4_lights.json') as f:
    data = json.loads(f.read())
print(json.dumps(data, ensure_ascii=False, indent=2))
```

**批量调用模式：**
- 优先用工具级组合查询（如 `get_loads_with_detail` 一次返回列表+逐条详情，内部自动循环）
- 后备方案：`execute_code` 里循环调用 `terminal()`，每次 `timeout=10`
- f-string 里 JSON 花括号要双写：`--params '{{"key":"{val}"}}'`

### A3. `get_canvas_all` 输出量极大（可能 >4MB）

包含所有甲板、舱室顶点坐标（每舱数十到上百点）。DECK 6 单一大舱室就有数百点。

**应对：** 只需特定类型时用对应独立查询工具；确需全量则文件中转。

---

## B. 写操作确认

### B1. `--confirm` 必须用 `echo "y" |` 管道传

`tool_dispatcher.py` 的 `--confirm` 会调用 `input()` 等待 stdin。

**错误做法：** `terminal(background=true)` + `process(action='submit', data='y')`——进程打印提示后立即退出，来不及接收。

**正确做法：**
```bash
echo "y" | python3 scripts/tool_dispatcher.py --tool delete_compartment \
  --params '{"deck_id":"DECK 4","compartment_id":"..."}' --confirm
```

详细确认流程见 [write-confirmation.md](write-confirmation.md)。

---

## C. 参数 / 字段约定

### C1. v4.1 全参必填（无 `= None` 默认值）

所有业务函数参数均为必填位置参数。查询甲板全部负载时传空字符串：
```bash
python3 scripts/tool_dispatcher.py --tool get_loads --params '{"deck_id":"DECK 4","compartment_id":""}'
```

### C2. `get_lights` / `get_loads` 的 `compartment_id` 传 `""`

`param_validator` 标可选、`api_client` 必填——传空字符串绕过。

### C3. `search_deck` 拒绝空字符串 keyword

校验逻辑用 Python 真值检查，`""` 判为缺参。**用通配符 `"*"`：**
```bash
python3 scripts/tool_dispatcher.py --tool search_deck --params '{"system_type":"primary","keyword":"*","deck_id":"DECK 4"}'
```

注意：即使 `"*"` 也只返回舱室列表，更细粒度元件需单独的 `get_main_switchboards` / `get_distribution_boards` / `get_loads`。

### C4. `light_type_id` 用 ID，不用名称

`get_light_types` 返回中，`light_type_id` 是唯一标识符（如 `type_02`），`type` 是显示名称（如"泛光灯B"）。

```bash
# ✅ 正确
--params '{"compartment_id":"xxx","light_type_id":"type_02","illuminance":200}'
# ❌ 错误 — "灯具类型不存在"
--params '{"compartment_id":"xxx","light_type_id":"泛光灯B","illuminance":200}'
```

### C5. `update_light` / `update_load` 需传全字段

签名要求所有字段为位置参数。即使只改 `light_name`，也必须传入 `compartment_id`、`light_type_id`、`points`。

**做法：** 先 `get_light_detail` / `get_load_detail` 取现值，再覆盖目标字段。

### C6. `get_load_detail` / `get_compartment_detail` 不返回关联资源 ID

只返回 `*_name` 不返回 `*_id`。需要 ID 时必须额外查列表：

| 工具 | 需要的 ID | 从哪查 |
|------|----------|--------|
| `update_load.supply_equipment_id` | 供电设备 ID | `get_distribution_boards` → 名称匹配 |
| `update_load.compartment_id` | 舱室 ID | `get_compartments` → 名称匹配 |
| `update_light.compartment_id` | 舱室 ID | `get_compartments` → 名称匹配 |

### C7. `update_load` 不支持电气参数

只支持 `load_name`, `type`, `compartment_id`, `supply_equipment_id`。**不支持** `rated_current/power/voltage`、`power_factor`。

按用户偏好：告知限制，**不要主动提议修复代码**。

### C8. `update_load` 在无舱室负载时无解

后端 Pydantic 校验 `compartment_id` 要求 `min_length=1`。当负载未绑定舱室时：
1. `get_load_detail` 返回 `compartment_name: null`，且**不返回** `compartment_id`/`supply_equipment_id`
2. 空字符串 → API 4001
3. 假 ID → API 4002

**应对：** 先 `get_compartments` 让用户选一个，再 `update_load` 同时绑定+改名。

---

## D. 几何 / 数据语义

### D1. `create_compartment` points 必须围成闭合多边形

斜线（每步同时增减 X/Y）不围成面积，结果 `compartment_area: 0.0`。

**正确：四角矩形按顺序环绕**
```bash
# ✅ 矩形 60×60
--params '{"deck_id":"DECK 4","points":[[10,20],[70,20],[70,80],[10,80]]}'
# ❌ 斜线（面积=0）
--params '{"deck_id":"DECK 4","points":[[10,20],[30,40],[50,60],[70,80]]}'
```

**口诀：先固 X 后动 Y 才是矩形，X 和 Y 一起动是斜线。**

### D2. `create_compartment` 不支持自定义 `compartment_id`

只接受 `record_id`, `deck_id`, `points`。后端自动生成（格式如 `WATERMIST VALVE CENTER MACHINERY_DECK 4_FR40+1_P1790`）。

### D3. 更换灯具布局必须先删后建

`layout_lights` 是 POST——每次创建新灯而非替换。无独立"更新布局类型" API。

```bash
# 1. 查现有 light_id（写文件避免参数过长）
python3 scripts/tool_dispatcher.py --tool get_lights --params '{"deck_id":"DECK 4","compartment_id":"<舱>"}' > /tmp/lights.json
python3 -c "
import json
with open('/tmp/lights.json') as f: d=json.loads(f.read())
ids=[l['light_id'] for l in d.get('data',[])]
with open('/tmp/ids.json','w') as f: json.dump({'light_ids':ids}, f)
"
# 2. 删旧
python3 scripts/tool_dispatcher.py --tool delete_lights --params "$(cat /tmp/ids.json)"
# 3. 新布局
python3 scripts/tool_dispatcher.py --tool layout_lights --params '{"compartment_id":"<舱>","light_type_count":[{"light_type_id":"type_02","count":399}],"layout_type":"one_click"}'
```

### D4. 删除舱室后关联引用残留

`delete_compartment` 不级联清理舱室→分配电箱→负载绑定。被删舱室的负载 ID 和供电关系成为孤儿引用，仍出现在 `get_distribution_board_connected` 返回中。

**应对：** 删除前/后手动 `unbind_compartment` / `unbind_power`，再 `update_load` 把负载 `compartment_id` 指向有效舱室。

### D5. DELETE 请求可以带 body

后端明确支持 `DELETE /decks/lights` 带 `{record_id, light_ids}`。`api_client._delete()` 已支持 `data=`。

**不要走 `POST .../delete` 绕路。**

### D6. DECK 数据量参考

DECK 4 有 36 个舱室、DECK 5 有 6 个、DECK 6 有 27 个。批量查询注意输出。

---

## E. 路由 / 绑定关系

### E1. `get_unbound_compartment` 无 deck_id 过滤 + 只接受 primary/secondary

返回**所有甲板**未绑定负载，且 `system_type` 不接受 `lighting`（与 `get_unbound_power` 不同）。

**按甲板过滤方案 — 交叉引用：** 取 `get_loads(deck_id=...)` 与 `get_unbound_compartment(...)` 的 `load_id` 集合交集。

```python
from hermes_tools import terminal
import json

# 该甲板所有负载
r1 = terminal('python3 scripts/tool_dispatcher.py --tool get_loads '
              '--params \'{"deck_id":"DECK 4","compartment_id":""}\'')
deck_loads = json.loads(r1['output'])['data']

# 所有未绑定负载（指定 system_type）
r2 = terminal('python3 scripts/tool_dispatcher.py --tool get_unbound_compartment '
              '--params \'{"system_type":"secondary"}\'')
unbound_ids = {l['load_id'] for l in json.loads(r2['output'])['data']['loads']}

# 取交集
deck_unbound = [l for l in deck_loads if l['load_id'] in unbound_ids]
deck_bound   = [l for l in deck_loads if l['load_id'] not in unbound_ids]
```

> 替代方案：未绑定列表 < 20 时，循环 `get_load_detail` 看 `deck_name` 字段过滤。负载多时（50+）交叉引用更快，只要 2 次 API 调用。

### E2. 部分端点标注"未完成"

梁线/车道线增删改、接线盒等虽 api_client 已封装函数，后端可能未实现，调用可能返回 4002。

### E3. 旧 `compartment_name` → 新 `compartment_id`

旧工具用名称字符串，新 API 用唯一 ID。迁移时通过 `get_compartment_info(compartment_name=...)` 由名称定位 ID。

---

## F. 展示规范

### F1. 查询返回必须全量展示

用户明确要求：所有字段、所有链接都展示，不截断、不挑选。结构化表格呈现。数据量特别大时可先总览计数再逐项。

### F2. 大量条目分页展示

如 220 盏灯，先展示**前 10 条**详细 + 按类型/舱室汇总统计，等用户进一步指示。

---

## G. 元规则（行为约束）

### G1. 不要主动修复脚本/代码

用户明确表示不希望 AI 主动提出修复。遇到 validator/api_client 不一致等问题：**报告、不动手**，等用户提出。

### G2. 旧审批流程已废弃

旧版基于 PostgreSQL + `approval_log`（`approve_pending`/`reject_pending`）已废弃。新 API 写操作直接由后端处理，**用本文 [write-confirmation.md](write-confirmation.md) 的双层确认**。
