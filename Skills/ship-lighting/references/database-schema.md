# 数据源说明 — 纯 HTTP API 架构

## 当前状态

本 skill **不使用 PostgreSQL**。所有数据通过 HTTP API 获取。

| 数据 | 来源 | 状态 |
|------|------|:----:|
| 甲板列表 | `GET /api/v1/decks` | ✅ 可用 |
| 导入记录 | `GET /api/v1/records` | ✅ 可用 |
| 舱室/负载/灯具 | `GET /api/v1/decks`（嵌套 compartments） | ⏳ 待上线 |
| 写操作 | API 写端点 | ⏳ 待上线 |
| 审批存储 | `approval_store.json`（本地文件） | ✅ 替代方案 |

## API 响应格式

```json
{
  "code": 0,
  "message": "success",
  "data": { ... }
}
```

完整 Schema 见 `references/api-endpoints.md`。

## API 端点一览

| 端点 | 方法 | 参数 | 返回 |
|------|:----:|------|------|
| `/api/v1/decks` | GET | record_id | 甲板列表（deck_id, name, height, url） |
| `/api/v1/records` | GET | record_id | 导入记录列表 |

### 默认 record_id

`ed18461b23884c569e2366c228378825`

## 审批存储（本地 JSON）

审批记录存储在 skill 目录下的 `approval_store.json`，格式：

```json
[
  {
    "id": 1,
    "operation": "UPDATE",
    "table_name": "compartments",
    "record_id": "机舱",
    "old_data": {},
    "new_data": {"layout": "centered_grid", "lamp_count": 12},
    "status": "pending",
    "requested_at": "2026-06-03 17:30:00",
    "reviewed_by": null,
    "reviewed_at": null,
    "note": null
  }
]
```
