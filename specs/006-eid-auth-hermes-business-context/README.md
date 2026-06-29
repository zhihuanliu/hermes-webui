---
status: superseded
created: '2026-06-11'
tags: [eid, authentication, authorization, iframe, session, skill, ddd]
priority: high
---

# EID 用户认证与 Hermes 业务上下文

> **Superseded / 历史方案**：本规格已被
> [008-eid-record-scoped-hermes-integration](../008-eid-record-scoped-hermes-integration/README.md)
> 取代，仅保留为历史上下文。当前实现是 record-only：没有 EID login、用户身份、
> tenant、trusted proxy、delegation token 或远端 record authorization endpoint。
> 本文件下面的 `api/eid_context.py`、`eid_subject`、`eid_tenant`、用户 A/B 隔离、
> `/hermes/authorize` 等内容不得作为当前实现、测试或部署依据。

> **Status**: superseded | **Priority**: high | **Created**: 2026-06-11

## Overview

`eid-web` 将通过同站点反向代理嵌入 Hermes WebUI。当前开发阶段由
`record_id` 标识 EID 业务记录，后续引入用户登录后，必须保证用户只能查看
和操作自己有权访问的记录，同时不能读取其他用户在 Hermes 中产生的会话。

目标部署拓扑：

```text
https://eid.example.com/             -> eid-web
https://eid.example.com/api/         -> EID 后端
https://eid.example.com/assistant/   -> Hermes WebUI
```

本规格废弃“将 `record_id` 固定写入 profile `.env`”作为生产业务上下文的方式。
环境变量适合静态配置和密钥，不适合随用户、iframe 和会话动态变化的资源标识。

核心原则：

- 登录身份来自 EID 的安全 Cookie，不从 iframe URL 获取。
- iframe URL 只携带非秘密资源标识 `record_id`。
- `user_id`、JWT、长期令牌不得出现在 iframe URL。
- EID 后端是用户与记录授权关系的最终裁决者。
- Hermes profile 只表示 Agent 配置，不表示 EID 用户身份。
- Skill 使用服务端绑定的可信业务上下文，不直接读取固定 `record_id` 环境变量。

## User Requirements

本节是本规格的权威需求清单。后续设计、实现和验收不得降低或替换这些要求。

### UR-01：iframe 嵌入

- `hermes-webui` 必须允许被 `eid-web` 的机器人对话框通过 iframe 嵌入。
- 开发阶段父页面为 `http://localhost:5174`，Hermes 当前服务为
  `http://localhost:8787/chatbot`。
- 生产阶段通过同站点反向代理提供 `/assistant/chatbot`，不再让浏览器直接访问
  Hermes 内部端口。
- 现代浏览器使用 CSP `frame-ancestors`，老浏览器使用 `X-Frame-Options` 兜底。
- 同站点生产策略为 `frame-ancestors 'self'` 和 `X-Frame-Options: SAMEORIGIN`。

### UR-02：record_id 从 EID 页面传入

- `eid-web` 将当前 `activeRecordId` 作为 iframe URL 的 `record_id` 查询参数传入。
- `record_id` 是动态值，不能写死为
  `ad862e249e08461386f1fc86c9297719` 或其他开发样例值。
- iframe 加载后，Hermes 必须在创建或恢复会话时绑定该 `record_id`。
- Agent 调用 EID Skill 时，必须使用当前会话绑定且已通过授权的 `record_id`。
- 浏览器传入的 `record_id` 只是待校验的资源标识，不能直接视为已授权上下文。

### UR-03：按 record_id 创建和恢复独立会话

- 当前 record 首次打开时创建独立 Hermes 会话。
- 已存在该 record 的有效会话时恢复原会话，不重复创建。
- record 从 A 切换到 B 时进入 B 的独立会话；再切回 A 时恢复 A 的原会话。
- 用户主动点击“新会话”时，为当前用户和 record 创建新会话，并归档或替换旧的
  当前有效会话。
- 会话记录、上下文和 Skill 调用不得在不同 record 之间串用。

### UR-04：无 record_id 时允许普通聊天

- iframe 或独立打开 Hermes 时没有 `record_id`，仍允许创建和使用普通聊天会话。
- 普通聊天不绑定任何 EID record。
- 普通聊天中禁止执行依赖 record 的 EID 业务工具，并提示用户先选择或打开记录。
- 不得在无 `record_id` 时静默使用 Skill 的固定默认 record，以免访问错误业务数据。

