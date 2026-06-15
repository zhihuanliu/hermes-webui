# Full Illumination Design — Real-World Example

> 2026-06-04: CHAIN LOCKER_DECK 4_FR253+725_P6622, type_02 (泛光灯B), 107 盏, uniform 布局

## 输入参数

| 参数 | 值 |
|:----|:----|
| 甲板 | DECK 4 |
| 舱室 | CHAIN LOCKER_DECK 4_FR253+725_P6622 |
| 灯具类型 | type_02（泛光灯B, 1200lm, 20W） |
| 目标照度 | 200 lx |
| 照明率 (utilization) | 0.8 |
| 保持率 (maintenance) | 1.0 |
| 布局方式 | uniform（均匀布局） |

## 命令

```bash
cd /home/lxhu/.hermes/skills/ship-lighting
python3 scripts/tool_dispatcher.py --tool full_illumination_design --params '{
  "compartment_id":"CHAIN LOCKER_DECK 4_FR253+725_P6622",
  "light_type_id":"type_02",
  "illuminance":200,
  "utilization":0.8,
  "maintenance":1.0,
  "layout_type":"uniform"
}'
```

## 流水线结果

### Step 1: recommend_light_count
```
推荐灯数：107 盏
灯具类型：type_02
```

### Step 2: verify_illuminance
```
计算照度：201.16 lx
要求照度：200.0 lx
结果：✅ 验算通过
```

### Step 3: layout_lights
```
灯数：107 盏（作为 light_type_count 传入）
布局：uniform
```

## 布局结构

| Y 行 | Y 坐标 | 列数 | 灯编号范围 |
|:----:|:------:|:----:|:----------:|
| 第1行 | 421.0 | 14 | 泛光灯B-1 ~ B-14 |
| 第2行 | 542.0 | 14 | 泛光灯B-15 ~ B-28 |
| 第3行 | 662.0 | 14 | 泛光灯B-29 ~ B-42 |
| 第4行 | 783.0 | 14 | 泛光灯B-43 ~ B-56 |
| 第5行 | 904.0 | 14 | 泛光灯B-57 ~ B-70 |
| 第6行 | 1025.0 | 14 | 泛光灯B-71 ~ B-84 |
| 第7行 | 1145.0 | 14 | 泛光灯B-85 ~ B-98 |
| 第8行 | 1266.0 | 9 | 泛光灯B-99 ~ B-107 |

- X 范围：6896.0 ~ 8415.0（列间距 ≈117）
- Y 范围：421.0 ~ 1266.0（行间距 ≈121）
- 总布局：7 × 14 + 9 = 107 盏（第8行9盏）

## 新建灯具观察

所有 107 盏灯在 `get_lights` 查询中显示：
- ✅ 正确分配到 compartment_id
- ✅ 正确标记 light_type_id = type_02
- ✅ 灯具命名：泛光灯B-1 ~ 泛光灯B-107（自动编号）
- ⚠️ `supply: null` — 新建灯具未绑定供电设备，需额外处理

## 经验

1. **107 盏灯的 get_lights 输出约 40KB**，未触发 terminal 50KB 截断。约 120+ 盏灯时须考虑文件重定向方案。
2. 新建灯具的 `supply` 字段均为 `null`，供电绑定是独立于照明设计之外的步骤。
3. 泛光灯B(type_02, 1200lm) 在 CHAIN LOCKER 舱室中，200 lx 目标用 107 盏灯达到 201.16 lx，误差 ~0.58%。
