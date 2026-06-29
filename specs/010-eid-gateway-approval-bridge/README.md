---
status: in-progress
created: '2026-06-16'
tags: [eid, gateway, approval, iframe, runtime]
priority: high
---

# EID Gateway 审批桥接

> **Status**: in-progress | **Priority**: high | **Created**: 2026-06-16

## Overview

在 EID 嵌入场景中，浏览器链路是：

```text
eid-web iframe -> Hermes WebUI -> remote Hermes Gateway Agent
```

当远程 Gateway Agent 执行 `execute_code` 或其他需要人工授权的工具时，Agent
会在自然语言中提示用户“请在 WebUI 点击 Approve/Allow”，但 Hermes WebUI
聊天界面没有出现现有审批卡片，也就没有 `Allow once`、`Allow session`、
`Allow always` 或 `Deny` 按钮。

根因不是 iframe 裁剪，也不是用户没有找到按钮，而是 Gateway 分离模式缺少审批桥接：

- Native WebUI 运行路径的审批请求会进入 WebUI 的 `_pending` 审批队列、
  `/api/approval/pending` 和 `/api/approval/stream`。
- Gateway-backed browser chat 原先使用 `/v1/chat/completions` 流式响应，只转发
  token 和工具进度。
- 远程 Gateway run 的 `approval.request` 没有被翻译成 WebUI 已有的 `approval`
  SSE 事件，也没有注册到 WebUI pending 队列。
- 用户点击 WebUI 审批按钮后，`/api/approval/respond` 也没有远端 run id，无法把
  选择转发到 Gateway。

本规格记录这次修复的目标：保持 WebUI 现有审批 UI 不变，只补齐 Gateway run
事件到 WebUI 审批通道的协议桥接。

## Design

### Runtime Contract

Gateway-backed WebUI chat 默认使用 run transport：

```text
POST /v1/runs
GET  /v1/runs/{run_id}/events
POST /v1/runs/{run_id}/approval
```

Gateway run SSE 必须至少能发出：

```json
{"event":"approval.request","run_id":"run_...","command":"...","description":"...","pattern_key":"execute_code","pattern_keys":["execute_code"]}
```

WebUI 将该事件标准化为现有审批卡片 payload：

```json
{
  "approval_id": "webui-generated-id",
  "command": "...",
  "description": "...",
  "pattern_key": "execute_code",
  "pattern_keys": ["execute_code"]
}
```

`approval_id` 仍由 WebUI 生成，用于前端精确匹配当前卡片；Gateway 自身的
`approval_id` 如果存在，作为 `gateway_approval_id` 保留，不改变前端协议。

### Event Bridge

当 WebUI 读取到 Gateway `approval.request`：

1. 解析并标准化 Gateway payload。
2. 调用 WebUI 现有 `submit_pending(session_id, payload)`。
3. 将队列头部作为 `approval` SSE 事件写入当前 chat stream。
4. `/api/approval/pending` 和 `/api/approval/stream` 立即能返回同一个 pending。
5. 前端沿用现有 `showApprovalCard()` 渲染审批卡片。

这条路径不新增浏览器 UI，不新增 iframe postMessage 协议，也不让 EID 页面参与审批。

### Response Bridge

WebUI 为每个活跃 Gateway run 维护短生命周期映射：

```text
session_id -> { run_id, stream_id, registered_at }
```

用户点击审批按钮时：

```text
POST /api/approval/respond
{ "session_id": "...", "approval_id": "...", "choice": "once|session|always|deny" }
```

如果该 session 有活跃 Gateway run，WebUI 将 choice 转发到：

```text
POST /v1/runs/{run_id}/approval
{ "choice": "once|session|always|deny" }
```

转发成功后，远程 Gateway run 继续执行，后续 token/tool/done 事件仍通过同一 chat
stream 到达浏览器。

### EID Record Context

Gateway 请求必须继续携带当前 record：

```text
X-EID-Record-Id: <session.record_id>
```

不得发送旧身份头或委托头；审批桥接只继承 008 的 record-only 边界。

审批桥接只解决运行时控制面，不改变 008 的 record-only 会话隔离模型。

