# Composite Pipeline 参数传递规则

## 原理

`tool_dispatcher.py` 的 `COMPOSITE_MAP` 定义串联 pipeline，`run_composite()` 执行：
1. 遍历 pipeline 中的每一步
2. `_prepare_composite_params(step_name, context)` 只构造当前步需要的参数
3. 调用 api_func(**step_params)
4. 将返回的关键值注入 context
5. 任一步出错则终止

## _prepare_composite_params 逻辑

```python
def _prepare_composite_params(step_name, context):
    params = {"record_id": context.get("record_id")}

    if step_name == "recommend_light_count":
        # 只传灯具推荐需要的字段
        for k in ["compartment_id", "light_type_id", "illuminance", "utilization", "maintenance"]:
            if k in context: params[k] = context[k]

    elif step_name == "verify_illuminance":
        # 用上一步count构建light_type_count
        for k in ["compartment_id", "illuminance", "utilization", "maintenance"]:
            if k in context: params[k] = context[k]
        if "_recommended_count" in context:
            params["light_type_count"] = [{"light_type_id": ..., "count": ...}]

    elif step_name == "layout_lights":
        params["compartment_id"] = context.get("compartment_id")
        if "_recommended_count" in context:
            params["light_type_count"] = ...
        params["layout_type"] = context.get("layout_type", "uniform")
```

## 扩展新 pipeline

在 `COMPOSITE_MAP` 中添加新定义 + `_prepare_composite_params` 中加对应的 `elif` 分支即可。

## key 注入规则

上一步返回的 dict 中，以下 key 会自动注入 context：

| 返回 key | context key | 用途 |
|----------|-------------|------|
| `count` | `_recommended_count` | 推荐灯数，传给照度验算和布局 |
| `lights_points` | `_lights_points` | 灯具坐标，后续可用 |
| `cal_illuminance` | `_cal_illuminance` | 计算照度，后续可用 |