### UR-05：Skill 调用 EID 后端

- Hermes Agent 已配置 EID Skill；Skill 内脚本会请求 EID 后端接口。
- Skill 不再把 profile `.env` 中的 `SHIP_LIGHTING_RECORD_ID` 作为生产数据来源。
- `record_id` 和用户身份由 Hermes 服务端的可信上下文绑定，模型不能自行指定或覆盖。
- EID 后端在每次业务数据访问时校验当前用户对 record 的权限，不能只依赖
  Hermes 前置校验。
- 无权访问时 Skill 不得返回目标 record 的任何业务数据。

### UR-06：用户登录和数据隔离

- `eid-web` 后续必须引入用户登录，并以 EID 登录身份作为用户归属的唯一来源。
- 不同登录用户只能看到自己拥有或被授权访问的 `record_id`。
- 用户只能创建、恢复、搜索、查看、导出和删除属于自己的 Hermes 会话。
- 用户 A 即使知道用户 B 的 `record_id`，也不能访问 B 的 record 或相关 Hermes 会话。
- `user_id` 不得由 iframe URL、请求体或模型参数传入；必须由服务端认证上下文产生。
- Hermes profile 不等同于 EID 用户，不能用不同 profile 代替正式用户登录和授权。

### UR-07：同站点认证

- Hermes 通过 EID 同站点反向代理部署在 `/assistant/`。
- EID 登录 Cookie 必须能覆盖 `/assistant/`，且使用安全 Cookie 属性。
- 反向代理负责验证登录态、清除客户端伪造身份头并注入可信身份。
- 登录失效后 Hermes 不得继续使用旧用户上下文，也不得降级为匿名 record 会话。

### UR-08：DDD 与规格驱动交付

- 本次及后续实现必须按 DDD 明确身份、会话、record 和 Skill 集成的领域边界。
- 需求、领域不变量、接口契约、实施步骤和验收测试必须保存在 LeanSpec 中。
- 行为变更必须同步更新架构、接口、安全、测试文档和 `CHANGELOG.md`。
- 实现完成前本规格保持 `planned` 或 `in-progress`；全部验收通过后才能改为
  `complete`。

### Development Transition

当前尚未接入 EID 登录时，只允许在明确开启的开发模式下使用一个固定的
`development_subject` 验证 record 会话流程。该身份不得由 URL 提供，并且开发模式
必须在生产环境默认关闭。开发阶段可以使用样例 `record_id` 调试，但不得恢复
`SHIP_LIGHTING_RECORD_ID` 的生产默认值语义。

## Domain Model

### Bounded Contexts

- **EID Identity and Access**：登录、用户身份、record 所有权和委托令牌。
- **Hermes Conversation**：会话创建、恢复、搜索、归档和用户隔离。
- **EID Skill Integration**：把可信业务上下文绑定到 Agent 工具和脚本调用。

### Values and Services

- `AuthenticatedEidSubject`：由 EID 认证系统签发的稳定用户标识。
- `EidTenantId`：可选租户标识，为多租户部署预留。
- `RecordId`：EID 业务记录标识，不代表访问权限。
- `TrustedEidContext`：仅存在于服务端运行时的可信上下文。
- `AuthorizeRecordAccess`：向 EID 后端验证当前用户是否能访问指定 record。
- `ResolveRecordSession`：为当前用户和 record 创建或恢复 Hermes 会话。
- `EidToolContextBinder`：向 EID 专用工具绑定已鉴权的业务上下文。

```text
TrustedEidContext {
  subject,
  tenant,
  record_id,
  delegation_token
}
```

### Invariants

- 用户身份只能来自受信任的反向代理认证结果，不能来自浏览器请求体或 URL。
- `record_id` 必须先通过 EID 授权检查，才能用于创建、恢复或查询 Hermes 会话。
- 会话归属键为 `(tenant, subject, record_id, agent_profile)`。
- 无 `record_id` 的普通聊天仍绑定当前用户，但不绑定 EID 记录。
- 所有会话读取、搜索、删除、导出和聊天操作都必须校验当前用户归属。
- 两个用户即使使用相同的 `record_id`，也不得共享 Hermes 会话。
- 委托令牌不得写入会话、日志、URL、提示词或浏览器存储。
- profile `.env` 中的 `SHIP_LIGHTING_RECORD_ID` 不得决定生产会话归属。
- 无 `record_id` 时不得使用固定默认 record 执行 EID 业务操作。
- 任何开发期固定身份或样例 record 都必须受显式开发开关约束，生产默认关闭。

