# 写操作双层确认流程

所有涉及数据库修改的操作（POST/PUT/DELETE）必须经过双层确认。这是用户的硬性安全要求。

## 涉及工具

| 类别 | 工具 |
|------|------|
| 甲板 | `update_deck` |
| 舱室 | `create_compartment`, `update_compartment`, `delete_compartment` |
| 负载 | `update_load` |
| 灯具 | `update_light`, `delete_lights`, `layout_lights`, `update_lights_layout` |
| 绑定 | `bind_compartment`, `unbind_compartment`, `bind_power`, `unbind_power` |
| 梁线 | `create_beam_line`, `update_beam_line`, `delete_beam_line` |
| 车道线 | `create_lane_line`, `update_lane_line`, `delete_lane_line` |
| 接线盒 | `create_junction_box` |
| 编辑模式 | `edit_mode_start`, `edit_mode_exit` |
| 图纸解析 | `primary_parse`, `submit_preview`, `secondary_parse`, `recognition` |
| 组合 | `full_illumination_design`（内含 `layout_lights`） |

**例外（只读、不需确认）：** `get_*`、`search_*`、`recommend_light_count`、`verify_illuminance`、`measure_*`。即使传了 `--confirm` 也会自动跳过。

---

## 第 1 层：LLM 通过 `clarify` 工具确认

调用工具前先向用户展示操作摘要表格：

```markdown
🖊 即将执行写入操作 — 请确认

| 项目 | 内容 |
|:----|:------|
| 操作 | update_deck — 编辑甲板信息 |
| 目标 | DECK 5 |
| 变更 | deck_name: DECK 5 → 新名称 |
```

然后调用：
```
clarify(choices=["✅ Allow (确认执行)", "❌ Reject (取消操作)"])
```

- **Allow** → 进入第 2 层
- **Reject** → 告知用户操作已取消，不调用 dispatcher

---

## 第 2 层：dispatcher 终端确认（管道传 y）

```bash
echo "y" | python3 scripts/tool_dispatcher.py --tool update_deck \
  --params '{"deck_id":"DECK 5","deck_name":"新名称"}' --confirm
```

### 为什么是 `echo "y" |` 管道

`tool_dispatcher.py` 的 `--confirm` 内部调用 `input()` 等待 stdin。

- ✅ `echo "y" |` 管道：字符 `y` + 换行通过 stdin 进入 `input()`，确认通过
- ❌ `terminal(background=true)` + `process(action='submit', data='y')`：dispatcher 打印提示后立即等待，但 background 模式的 process.submit 来不及把 y 写进 stdin，dispatcher 阻塞或超时

**管道写法是唯一标准方式。**

---

## 完整示例

```
用户：删除 WATERMIST VALVE CENTER MACHINERY_hermes 这个舱室

助手：
  🖊 即将执行写入操作 — 请确认
  | 项目 | 内容 |
  | 操作 | delete_compartment — 删除舱室 |
  | 甲板 | DECK 4 |
  | 目标 | WATERMIST VALVE CENTER MACHINERY_hermes |

  [调用 clarify(choices=["✅ Allow","❌ Reject"])]

用户：✅ Allow

助手：
  [执行]
  echo "y" | python3 scripts/tool_dispatcher.py --tool delete_compartment \
    --params '{"deck_id":"DECK 4","compartment_id":"WATERMIST VALVE CENTER MACHINERY_hermes"}' \
    --confirm

  ✅ 删除成功！
```

---
