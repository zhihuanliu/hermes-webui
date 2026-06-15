# 复合 Pipeline 行为说明

## full_illumination_design（v4 API 版）

组合工具流程（当前活跃 API）：
```
recommend_light_count → verify_illuminance → layout_lights
```

### 当前行为（HTTP API 模式，v4.1+）

| 步骤 | 工具 | 说明 |
|:----:|:-----|:-----|
| Step 1 | `recommend_light_count` | 服务器端推荐灯数，返回 count |
| Step 2 | `verify_illuminance` | 用上一步 count 作为 light_type_count 验算照度 |
| Step 3 | `layout_lights` | 用上一步 count 作为 light_type_count 生成灯具位置 |

**参数传递规则：**
- Step 1 使用：`compartment_id, light_type_id, illuminance, utilization, maintenance`
- Step 2 使用：`compartment_id, illuminance, utilization, maintenance` + 上一步 count（转为 `light_type_count`）
- Step 3 使用：`compartment_id` + 上一步 count（转为 `light_type_count`）+ `layout_type`

> 注意：`light_type_id` 只在 Step 1 传递，不传给后两步（避免 `unexpected keyword argument`）。

### 行为特点

- 任一步返回 error 则终止 pipeline
- Step 1 → Step 2 → Step 3 严格串联
- 新建灯具的 supply 字段均为 null（需额外绑定供电设备）
- 所有操作直接写入后端，无本地审批流程

### 灯数差异

`recommend_light_count` 按照度公式计算灯数（返回整数 count），`layout_lights` 按该 count 在舱室几何空间中均匀排布。二者使用同一个 count 值，不存在旧版中的「本地计算 vs 几何排布」差异。如果用户对灯数不满意，可：
1. 手动指定 `light_type_count` 直接用 `layout_lights`
2. 用不同的 `light_type_id`（更大流明值可减少灯数）
3. 调整 `illuminance`/`utilization`/`maintenance` 重新推荐

> ⚠️ 旧版 (v3) 工具名 `calculate_lamp_count`, `check_illuminance`, `auto_layout` 已废弃，新代码不应再使用。