## Design

### Authentication and Reverse Proxy

1. 用户登录 EID 后，服务端设置 `HttpOnly`、`Secure`、`SameSite=Lax`、
   `Path=/` 的登录 Cookie。
2. `eid-web` 使用相对同源地址加载 `/assistant/chatbot?record_id=<id>`。
3. 反向代理对 `/assistant/*` 执行 EID 认证子请求。
4. 代理先删除客户端可能伪造的身份头，再注入：
   - `X-EID-Subject`：不可变用户标识。
   - `X-EID-Tenant`：可选租户标识。
   - `X-EID-Delegation`：短期、限定受众和权限的委托令牌。
5. Hermes 调用 EID 后端验证当前 subject 是否有权访问 URL 中的 `record_id`。
6. 无权限返回 `403`，记录不存在返回 `404`；两种情况都不得创建或恢复会话。

Hermes 生产服务只监听内网地址或 Unix socket，禁止绕过反向代理直接访问。
聊天写接口继续执行 CSRF 或 `Origin` 校验。

### Session Resolution

Hermes Session 增加以下持久化字段：

```text
eid_subject: string | null
eid_tenant: string | null
record_id: string | null
context_type: "eid-record" | "general"
```

新增会话解析接口：

```http
POST /assistant/api/session/resolve
Content-Type: application/json

{
  "record_id": "ad862e249e08461386f1fc86c9297719",
  "force_new": false
}
```

接口不得接收 `user_id`。用户和租户从可信认证上下文读取。

行为规则：

- 有 `record_id`：鉴权成功后恢复当前归属键下最近的未归档会话；不存在则创建。
- `force_new=true`：归档当前归属键下的有效会话并创建新会话。
- A -> B -> A：分别创建或恢复当前用户自己的 A、B 会话。
- 无 `record_id`：进入当前用户的普通聊天，不启用 EID record 工具上下文。
- 登出或切换账号后，不得继续访问前一用户的会话。

### Skill Redesign

删除现有 Skill 规则：

```text
record_id 由 SHIP_LIGHTING_RECORD_ID 环境变量控制
```

同时删除生产环境中的固定默认 record：

```text
ed18461b23884c569e2366c228378825
```

替换为以下 Skill 契约：

```text
规则4：EID 业务上下文由 Hermes 服务端提供。
- Skill 不读取、猜测或缓存 record_id、user_id。
- Skill 不允许模型自行提供或覆盖 user_id。
- Skill 只能通过 EID 专用工具访问业务数据。
- EID 专用工具自动绑定当前已鉴权用户和当前会话 record_id。
- 无 record_id 时不执行记录相关操作，并提示用户先打开或选择记录。
- EID 后端是记录访问权限的最终裁决者。
```

推荐将现有脚本封装为服务端工具，例如：

```text
eid_get_ship_summary()
eid_query_lighting(query)
eid_update_lighting(command)
```

公开工具参数不包含 `user_id` 和 `record_id`。`EidToolContextBinder` 在工具执行时
自动注入 `TrustedEidContext`。脚本仍可接收显式 `record_id` 参数，但该参数只能由
服务端工具执行器生成，不能由模型或浏览器覆盖。

委托令牌通过子进程专用环境或标准输入传递，不放入命令行。每个工具调用使用
独立环境副本，禁止为动态用户上下文修改 WebUI 进程的全局 `os.environ`。

`SHIP_LIGHTING_RECORD_ID` 仅允许作为本地单用户开发兼容项，通过显式配置开关
启用；生产环境默认关闭，并在迁移完成后删除。

### Frontend Behavior

- `eid-web` 登录后仅从 EID 后端获取当前用户有权访问的 record 列表。
- `activeRecordId` 必须来自该列表或已鉴权的导入结果。
- iframe 使用 `/assistant/chatbot?record_id=<activeRecordId>`。
- 切换 record 时 iframe 解析并恢复对应会话。
- 用户篡改 URL 中的 `record_id` 不能绕过服务端权限检查。
- 登录失效时 iframe 显示统一的重新登录状态，不退化为匿名 record 会话。
- 无 record 时允许普通聊天，但 EID 记录工具不可执行。

开发环境使用 Vite 将 `/assistant` 代理到 `http://localhost:8787`，保持浏览器视角
下的同源路径。生产响应使用：

```text
Content-Security-Policy: frame-ancestors 'self'
X-Frame-Options: SAMEORIGIN
```

