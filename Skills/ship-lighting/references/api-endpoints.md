# HTTP API 接口文档

## 基础信息

- **Base URL**: `http://192.168.208.23:5000/api/v1/`
- **record_id**: 由 Hermes 服务端绑定的当前已授权记录注入，无固定默认值
- **认证**: 每次请求携带 Hermes 注入的 EID 身份头；生产调用必须携带短期委托令牌
- **响应格式**: `{"code": 0, "message": "success", "data": {...}}`

## 可用端点

### GET /api/v1/decks

获取甲板列表（当前仅返回基本信息，嵌套 compartments 待上线）。

**参数**:
| 参数 | 类型 | 必填 | 说明 |
|------|------|:----:|------|
| record_id | string | ✅ | 导入记录 ID |

**返回** (当前):
```json
{
  "code": 0,
  "data": {
    "record_id": "<authorized-record-id>",
    "decks": [
      {
        "deck_id": "DECK 4",
        "deck_name": "DECK 4",
        "deck_height": 13.2,
        "deck_url": "http://.../deck_png/DECK 4.png"
      }
    ]
  }
}
```

### GET /api/v1/records

获取导入记录列表。

**参数**:
| 参数 | 类型 | 必填 | 说明 |
|------|------|:----:|------|
| record_id | string | ✅ | 导入记录 ID |

**返回**:
```json
{
  "code": 0,
  "data": {
    "records": [
      {
        "record_id": "71de81840aa14e0990c5d6abe1338ceb",
        "file_name": "ACAD-4738.100.102I4 General Arrangement.dxf",
        "import_mode": "cover",
        "stage": "primary_completed",
        "createdAt": "2026-06-03T08:40:23.619298+00:00",
        "updatedAt": "2026-06-03T08:40:23.653219+00:00"
      }
    ]
  }
}
```

stage 取值: `recognition_completed` / `primary_completed` / `secondary_completed`

### GET /api/v1/files/{record_id}/deck_png/{deck_name}.png

获取甲板底图 PNG。

---

## 完整 API Schema（目标结构）

以下 JSON 定义了 **所有子功能的接口规范**，当前 `/api/v1/decks` 仅返回甲板基本信息（无嵌套 compartments）。此 Schema 是最终目标——一个 `GET /decks` 返回完整的甲板→舱室→设备嵌套数据。

**record_id 来源**: Hermes 服务端可信 EID 会话上下文。

```json
{
  "code": 0,
  "message": "success",
  "data": {
    "record_id": "xxx",
    "decks": [
      {
        "deck_id": "123",
        "deck_name": "deck1",
        "deck_height": 100,
        "deck_url": "http://xxxxxx/deck.png",
        "compartments": [
          {
            "compartment_id": 1,
            "compartment_name": "compartment1",
            "center_point": [12, 34],
            "points": [[10,20], [30,20], [1,2], [3,4]],
            "primary": {
              "main_switchboards": [
                {"msb_id": "msb_001", "msb_name": "主电板1", "icon_url": "1.svg"}
              ],
              "distribution_boards": [
                {"db_id": "db_001", "db_name": "分配电箱1", "icon_url": "1.svg"}
              ],
              "loads": [
                {"load_id": "L001", "load_name": "负载1", "type": "PC", "icon_url": "1.svg"}
              ]
            },
            "secondary": {
              "distribution_boards": [
                {"db_id": "db_002", "db_name": "分配电箱2", "icon_url": "1.svg"}
              ],
              "loads": [
                {"load_id": "L002", "load_name": "负载2", "type": "PC", "icon_url": "1.svg"}
              ]
            },
            "lighting": {
              "lights": [
                {"light_id": "light_001", "light_name": "灯具1", "icon_url": "1.svg", "type": "筒灯", "points": [3, 4]}
              ],
              "beam_lines": [
                {"beam_line_id": "001", "beam_line_name": "梁线1", "points": [[10,20], [30,20]]}
              ],
              "lane_lines": [
                {"lane_line_id": "001", "lane_line_name": "车道线1", "points": [[10,20], [30,20]]}
              ]
            }
          }
        ]
      }
    ]
  }
}
```

### 数据模型说明

| 层级 | 描述 | 字段 |
|------|------|------|
| deck | 甲板 | deck_id, deck_name, deck_height, deck_url |
| compartment | 舱室 | compartment_id, compartment_name, center_point, points |
| primary | 一次侧设备 | main_switchboards[], distribution_boards[], loads[] |
| secondary | 二次侧设备 | distribution_boards[], loads[] |
| lighting | 照明 | lights[], beam_lines[], lane_lines[] |

### 当前 API 实现状态

| 端点 | 返回内容 | 状态 |
|------|----------|:----:|
| `GET /api/v1/decks?record_id=xxx` | 仅 deck_id/deck_name/deck_height/deck_url | ✅ 可用（无嵌套） |
| 嵌套 compartments 数据 | 完整舱室→设备数据 | ⏳ 待服务端实现 |

当嵌套 Schema 在 API 中可用时，只需在 `api_client.py` 中将对应 `get_*()` 函数改为直接解析 `data.decks[].compartments[]` 即可。

---

## 2026-06-03 端点探测记录

以下路径在历史开发会话中探测过。它们仅作为路径兼容性记录，不是可执行命令；
Skill 运行时必须通过 `tool_dispatcher.py` 访问。

### 已验证可用 ✅

- `GET /api/v1/decks`：返回甲板基本信息。
- `GET /api/v1/records`：返回当前授权 record 范围内的导入记录。

### 已验证 404 ❌

历史上返回资源不存在的扁平路径包括 `/compartments`、`/compartment`、`/deck`
和 `/record/{id}`。使用本文档前面的嵌套资源路径。
