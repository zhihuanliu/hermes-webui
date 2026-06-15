---
name: test-reporting
description: "全量工具测试报告生成指南 — 自然语言交互格式"
---

# 全量工具测试报告生成指南

当用户要求生成测试报告时，按此流程操作。

## 用户对测试报告的硬性要求

1. **格式：** Markdown（.md），不是 DOCX 或 PDF
2. **交互格式：** 用 **自然语言交互** 形式展示，不是 API 参数 + JSON 返回
   - **用户输入：** 用户说了什么（如"查下 DECK 4 的灯具"）
   - **Hermes 响应：** 智能体的格式化回复（表格、结构化文本）
   - ❌ 不要展示 raw JSON 或 tool_dispatcher 命令行
3. **全量覆盖：** 所有 61 个工具都必须测，一个不落
4. **无截断：** 每个测试的 Hermes 响应必须完整展示，不得截断
   - 大输出（>50KB）：独立保存到 `/tmp/`，报告中引用路径
5. **真实结果：** 必须通过真实 API 调用获取数据，不能模拟或伪造
6. **通过率：** 最终报告需要包含通过率数据

## 报告结构

```
1. 用户核心需求与应对方案
   - 上下文能力、功能清单覆盖、灵活交互、口语化识别
2. Hermes + SKILL 架构
   - 架构原理图解 vs LangGraph 对比
3. 测试用例（自然语言交互）
   - TC-01 ~ TC-N：每个用例展示「用户输入 → Hermes响应」
4. 测试总结
   - 统计结果、关键验证路线、已知问题
```

## 测试用例格式模板

每个 TC 使用如下三段式结构：

```markdown
## TC-01：查询甲板列表

**工具：** `get_decks`

**用户输入：**
> 查询甲板列表

**Hermes 响应：**

当前设计共有 **3 个甲板**：

| 甲板ID | 层高 |
|:------:|:----:|
| DECK 4 | 13.2m |
| DECK 5 | 15.0m |
| DECK 6 | 18.0m |
```

## 全量测试执行

### 方案：批量脚本 + 逐步运行

1. 写一个 Python 脚本，用 `subprocess` 遍历所有工具
2. 对每个工具：
   - 构造带 `&` 容错的 JSON 参数
   - 调用 `tool_dispatcher.py` 获取结果
   - 将结果格式化为 Hermes 风格的表格/结构化文本
   - 保存到 `/tmp/hermes_test_data.json`（JSON 数组）
3. 从 JSON 数据文件生成最终 MD 报告

### 关键实现技巧

**`&` 符号容错：** 舱室 ID 如 `CHAIN LOCKER & MUD BOX ACCESS_...` 含 `&`，直接传 `--params` 会被 bash 解释为后台任务。

```python
# ✅ 正确：写文件再读取
with open('/tmp/_tdp.json', 'w') as f:
    json.dump(params, f)
cmd = f'cd {SCRIPTS} && python3 scripts/tool_dispatcher.py --tool {tool} --params "$(cat /tmp/_tdp.json)"'
r = subprocess.run(cmd, capture_output=True, text=True, timeout=30, shell=True)
```

**Hermes 响应格式化：** 从 JSON 结果提取字段，构建 Markdown 表格。

```python
def fmt_table(headers, rows):
    h = '| ' + ' | '.join(headers) + ' |'
    sep = '|' + '|'.join(':' + '-'*max(len(hh),3) + ':' for hh in headers) + '|'
    body = ['| ' + ' | '.join(str(c) for c in row) + ' |' for row in rows]
    return '\n'.join([h, sep] + body)
```

### 大输出文件独立保存

| 工具 | 典型大小 | 原因 |
|:-----|:--------:|:-----|
| get_canvas_all | ~4.3 MB | 所有甲板的舱室坐标点 |
| get_lights(DECK4) | ~178 KB | 220 盏灯具数据 |
| get_lights(DECK6) | ~83 KB | 多个舱室数据 |
| search_deck | ~139 KB | 照明系统搜索 |

保存路径：`/tmp/test_result_{label}.json`

## 已知陷阱

### 1. execute_code 环境隔离

在每个 `execute_code` 调用中，`/tmp/` 是独立的沙箱文件系统。一个 `execute_code` 中写入的文件不能在下一个 `execute_code` 中读取。**必须使用 `terminal()` 工具写入文件才能在后续 persist。** 但 terminal 的 `/tmp/` 是宿主机的，execute_code 是隔离沙箱。

### 2. `terminal` 输出截断（~50KB）

`terminal` 工具的 stdout 有约 50KB 上限。大 JSON 输出会被截断导致 `JSONDecodeError`。

**解决：** 用 `> /tmp/output.json` 重定向到文件写入完整数据，再从文件读取。

### 3. compartment_id 需要传空字符串

`get_lights`、`get_loads`、`get_beam_lines`、`get_lane_lines` 在 `api_client` 中 `compartment_id` 是必填参数。查询全甲板时要传 `""`。

### 4. 部分工具返回数据格式不一致

`get_compartment_info`、`get_unbound_compartment`、`get_loads_with_detail` 等工具返回的数据可能是 dict 或 list 或 nested dict。代码中需用 `isinstance()` 判断格式，不能假设固定结构。

### 5. 测试脚本需要经常修正

每次生成测试报告时，需要根据 API 实际返回的数据结构调整脚本（字段名、嵌套层次、None 值处理）。**不要期待一次写完就能跑通全部 61 个工具。**

## 报告生成脚本

|| 脚本 | 功能 |
||:-----|:-----|
|| `scripts/run_nl_tests.py` | ~~已删除~~ |
|| `scripts/gen_final_report.py` | ~~已删除~~ |
|| `scripts/run_all_tests.py` | ~~已删除~~ |
|| `scripts/gen_md_report.py` | ~~已删除~~ |

> 测试脚本已全部清理。如需进行全量测试，可通过 `execute_code` 循环调用 `tool_dispatcher.py` 完成。

```bash
# 完整测试流程（通过 execute_code 循环调用 tool_dispatcher.py）
# 示例：在 execute_code 中依次调用各工具并收集结果
```