### Runtime Compatibility

Native、Gateway 和未来 Runner 后端必须共享同一 `TrustedEidContext` 契约。
如果某个后端不能可靠传递用户、record 和委托令牌，应明确拒绝 EID 业务工具，
不得静默回退到 profile `.env` 或 WebUI 服务进程环境。

## Implementation Notes

本节记录当前已落地实现的细节，作为代码评审与后续迭代的基线。

### 模块与职责

| 位置 | 职责 |
| --- | --- |
| `api/eid_context.py` | 可信身份解析（代理头 / 开发模式）、`record_id` 与身份格式校验、EID 记录授权客户端（fail-closed）、授权正向结果 TTL 缓存、会话归属判定辅助函数 |
| `api/routes.py` | 请求级守卫：GET/POST 中携带 `session_id` 的请求统一做归属与记录授权检查；`/api/session/resolve` 创建/恢复记录会话；会话列表与搜索按 `(subject, tenant, record)` 过滤；浏览器响应剥离 `eid_subject`/`eid_tenant` |
| `api/models.py` | `Session` 新增持久化字段 `eid_subject`/`eid_tenant`/`record_id`/`context_type`，写入 sidecar 与 `_index.json`；空的 EID 会话不会被“隐藏空 Untitled 会话”规则吞掉（否则 resolve 无法恢复刚创建的记录会话） |
| `api/streaming.py` | 线程级 env 注入 `HERMES_EID_SUBJECT`/`HERMES_EID_RECORD_ID`；EID 会话剥离 profile 级 `SHIP_LIGHTING_RECORD_ID`；Agent 非持久化上下文携带 `record_id`/`context_type` |
| `api/helpers.py` | `redact_session_data` 在响应层统一移除 `eid_subject`/`eid_tenant`（覆盖 SSE `done` 事件与压缩等路径） |
| `static/chatbot.html` / `boot.js` / `sessions.js` | 从 iframe URL 读取 `record_id`（仅资源标识）；启动时调 `/api/session/resolve` 恢复或创建；“新会话”按钮带 `force_new` 归档旧记录会话；列表/搜索请求附加 `record_id` 作用域 |

### 配置项

| 环境变量 | 默认 | 说明 |
| --- | --- | --- |
| `HERMES_WEBUI_EID_CONTEXT` | 关 | 总开关；关闭时所有 EID 守卫为 no-op |
| `HERMES_WEBUI_EID_TRUST_PROXY` | 关 | 信任代理注入的 `X-EID-Subject`/`X-EID-Tenant`/`X-EID-Delegation` |
| `HERMES_WEBUI_EID_AUTHORIZE_URL` | 空 | 记录授权端点；缺失时记录会话 fail-closed（503） |
| `HERMES_WEBUI_EID_AUTHORIZE_TIMEOUT` | `5` | 授权请求超时秒数（0.1–30） |
| `HERMES_WEBUI_EID_AUTHORIZE_CACHE_TTL` | `30` | 授权正向结果缓存秒数（0 禁用，上限 300）。仅缓存“允许”，拒绝/404/不可用永不缓存；权限回收延迟以该 TTL 为上界 |
| `HERMES_WEBUI_EID_DEVELOPMENT_MODE` | 关 | 开发模式：使用固定 `development_subject`，跳过远端记录授权 |
| `HERMES_WEBUI_EID_DEVELOPMENT_SUBJECT` / `_TENANT` | 空 | 开发模式固定身份；不得来自 URL |

### 请求守卫语义

- GET：`/api/*?session_id=` 统一先做归属检查，非本人会话一律 `404`（不暴露存在性）。
- POST：除 `/api/session/new`、`/api/session/resolve`、恢复与导入端点外，body 携带
  `session_id` 的请求统一做归属检查；`/api/session/new` 单独校验 `prev_session_id`。
- 流接口：`stream_id` 先经 run journal 或活跃会话反查 `session_id` 再做归属检查；
  无法反查时 fail-closed 返回 `404`。
- 错误映射：身份缺失/失效 `401`、无权 `403`、记录不存在 `404`、授权服务不可用 `503`。
- 浏览器响应不回传 `eid_subject`/`eid_tenant`：列表/详情/解析端点显式剥离，
  其余会话载荷在 `redact_session_data` 响应层统一剥离。

### 已知限制与后续事项

- Skill 仍是脚本形态，`eid_get_*` 服务端工具与 `EidToolContextBinder` 未落地（对应
  Plan 未勾选项）；当前仅通过线程 env 传递 `HERMES_EID_SUBJECT`/`HERMES_EID_RECORD_ID`。
