# 船舶照明 API 完整 Schema 定义

来源: 用户 2026-06-04 提供（接口设计文档.docx）
基础 URL: `http://192.168.208.23:5000/api/v1/`
`record_id` 由 Hermes 服务端的可信 EID 会话上下文注入；模型和浏览器不得提供或覆盖。

> 所有端点在 api_client.py 中已封装。查询通过 `GET /canvas/all` 获取完整嵌套数据，写操作通过 POST/PUT/DELETE 端点直接执行。
>
> ⚠️ 部分端点标注"未完成"（梁线/车道线增删改、接线盒等），api_client 已封装函数但后端可能未实现，调用可能返回 4002。

## 核心端点速查

| 类型 | 方法 | 路径 | 必填参数 |
|------|------|------|----------|
| 完整嵌套数据 | GET | `/canvas/all` | record_id, system_type |
| 甲板列表 | GET | `/decks` | record_id |
| 甲板搜索 | GET | `/decks/search` | record_id, system_type, keyword, deck_id |
| 编辑甲板 | PUT | `/decks` | record_id, deck_id, deck_height, deck_name |
| 舱室列表 | GET | `/decks/compartments` | record_id, deck_id |
| 舱室详情 | GET | `/decks/compartments/detail` | record_id, deck_id, compartment_id |
| 新增舱室 | POST | `/decks/compartments` | record_id, deck_id, points |
| 编辑舱室 | PUT | `/decks/compartments` | record_id, deck_id, compartment_id, compartment_name, compartment_function, points |
| 删除舱室 | DELETE | `/decks/compartments` | record_id, deck_id, compartment_id |
| 主配电板列表 | GET | `/decks/main-switchboards` | record_id, deck_id, compartment_id |
| 分配电箱列表 | GET | `/decks/distribution-boards` | record_id, deck_id, compartment_id |
| 负载列表 | GET | `/decks/loads` | record_id, deck_id, compartment_id |
| 负载详情 | GET | `/decks/loads/detail` | record_id, load_id |
| 编辑负载 | PUT | `/decks/loads` | record_id, load_id, load_name, type, compartment_id, supply_equipment_id |
| 灯具类型库 | GET | `/decks/light-types` | record_id |
| 灯具列表 | GET | `/decks/lights` | record_id, deck_id, compartment_id |
| 灯具详情 | GET | `/decks/lights/detail` | record_id, light_id |
| 编辑灯具 | PUT | `/decks/lights` | record_id, light_id, light_name, compartment_id, light_type_id, points |
| 批量删除灯具 | DELETE | `/decks/lights` | record_id, light_ids |
| 灯数推荐 | POST | `/decks/lights/count-recommendation` | record_id, compartment_id, light_type_id, illuminance, utilization, maintenance |
| 灯具布局 | POST | `/decks/lights/lights-layout` | record_id, compartment_id, light_type_count, layout_type |
| 照度验算 | POST | `/decks/lights/verify-illuminance` | record_id, compartment_id, light_type_count, illuminance, utilization, maintenance |
| 梁线列表 | GET | `/decks/beam-lines` | record_id, deck_id |
| 车道线列表 | GET | `/decks/lane-lines` | record_id, deck_id |
| 未绑定舱室负载 | GET | `/allocation/unbound-compartment` | record_id, system_type |
| 未绑定配电负载 | GET | `/allocation/unbound-power` | record_id, deck_id, system_type, compartment_id |
| 绑定负载到舱室 | POST | `/allocation/bind-compartment` | record_id, deck_id, compartment_id, unbound_loads |
| 绑定负载到供电 | POST | `/allocation/bind-power` | record_id, supply_equipment_id, unbound_loads |
| 导入记录 | GET | `/records` | 无 |
| 点距测量 | POST | `/tools/measure-point` | record_id, deck_id, start_point, end_point |

## 完整嵌套数据响应结构

`GET /canvas/all?record_id=xxx[&system_type=primary/secondary/lighting]`

system_type 过滤:
- `primary` — 一次系统（主配电板、分配电箱、大功率负载）
- `secondary` — 二次系统（分配电箱、小功率负载）
- `lighting` — 照明系统（灯具、车道线、梁线）
- 不传 — 三个系统合并返回

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
        "deck_url": "http:xxxxxx/deck.png",
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
              "distribution_boards": [...],
              "loads": [...]
            },
            "lighting": {
              "lights": [
                {"light_id": "light_001", "light_name": "灯具1", "type": "筒灯", "points": [3,4]}
              ],
              "beam_lines": [
                {"beam_line_id": "001", "beam_line_name": "梁线1", "points": [[10,20],[30,20]]}
              ],
              "lane_lines": [
                {"lane_line_id": "001", "lane_line_name": "车道线1", "points": [[10,20],[30,20]]}
              ]
            }
          }
        ]
      }
    ]
  }
}
```

## 数据字段说明

### Deck（甲板）
| 字段 | 类型 | 说明 |
|------|------|------|
| deck_id | string | 甲板 ID (如 "DECK 4") |
| deck_name | string | 甲板名称 |
| deck_height | number | 层高 (m) |
| deck_url | string | 底图 PNG URL |
| compartments | array | 舱室数组 |

### Compartment（舱室）
| 字段 | 类型 | 说明 |
|------|------|------|
| compartment_id | string | 舱室唯一 ID |
| compartment_name | string | 舱室名称 |
| center_point | [number, number] | PNG 坐标上的中心点 |
| points | [[number,number],...] | 轮廓点坐标列表 |
| primary | object | 一次侧设备 |
| secondary | object | 二次侧设备 |
| lighting | object | 照明数据 |

## 已知陷阱

1. **嵌套路径规则**: 资源都在 `/decks/` 下，不是扁平。`/compartments` → 404, `/decks/compartments` → 200
2. **全参必填**: api_client 所有业务函数参数均为必填位置参数，无 `= None` 或 `**kwargs`
3. **空字符串过滤**: 查询全部负载/灯具时传空字符串作为 compartment_id
4. **DELETE 带 body**: `DELETE /decks/lights` 支持 JSON body
5. **terminal 截断**: 大数据量输出有 ~50KB 上限，用文件中转
