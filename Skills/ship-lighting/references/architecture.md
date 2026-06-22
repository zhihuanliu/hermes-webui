# 架构说明

## 调用链

```
用户自然语言
    │
    ▼
LLM（你）：
  ├── 意图识别  → 匹配工具
  ├── 参数提取  → 从自然语言抽取 deck_id、compartment_id…
  └── 调度执行  → 调用 tool_dispatcher.py
          │
          ▼
tool_dispatcher.py：
  ├── 自动注入 default record_id
  ├── param_validator 三层校验
  │     ├── 必填参数（缺则返回结构化错误 + 可用选项）
  │     ├── 枚举值（不合法返回允许值列表）
  │     └── 未知参数（提醒，不阻塞）
  └── api_client HTTP 调用
          │
          ▼
    ┌──────────────────────────────────────┐
    │       HTTP API (Flask)               │
    │  http://192.168.208.23:5000/api/v1   │
    └──────────────────────────────────────┘
```

## 参数校验三层

`param_validator.py` 在 API 调用前执行：

| 层 | 检查 | 失败返回 |
|----|------|----------|
| 1 | 必填参数 | `validation_error` + `missing` + 可用选项（如自动获取甲板列表） |
| 2 | 枚举值 | `invalid_enum` + 允许值列表 |
| 3 | 未知参数 | 警告（不阻塞调用） |

### 为什么已有必填位置参数还需要 param_validator？

`api_client` 函数签名缺参数时抛 Python `TypeError`（模糊的 `missing argument`），而 param_validator 返回结构化错误（`缺少 deck_id，可用甲板：DECK 4, DECK 5, DECK 6`），更适合 LLM 引导用户补全。

它也在调用 API 之前拦截非法枚举值，节省网络请求。

### 响应模板

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

---

## 数据隔离：record_id 与 profile

- 默认值：`210e9a838a5341d982c7f26d8036b11a`
- 不同 profile 通过 `.env` 中的 `SHIP_LIGHTING_RECORD_ID` 覆盖
- 例：`~/.hermes/profiles/user_zhang/.env` 写 `SHIP_LIGHTING_RECORD_ID=xxx`
- 效果：每个 profile 查自己的 record_id，互不可见

---

## 组合工具机制

`tool_dispatcher.py` 的 `COMPOSITE_MAP` 定义 pipeline，`run_composite()` 串联执行：

1. 遍历 pipeline 每一步
2. `_prepare_composite_params(step_name, context)` 只构造当前步需要的参数
3. 调用 `api_func(**step_params)`
4. 关键返回值注入 context 供下一步使用
5. 任一步出错则终止整个 pipeline

### 参数注入规则

上一步返回 dict 中以下 key 自动注入 context：

| 返回 key | 注入 context 的 key | 用途 |
|----------|---------------------|------|
| `count` | `_recommended_count` | 推荐灯数 → 验算 / 布局 |
| `lights_points` | `_lights_points` | 灯具坐标 |
| `cal_illuminance` | `_cal_illuminance` | 实际照度 |

### 当前组合工具

| 工具 | pipeline |
|------|----------|
| `full_illumination_design` | `recommend_light_count` → `verify_illuminance` → `layout_lights` |

### `full_illumination_design` 各步参数表

| 步骤 | 工具 | 传入参数 | 来源 |
|:----:|:-----|:---------|:-----|
| 1 | `recommend_light_count` | `record_id, compartment_id, light_type_id, illuminance, utilization, maintenance` | 用户参数 |
| 2 | `verify_illuminance` | `record_id, compartment_id, illuminance, utilization, maintenance, light_type_count` | 用户参数 + 上一步 count（转为 `light_type_count`） |
| 3 | `layout_lights` | `record_id, compartment_id, light_type_count, layout_type` | 用户参数 + 上一步 count + `layout_type` |

**关键约束：** `light_type_id` 只在 Step 1 传，不传给后两步；`layout_type` 只在 Step 3 传。否则 api_client 报 `unexpected keyword argument`。

### `_prepare_composite_params` 逻辑骨架

```python
def _prepare_composite_params(step_name, context):
    params = {"record_id": context.get("record_id")}

    if step_name == "recommend_light_count":
        for k in ["compartment_id", "light_type_id", "illuminance", "utilization", "maintenance"]:
            if k in context: params[k] = context[k]

    elif step_name == "verify_illuminance":
        for k in ["compartment_id", "illuminance", "utilization", "maintenance"]:
            if k in context: params[k] = context[k]
        if "_recommended_count" in context:
            params["light_type_count"] = [{"light_type_id": ..., "count": ...}]

    elif step_name == "layout_lights":
        params["compartment_id"] = context.get("compartment_id")
        if "_recommended_count" in context:
            params["light_type_count"] = [{"light_type_id": ..., "count": ...}]
        params["layout_type"] = context.get("layout_type", "uniform")

    return params
```

### 行为特点

- **任一步返回 error 则终止**——后续步骤不执行
- **Step 1 → 2 → 3 严格串联**——后两步必须等前一步返回 count
- **新建灯具的 supply 字段均为 null**——需额外通过 `bind_power` 绑定供电设备
- **直接写入后端**——无本地审批流程

### 灯数差异说明

v3 旧版 `calculate_lamp_count`（本地公式）和 `auto_layout`（几何排布）可能产生不一致的灯数。

v4 新版 `recommend_light_count` 和 `layout_lights` 共享同一 count，**不存在**这种差异。

如果用户对灯数不满意，可：
1. 手动指定 `light_type_count` 直接调 `layout_lights`
2. 换 `light_type_id`（更大流明值 → 更少灯数）
3. 调整 `illuminance` / `utilization` / `maintenance` 重新推荐

### 扩展新 pipeline

在 `COMPOSITE_MAP` 添加定义 + `_prepare_composite_params` 加 `elif` 分支即可。

> 旧 v3 工具名 `calculate_lamp_count`, `check_illuminance`, `auto_layout` 已废弃，新代码不应再使用。映射见 [legacy-tool-mapping.md](legacy-tool-mapping.md)。

---

## Skill vs Plugin：为什么选 Skill

| 维度 | Skill | Plugin | 选 Skill 的理由 |
|:----|:------|:-------|:----------------|
| 交互 | LLM 引导文档 + terminal | 工具注册 + 钩子 + slash 命令 | 所有操作走 terminal → dispatcher，不需注册工具 |
| 加载 | `skill_view()` 按需 | 自动发现 + config.yaml 启用 | 按需加载更适合低频使用，不增加 session 启动开销 |
| 生命周期 | LLM 决定 | 全程活跃（hooks） | 不需要 `on_session_start` 等钩子 |
| 脚本调用 | `python3 scripts/tool_xxx.py` | 注册为工具自动发现 | terminal 调用模式成熟稳定 |

**结论：** 所有交互通过 terminal → dispatcher，不涉及 Hermes 工具注册、生命周期钩子或 slash 命令。Skill 直接提供 LLM 文档 + CLI 脚本，结构更简洁。将来如需 hooks 或工具注册，迁移成本很低（已有实操经验）。
