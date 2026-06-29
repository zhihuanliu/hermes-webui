# 当前仓库改动审查报告

生成时间：2026-06-17  
工作分支：`haizhou/chatbot`  
比较基线：`origin/master` / `master`，提交 `163df174`（`v0.51.262`）  

## 1. 仓库状态概览

当前分支没有配置 upstream。按本地历史看，`haizhou/chatbot` 基于 `origin/master`
继续开发，已有 3 个本地提交：

- `74c2db85 feat: 新增chatbot专属页面`
- `ca52ebe1 feat: add Skills`
- `0b994e8e debug: 完成开发环境调试`

相对 `origin/master`，已跟踪文件差异约为：

- 49 个文件变更
- 约 6,849 行新增，223 行删除
- 主要集中在 EID record-scoped chatbot、Gateway chat approval 桥、ship-lighting Skill、嵌入安全头、Docker/Windows 支持、中文文档和测试

当前工作区仍是 dirty 状态：

- 已暂存：`static/boot.js`、`static/chatbot.html`、`static/workspace.js`
- 未暂存：大量源码、文档、测试改动，以及 `api/eid_context.py` 的删除
- 未跟踪但被当前代码依赖：`api/eid_record_context.py`
- 未跟踪测试/规范/文档：`tests/test_chatbot_startup_loading.py`、`specs/`、`.lean-spec/`、多份中文 docs
- 未跟踪生成产物：`.tmp-pytest/`、`Skills/ship-lighting.zip`、`hermes-webui-eid.tar`

特别注意：`hermes-webui-eid.tar` 约 882 MB，`.tmp-pytest/` 约 52 个文件、119 KB。这些看起来是构建/测试产物，不应进入提交。

## 2. 主要改动说明

### 2.1 独立 chatbot 页面

新增 `static/chatbot.html`，作为嵌入式中文聊天页面：

- 固定中文 locale 和助手显示名
- 去掉右侧 workspace panel，使用更窄的 iframe 友好布局
- 左侧会话列表改为 overlay slide-over
- 启动时显示 loading 状态，避免 iframe 空白
- URL 保持在 `/chatbot`，会话通过 `?session=<id>` 表达，避免刷新时落回普通 `index.html`
- 从 URL 读取 `record_id`，写入 `window.__HERMES_CHATBOT_CONTEXT__`
- 对同源 unsafe fetch/sendBeacon 自动加 CSRF header

相关前端改动：

- `static/boot.js`：启动时如果存在合法 `record_id`，调用 record resolve 路径创建/恢复会话
- `static/sessions.js`：新增 record scope 工具函数，EID record 会话走 `/api/session/resolve`
- `static/workspace.js`：API 请求在 chatbot record 上下文中自动附加 `record_id`

### 2.2 EID record-only 会话上下文

新增 `api/eid_record_context.py`，把 EID 集成简化为 record-only 模式：

- `HERMES_WEBUI_EID_RECORD_CONTEXT=1` 开启
- `record_id` 只允许 `[A-Za-z0-9_-]`，最长 128
- 不再解析 EID 用户身份、tenant、delegation token
- 不再调用远端 record authorization endpoint
- 仅用 `record_id` 做会话分区和业务上下文路由

后端模型和路由变化：

- `api/models.py` 的 `Session` 新增 `record_id`、`context_type`；旧 `eid_subject`、`eid_tenant` 字段已从 Session 持久化和输出中移除
- `api/routes.py` 新增 `/api/session/resolve`
- `/api/sessions`、`/api/sessions/search`、带 `session_id` 的 GET/POST 在 record 模式下做 record 匹配
- 返回浏览器的 session payload 只暴露 record-scoped 所需上下文

运行时变化：

- `api/streaming.py` 在 agent 环境中注入 `HERMES_EID_RECORD_ID`
- WebUI ephemeral system prompt 会带上 `record_id` 和 `context_type`
- profile 级 `SHIP_LIGHTING_RECORD_ID` 在 record session 中被动态 record 覆盖/规避

### 2.3 Gateway-backed chat 与 approval 桥

`api/gateway_chat.py` 从原先的 OpenAI-compatible completions bridge 扩展为两种 transport：

- 默认 `runs`：`POST /v1/runs` + `GET /v1/runs/{run_id}/events`
- 兼容 `completions`：`POST /v1/chat/completions`

新增能力：

- 记录 WebUI session 到远端 Gateway run 的映射
- 将 Gateway `approval.request` SSE 转成 WebUI `approval` 事件
- `/api/approval/respond` 在 gateway active run 存在时转发到 `POST /v1/runs/{run_id}/approval`
- Gateway 请求携带 `X-EID-Record-Id`
- run events 可翻译 `message.delta`、`tool.started`、`tool.completed`、`run.completed`、`run.failed`
- gateway turn settle 后写回 WebUI session，并保持 context/display message 分层

文档同步到了 `docs/advanced-chat-setup.md` 和 `CHANGELOG.md`。

### 2.4 ship-lighting Skill

新增 `Skills/ship-lighting/`：