### Compatibility

`HERMES_WEBUI_GATEWAY_TRANSPORT` 可显式设为 completions 兼容旧 Gateway：

```env
HERMES_WEBUI_GATEWAY_TRANSPORT=completions
```

但 completions transport 不能可靠承载阻塞式审批；需要审批卡片的 EID 嵌入部署应使用
默认 runs transport，并确认 Gateway 支持 `/v1/runs`、`/events` 和 `/approval`。

## Implementation Details

### 1. Gateway chat 默认切到 runs transport

实现位置：`api/gateway_chat.py`

新增 `HERMES_WEBUI_GATEWAY_TRANSPORT` 解析逻辑：

```text
unset / runs / unknown -> runs
completions / chat / chat_completions / chat-completions -> completions
```

这样 EID + Gateway 场景默认走可表达审批状态的 run API，而旧
`/v1/chat/completions` 只作为显式兼容模式保留。旧测试中需要 completions 行为的
用例都显式设置：

```env
HERMES_WEBUI_GATEWAY_TRANSPORT=completions
```

### 2. WebUI 创建远程 Gateway run 并保存 run 映射

实现位置：`api/gateway_chat.py`

Gateway-backed chat 启动后，当 transport 为 `runs`：

1. WebUI 先调用 `POST /v1/runs`。
2. 请求体包含当前用户输入、`session_id`、system instructions、
   conversation history、model 和 provider。
3. Gateway 返回 `run_id` 后，WebUI 调用
   `register_gateway_session_run(session_id, run_id, stream_id)`。
4. `_GATEWAY_SESSION_RUNS` 暂存：

```text
session_id -> {
  run_id,
  stream_id,
  registered_at
}
```

这个映射只用于本次活跃流的 approval respond 路由，stream 结束时通过
`clear_gateway_session_run(session_id, stream_id)` 清理。

### 3. WebUI 消费 Gateway run SSE 并翻译事件

实现位置：`api/gateway_chat.py`

创建 run 后，WebUI 连接：

```text
GET /v1/runs/{run_id}/events
Accept: text/event-stream
```

`_consume_gateway_sse_stream()` 逐行解析 SSE，并将 Gateway run event 翻译成 WebUI
已有 stream event：

| Gateway event | WebUI event |
| --- | --- |
| `message.delta` | `token` |
| `approval.request` | internal `__approval__` -> WebUI `approval` |
| `clarify.request` | internal `__clarify__` -> WebUI `clarify` |
| `tool.started` | `tool` |
| `tool.completed` | `tool_complete` |
| `run.completed` | terminal completion |
| `run.failed` / `error` | `apperror` |

这保证浏览器端仍复用 `static/messages.js` 的现有渲染和审批逻辑。

### 4. approval.request 桥接到 WebUI pending 队列

实现位置：`api/gateway_chat.py` 调用 `api.routes.submit_pending`

当 `_gateway_run_event()` 识别到：

```json
{"event":"approval.request", "...":"..."}
```

WebUI 执行：

1. `_gateway_approval_payload()` 标准化字段：
   - `command`
   - `description`
   - `pattern_key`
   - `pattern_keys`
   - optional `gateway_approval_id`
2. `_bridge_gateway_approval_to_webui()` 调用 `submit_pending(session_id, payload)`。
3. `submit_pending()` 为该 approval 生成 WebUI `approval_id`，并写入 `_pending`。
4. 同步通知 `/api/approval/stream` 的 SSE subscribers。
5. 当前 chat stream 也收到一个 `approval` event。

因此前端会像 native Agent 审批一样显示同一张审批卡片，不需要 EID iframe 做任何
额外处理。

### 5. /api/approval/respond 转发到远端 Gateway run

实现位置：`api/routes.py` 和 `api/gateway_chat.py`

前端点击 `Allow once` / `Allow session` / `Allow always` / `Deny` 后仍调用：

```text
POST /api/approval/respond
```

`_resolve_approval_legacy()` 先按 `approval_id` 从 WebUI `_pending` 队列弹出对应项，
然后判断当前 session 是否有活跃 Gateway run：

