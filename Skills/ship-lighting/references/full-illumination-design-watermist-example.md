# 完整照明设计实测 — WATERMIST VALVE CENTER MACHINERY（399盏泛光灯B）

## 基本信息

| 项目 | 值 |
|:----|:---|
| **舱室** | WATERMIST VALVE CENTER MACHINERY_hermes |
| **舱室ID** | `WATERMIST VALVE CENTER MACHINERY_DECK 4_FR40+1_P1790` |
| **甲板** | DECK 4 |
| **面积** | 239.04 m² |
| **灯具类型** | 泛光灯B (type_02) |
| **布局类型** | `uniform`（均匀布局） |

## 调用命令

```bash
python3 scripts/tool_dispatcher.py --tool full_illumination_design --params '{
  "compartment_id":"WATERMIST VALVE CENTER MACHINERY_DECK 4_FR40+1_P1790",
  "light_type_id":"type_02",
  "illuminance":200,
  "utilization":0.1,
  "maintenance":1,
  "layout_type":"uniform"
}'
```

## 三步流程结果

### Step 1: recommend_light_count

| 输入参数 | 值 |
|:---------|:---|
| 目标照度 | 200 lx |
| 照明率 | 0.1 |
| 保持率 | 1.0 |
| **推荐灯数** | **399 盏** |

### Step 2: verify_illuminance

| 项目 | 值 | 判定 |
|:----|:---|:----:|
| 要求照度 | 200.0 lx | — |
| 计算照度 | 200.3 lx | **✅ 达标**（+0.3 lx） |

### Step 3: layout_lights

| 项目 | 值 |
|:----|:---|
| 布局模式 | uniform |
| 布灯数 | 399 盏 |
| 坐标范围 | X: 2101–4232, Y: 748–827 （密集均匀网格） |

## 落库验证

查询舱室详情确认数据已写入：

```json
{
  "light_count": 399,
  "light_total_power": 7980.0,
  "total_luminous_flux": 478800
}
```

## 与 CHAIN LOCKER 示例对比

| 对比项 | CHAIN LOCKER (107盏) | WATERMIST (399盏) |
|:-------|:-------------------:|:-----------------:|
| 舱室面积 | 较小 | 239.04 m² |
| 推荐灯数 | 107 | 399 |
| 验算照度 | 201.16 lx | 200.3 lx |
| 布局类型 | uniform | uniform |
| 目标照度 | 200 lx | 200 lx |