- 委托令牌仅存在于请求作用域，尚未向工具子进程传递（待工具化时实现）。
- `/api/session/import*` 在 EID 模式下不打用户归属标记，导入结果对 EID 用户不可见；
  嵌入部署应禁用导入入口或后续补齐归属标记。
- `/api/session/resolve` 无并发去重：同一 record 的两个并发首次加载可能各建一个会话，
  下次 resolve 恢复最近一个，旧会话保持未归档。可接受，后续可加 per-key 锁。
- EID 模式下 `/api/chat/stream/status` 对无法归属的 stream 返回 `404`（原契约为
  `{active:false}`）；前端轮询路径均有 try/catch，影响有限。
- `boot.js` 解析失败（401/403/503）时仅停留在空界面并打 console 警告，统一的
  “重新登录/无权限”状态页由 `eid-web` 侧承担（UR-07 前端项未完成）。

## Plan

- [ ] 在 EID 后端实现登录、当前用户查询和 record 所有权校验。
- [ ] 配置同站点反向代理、认证子请求和可信身份头清洗/注入。
- [ ] 在 `eid-web` 增加登录态、凭证请求策略和用户可见 record 列表。
- [ ] 使用相对 `/assistant` 地址嵌入 Hermes，并传递当前 `record_id`。
- [x] 在 Hermes 中实现可信身份解析和 record 授权客户端。
- [x] 扩展 Session 聚合及索引，实现用户/record 归属和解析接口。
- [ ] 将 Skill 改造成 EID 专用工具调用，移除生产固定 record 环境变量。
- [ ] 为 Native、Gateway 和 Runner 实现一致的运行时上下文绑定。
- [x] 更新 Hermes 部署、接口契约、安全说明、测试文档和变更日志。

## Test

- [ ] `UR-01`：开发和生产拓扑下 iframe 均可加载，非允许站点无法嵌入。
- [ ] `UR-02`：动态 `activeRecordId` 正确进入 iframe、会话和 Skill 上下文。
- [ ] `UR-03`：同一用户执行 A -> B -> A 时分别创建并恢复正确会话。
- [ ] `UR-04`：无 `record_id` 时普通聊天正常，且不会使用固定默认 record。
- [ ] `UR-05`：EID Skill 仅使用服务端绑定上下文，模型无法覆盖用户或 record。
- [ ] `UR-06`：用户只能查看自己的 record 和 Hermes 会话。
- [ ] `UR-07`：登录失效或账号切换后，旧身份和会话均不可继续访问。
- [ ] `UR-08`：接口、领域不变量、测试和发布文档与实现保持一致。
- [ ] 用户 A 只能获取和打开属于 A 的 record。
- [ ] 用户 A 篡改为用户 B 的 `record_id` 时返回 `403`。
- [ ] 用户 A、B 使用相同 `record_id` 时不会共享会话。
- [ ] 当前用户执行 A -> B -> A 时恢复正确会话。
- [ ] 登出后登录另一账号无法读取原账号的会话。
- [ ] 无 `record_id` 时普通聊天正常，EID 业务工具拒绝执行。
- [ ] Skill 和脚本无法通过模型参数覆盖可信用户或 record。
- [ ] 并发用户、record、profile 执行时上下文不会串号。
- [ ] 委托令牌不会出现在日志、会话 JSON、提示词和错误响应中。
- [ ] Vite 开发代理和生产反向代理下 Cookie、iframe 和安全头均正常。
- [ ] Native、Gateway 和 Runner 后端通过相同上下文契约测试。

## Notes

### Decision Record

- 选择同站点反向代理，降低 iframe Cookie 和跨域通信复杂度。
- 不把 EID 用户映射为 Hermes profile，避免混淆身份边界与 Agent 配置边界。
- 不信任 iframe URL 中的用户信息；URL `record_id` 仅是待授权的资源标识。
- 不采用动态全局环境变量传递用户上下文，避免并发会话串号。
- EID 后端在数据访问时再次鉴权，Hermes 的会话过滤不能替代资源授权。

### Rollout

1. 先实现 EID 登录和 record 授权接口。
2. 再实现 Hermes 用户会话隔离和只读 EID 工具。
3. 验证审计与并发隔离后开放写工具。
4. 最后关闭并删除 `SHIP_LIGHTING_RECORD_ID` 兼容模式。