```text
webui_gateway_chat_enabled() && gateway_session_has_active_run(sid)
```

如果有，调用 `forward_gateway_approval_response(session_id, choice)`，向 Gateway 发：

```text
POST /v1/runs/{run_id}/approval
Content-Type: application/json

{"choice":"once|session|always|deny"}
```

Gateway 返回 `resolved > 0` 或 HTTP `200/201/202` 时，WebUI 认为响应已送达，远程
run 继续执行。

### 6. EID record header 沿用 record-only 方案

实现位置：`api/gateway_chat.py`

`_gateway_request_headers()` 统一生成 Gateway 请求头：

```text
Authorization: Bearer <gateway key>
X-Hermes-Session-Id: <session_id>
X-Hermes-Session-Key: webui:<session_id>
X-EID-Record-Id: <session.record_id>
```

如果 session 没有 `record_id`，则不发 `X-EID-Record-Id`。旧的用户身份和委托头不得发送。

### 7. 测试覆盖

实现位置：`tests/test_webui_gateway_chat_backend.py`

新增或调整的关键测试包括：

- `test_gateway_approval_payload_normalizes_run_event_fixture`
- `test_gateway_run_event_translates_approval_request_marker`
- `test_gateway_run_sse_forwards_approval_to_webui_stream`
- `test_forward_gateway_approval_response_posts_to_remote_run`
- `test_gateway_chat_forwards_eid_record_header_for_record_scoped_session`

同时旧 completions 测试显式设置 `HERMES_WEBUI_GATEWAY_TRANSPORT=completions`，避免
默认 runs transport 改变旧断言。

## Plan

- [x] 增加 Gateway transport 选择，默认使用 `runs`。
- [x] 用 `POST /v1/runs` 创建远程 run，并保存 `session_id -> run_id` 映射。
- [x] 消费 `GET /v1/runs/{run_id}/events` SSE。
- [x] 将 `approval.request` 桥接到 WebUI `submit_pending()` 和 chat stream
  `approval` 事件。
- [x] 让 `/api/approval/respond` 在 Gateway-backed active run 中转发到远端
  `/v1/runs/{run_id}/approval`。
- [x] 保留 completions transport 作为显式兼容模式。
- [x] Gateway 请求继续携带 `X-EID-Record-Id`。
- [ ] 在真实 EID iframe + 远程 Gateway Agent 环境中验证 `execute_code`
  审批卡片出现并能 unblock run。
- [ ] 明确 Gateway `/v1/runs` 事件字段是否包含稳定远端 approval id；如果需要多审批
  精确映射，再把 `gateway_approval_id` 纳入 response body。

## Test

- [x] Gateway `approval.request` payload 能标准化为 WebUI approval payload。
- [x] Gateway run SSE 中的 `approval.request` 会向 chat stream 发出 `approval` 事件。
- [x] WebUI pending 队列会为桥接 approval 生成 `approval_id`。
- [x] `POST /api/approval/respond` 能将 choice 转发到
  `/v1/runs/{run_id}/approval`。
- [x] Gateway completions transport 旧测试显式设置
  `HERMES_WEBUI_GATEWAY_TRANSPORT=completions` 后仍保持原行为。
- [x] record-scoped session 的 Gateway 请求携带 `X-EID-Record-Id`，且不携带旧 EID
  身份或委托头。
- [ ] 真实浏览器手动验收：EID iframe 中触发 `execute_code` 后出现审批卡片。
- [ ] 真实 Gateway 手动验收：点击 `Allow once` 后远程 run 继续执行并返回最终结果。

## Notes

- 本修复属于运行时控制面桥接，不属于 EID iframe 布局修复。
- WebUI 仍是审批 UI 的拥有者；Gateway 是审批状态和执行阻塞的拥有者。
- `_GATEWAY_SESSION_RUNS` 是短生命周期 respond 路由表，不是 durable runner registry。
  WebUI 重启后的 active Gateway run 重连不是本规格范围。
- 如果未来 Gateway 支持 clarify 或更完整的 run event family，应沿用同一桥接原则：
  Gateway event 进入 WebUI 现有 pending/SSE/UI 通道，用户响应再转发回远端 run。