- `SKILL.md`：中文业务 skill 指南
- 多个 `references/*.md`：接口发现、数据库 schema、灯具类型、组合流程、测试报告等
- `scripts/api_client.py`：HTTP API 客户端，默认 `SHIP_LIGHTING_API_BASE=http://192.168.208.23:5000/api/v1`
- `scripts/param_validator.py`：工具参数规则、校验和帮助信息
- `scripts/tool_dispatcher.py`：统一调度工具，绑定当前 `HERMES_EID_RECORD_ID`

安全意图是清晰的：模型不能在参数中提供或覆盖 `record_id`、用户身份或 delegation token；调度器只从 Hermes 服务端注入的环境变量取 record。

### 2.5 嵌入安全头、CSRF、Docker/Windows

安全头变化：

- `api/helpers.py` 将 `X-Frame-Options` 从 `DENY` 改为 `ALLOW-FROM <origin>`
- CSP 增加 `frame-ancestors 'self' <origin>`
- `server.py` 的 Report-Only CSP 使用同一个 `FRAME_ANCESTORS_VALUE`

CSRF 变化：

- `api/routes.py` 支持逗号分隔的 `X-Forwarded-Host` 代理链

Docker/Windows/运维变化：

- 新增 `docker-compose.eid-webui.yml`
- `docker_init.bash` 为 `/app/venv` volume 修正 owner
- `start.ps1` 优先使用显式 `HERMES_HOME\hermes-agent`，支持 WSL UNC 路径
- `api/kanban_bridge.py` 针对 Windows + WSL UNC 路径跳过不兼容的 `msvcrt` 初始化锁

### 2.6 文档与测试

新增/更新：

- `README.md`：EID record-scoped embedded chat、iframe embedding、Gateway 环境变量
- `.env.example`：新增 EID/Gateway 配置示例
- `ARCHITECTURE.md`：记录 `HERMES_EID_RECORD_ID` 和 record-only 模式
- `TESTING.md`：新增 EID embedded record-session 手工检查
- 中文文档：`docs/onboarding-and-secondary-development.zh-CN.md`、`docs/api-webui-map.zh-CN.md`、`docs/sessions-js-reading-guide.zh-CN.md`、`docs/messages-js-reading-guide.zh-CN.md`
- 新增测试：`tests/test_eid_business_context.py`、`tests/test_iframe_embedding_headers.py`、`tests/test_chatbot_startup_loading.py`
- 扩展测试：`tests/test_webui_gateway_chat_backend.py`、CSRF/CSP/Kanban/session 相关测试

## 3. 审查发现

### P1：嵌入 origin 默认值与文档/测试不一致

`api/helpers.py` 当前默认值仍是 `http://localhost:5173`：

- `EMBED_ALLOWED_ORIGIN`
- `FRAME_ANCESTORS_VALUE`
- `LEGACY_X_FRAME_OPTIONS_VALUE`

但 `README.md`、`TESTING.md`、`tests/test_iframe_embedding_headers.py`、`tests/test_sprint19.py` 都要求 `http://localhost:5174`。

已复现失败：

```text
tests/test_sprint19.py::test_security_headers_on_json
expected: ALLOW-FROM http://localhost:5174
actual:   ALLOW-FROM http://localhost:5173
```

建议：把 `api/helpers.py` 的默认值统一改为 5174，或反向修正文档/测试；从当前变更意图看，应改代码默认值。

### P1：record-only 模式下 `/chatbot` 无 `record_id` 的普通聊天路径会坏（已修复）

此前 `TESTING.md` 写明：

> Open `/chatbot` without `record_id`; expect ordinary chat and no fixed record fallback.

但 `api/routes.py` 的 `_eid_filter_session_rows()` 在 `HERMES_WEBUI_EID_RECORD_CONTEXT=1` 时对 session list/search 强制要求 `record_id`。前端在没有 record 时不会附加 `record_id`，于是：

- `/api/sessions` 会返回 `record_id is required`
- `/api/sessions/search` 同样会失败
- 普通聊天的会话列表、搜索、删除后加载剩余会话等路径都会受影响

处理结果：产品语义已明确为“无 `record_id` 时禁止聊天”。`static/boot.js` 会在首次 session list 请求前识别缺失或非法 `record_id` 并停止启动；`static/chatbot.html` 显示页面内阻断提示，禁用输入框、新建会话和发送按钮；`static/sessions.js`、`static/messages.js` 也加入了防绕过 guard。测试 `tests/test_chatbot_startup_loading.py` 已覆盖该 guard 必须早于 `renderSessionList()`。

### P1：被源码 import 的 `api/eid_record_context.py` 仍是未跟踪文件

`api/routes.py` 顶部已经 `from api.eid_record_context import ...`。如果只提交已跟踪修改而漏掉这个未跟踪文件，干净 checkout 会在导入 `api.routes` 时直接失败。

建议：将 `api/eid_record_context.py` 纳入提交；同时确认 `tests/test_chatbot_startup_loading.py`、`docker-compose.eid-webui.yml`、新增中文 docs/specs 是否都属于本次 PR 范围。

