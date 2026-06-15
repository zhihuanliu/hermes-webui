# API 端点发现方法

## 问题背景

初次探测一个 Flask REST API 时，如果只尝试扁平路径（如 `/compartments`、`/loads`），会得到 404。
实际端点可能位于嵌套路径下（如 `/decks/compartments`、`/decks/loads`）。

**本次教训：** 花了多次往返才发现 `/api/v1/decks/compartments` 而不是 `/api/v1/compartments`。

## 通用模式

```
/{领域}/{资源}                     → 如 /decks, /records
/{领域}/{资源}/{子资源}            → 如 /decks/compartments, /decks/lights
/{领域}/{资源}/{子资源}/{动作}     → 如 /decks/compartments/detail, /decks/lights/verify-illuminance
/{领域}/{资源}/{子资源}/{子操作}   → 如 /decks/lights/count-recommendation
```

## 探测步骤

```bash
# 1. 先试顶层领域
curl host/api/v1/decks
curl host/api/v1/records
curl host/api/v1/canvas

# 2. 再试领域下的资源嵌套
curl host/api/v1/decks/compartments
curl host/api/v1/decks/loads
curl host/api/v1/decks/lights
curl host/api/v1/decks/main-switchboards
curl host/api/v1/decks/distribution-boards
curl host/api/v1/decks/beam-lines
curl host/api/v1/decks/lane-lines

# 3. 再试子资源下的详情/动作
curl host/api/v1/decks/compartments/detail
curl host/api/v1/decks/loads/detail
curl host/api/v1/decks/lights/detail
curl host/api/v1/decks/lights/verify-illuminance
curl host/api/v1/decks/lights/count-recommendation
curl host/api/v1/decks/lights/lights-layout

# 4. 跨领域的操作
curl host/api/v1/allocation/bind-compartment
curl host/api/v1/tools/measure-point
curl host/api/v1/drawings/primary-parse
```

## 对应关系

| 扁平路径（❌ 404） | 嵌套路径（✅ 成功） |
|--------------------|-------------------|
| `/compartments` | `/decks/compartments` |
| `/loads` | `/decks/loads` |
| `/lights` | `/decks/lights` |
| `/main-switchboards` | `/decks/main-switchboards` |
| `/distribution-boards` | `/decks/distribution-boards` |
| `/beam-lines` | `/decks/beam-lines` |
| `/lane-lines` | `/decks/lane-lines` |

## 根本原则

REST API 的资源路径反映**资源归属关系**：

```
decks (甲板) ──┬── compartments (舱室) ──┬── detail (详情)
               │                          ├── main-switchboards (主配电板)
               │                          ├── distribution-boards (分配电箱)
               │                          ├── loads (负载)
               │                          ├── lights (灯具)
               │                          ├── beam-lines (梁线)
               │                          └── lane-lines (车道线)
               │
               └── search (搜索)
```

所有业务资源都在 `/decks/` 下，不是平铺的。
