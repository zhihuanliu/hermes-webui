# 批量查询模式

## 适用范围

批量查询仅适用于 **API 已实现的端点**：

| 查询工具 | 可批量 | 说明 |
|----------|:------:|------|
| `query_current_system_status` | ✅ | 单次调用即返回所有数据 |
| `query_import_info` | ✅ | 单次调用即返回所有记录 |
| `query_compartment_info` | ✅ | 不传参数列出全部舱室，传参数查单个 |
| 其他查询工具 | ⏳ | API 嵌套数据待上线 |

## 批量查询模式（API 可用时使用）

### 方案 A：工具级组合查询（推荐）

对于已实现组合查询工具的场景（目前仅 `get_loads_with_detail`），直接调用工具即可，无需循环：

```bash
# 查整个甲板全部负载的列表+详情
python3 scripts/tool_dispatcher.py --tool get_loads_with_detail --params '{"deck_id":"DECK 4"}'

# 限定舱室
python3 scripts/tool_dispatcher.py --tool get_loads_with_detail --params '{"deck_id":"DECK 4","compartment_id":"PIPES..."}'
```

内部自动执行：GET /decks/loads → 逐条 GET /decks/loads/detail，返回 `{total, loads: [...]}`。
如需为其他实体（灯具、配电板等）添加同类组合查询，需三处修改：
1. `api_client.py` — 加 `get_XXXs_with_detail()` 函数
2. `param_validator.py` — 加校验规则
3. `tool_dispatcher.py` — 加映射条目

### 方案 B：execute_code 循环调用（通用后备）

```python
from hermes_tools import terminal
import json

# 循环从 API 查询甲板详情
result = terminal(
    'python3 scripts/tool_dispatcher.py --tool query_current_system_status --params \'{}\'',
    workdir="/home/lxhu/.hermes/skills/ship-lighting",
    timeout=10
)
data = json.loads(result["output"])
print(json.dumps(data, ensure_ascii=False, indent=2))
```

## 参数中的键名要转义

Python f-string 中 JSON 的花括号需要双写：
- 正确：`--params '{{"compartment_name":"{name}"}}'`
- 错误：`--params '{"compartment_name":"{name}"}'`

## 注意事项

- 退出码全部为 0 才表示成功
- 每个调用设 timeout=10，避免单个卡住
- 工具返回 `api_not_implemented` 时说明 API 端点尚未实现