### P2：`test_chatbot_startup_loading.py` 与实现细节不一致（已修复）

已复现失败：

```text
tests/test_chatbot_startup_loading.py::test_chatbot_forces_chinese_embed_locale
assert "typeof S!=='undefined'&&S._bootReady" in CHATBOT_HTML
```

实际实现为：

```js
return typeof S!=='undefined'&&(S._bootReady||(S.session&&S.session.session_id));
```

处理结果：测试已改为检查 `_bootProgressReady()` 存在并包含 `S._bootReady`，不再绑定精确 JS 表达式；同时新增了 `/chatbot` 缺失 `record_id` 的阻断态断言。

### P2：旧 EID 身份/授权规格仍残留，和 record-only 实现冲突（已修复）

当前 README/CHANGELOG/实现明确说明 record-only 模式没有 EID login、身份、tenant、delegation token、远端授权 endpoint；`record_id` 不是访问凭证。

原先新增/残留文档中仍有旧语义，例如：

- `TESTING.md` 当时仍有旧 trusted-proxy 测试计划
- `specs/006-eid-auth-hermes-business-context/README.md`、`specs/007-eid-production-multi-user-deployment/README.md` 当时仍像当前方案一样描述 `api/eid_context.py`、用户 A/B 隔离、远端 record authorization
- `api/eid_context.py` 已在工作区里被删除，但旧 specs 当时仍未醒目标废弃

处理结果：`specs/006-*`、`specs/007-*` 已在索引和正文顶部标记为 superseded / 历史方案，明确不得作为当前实现、测试或部署依据；`specs/008-*` 补充了 `/chatbot` 无 `record_id` 阻断态和 record-only 测试项；`specs/010-*` 收敛为只发送 `X-EID-Record-Id`，旧身份/委托头不得发送；`TESTING.md` 的自动聚焦命令加入 `tests/test_chatbot_startup_loading.py`。

### P2：生成产物和临时目录需要清理或忽略

未跟踪文件中包含：

- `.tmp-pytest/`
- `Skills/ship-lighting.zip`
- `hermes-webui-eid.tar`（约 882 MB）

这些不应进入普通源码 PR。建议删除本地生成产物，并在 `.gitignore` / `.dockerignore` 中补上必要规则。

### P2：`git diff --check origin/master` 失败

检查结果显示：

- `Skills/ship-lighting/SKILL.md` 有 trailing whitespace
- `Skills/ship-lighting/scripts/api_client.py` 有 trailing whitespace
- `static/chatbot.html` 大量行被报告 trailing whitespace

`static/chatbot.html` 当前是 CRLF 行尾；是否要统一行尾取决于仓库策略，但至少 `diff --check` 当前是红的。建议在提交前清理空白和行尾。

## 4. 验证结果

已执行：

```bash
python -m py_compile api/eid_record_context.py api/gateway_chat.py api/routes.py api/streaming.py Skills/ship-lighting/scripts/api_client.py Skills/ship-lighting/scripts/tool_dispatcher.py Skills/ship-lighting/scripts/param_validator.py
```

结果：通过。

已执行：

```bash
python -m pytest -q tests/test_sprint19.py::test_security_headers_on_json tests/test_sprint19.py::test_security_headers_on_health -q
```

结果：1 失败、1 通过。失败原因是 5173/5174 默认 origin 不一致。

已执行：

```bash
python -m pytest -q tests/test_chatbot_startup_loading.py -q
```

结果：1 失败、1 通过。失败原因是测试精确字符串与当前 `_bootProgressReady()` 实现不一致。

已执行：

```bash
python -m pytest -q tests/test_iframe_embedding_headers.py tests/test_eid_business_context.py tests/test_webui_gateway_chat_backend.py -q
```

结果：测试夹具在本机 20 秒内未能启动隔离 test server，导致整组 setup error；不能据此判断这些用例本身通过或失败。另用临时 state 前台启动 `server.py`，5 秒后进程仍在运行，说明不是简单语法崩溃。

已执行：

```bash
git diff --check origin/master
```

结果：失败，存在 trailing whitespace / 行尾问题。

## 5. 建议处理顺序

1. 修复 `api/helpers.py` 的默认 embed origin：5173 -> 5174，并重跑 security header 测试。
2. `/chatbot` 无 `record_id` 的产品语义已明确为禁止聊天；继续补浏览器验证。
3. 将必要未跟踪源码纳入提交，尤其是 `api/eid_record_context.py` 和新增测试；清理 `.tmp-pytest/`、`.tar`、`.zip` 产物。
4. 统一 record-only 文档：更新或废弃仍描述身份/授权模式的 specs 和 TESTING 条目。
5. `test_chatbot_startup_loading.py` 的脆弱字符串断言已修复。
6. 清理 trailing whitespace / 行尾问题。
7. 再跑聚焦测试：EID、Gateway、iframe headers、chatbot startup、CSRF。
8. 最后按风险补一次浏览器验证：桌面普通 WebUI、窄 iframe `/chatbot?record_id=...`、`/chatbot` 无 record、Gateway approval 卡片。
