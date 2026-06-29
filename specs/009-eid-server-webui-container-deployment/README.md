---
status: planned
created: '2026-06-16'
tags: [eid, hermes, docker, deployment, gateway, record]
priority: high
---

# EID 服务器部署 Hermes WebUI 独立容器

> **Status**: planned · **Priority**: high · **Created**: 2026-06-16

## Overview

本规格说明在 EID 已部署到服务器 `192.168.208.23:8080`、Hermes Agent
Gateway 已部署到 `192.168.208.23:8642` 的情况下，如何把 Hermes WebUI
部署为独立 Docker 容器，并让 EID 页面按 `record_id` 正确嵌入聊天窗口。

当前需求延续 008 的 record-only 方案：

- EID 不提供用户登录给 Hermes。
- EID 页面只把当前 `record_id` 传给 Hermes WebUI。
- Hermes WebUI 按 `record_id` 创建、恢复和过滤会话。
- Hermes WebUI 通过 Gateway 调用已运行的 Hermes Agent。
- Gateway API key 作为部署 secret 注入，不写入仓库。

参考地址：

```text
EID 页面:
  http://192.168.208.23:8080/?record_id=b9dea1d362fc4956a1274d0457ff12a3

Hermes Agent Gateway:
  http://192.168.208.23:8642

Hermes WebUI 独立容器:
  http://192.168.208.23:8787
```

## Design

### 推荐拓扑

```text
浏览器
  -> http://192.168.208.23:8080/?record_id=<record_id>
       EID 页面读取 record_id
       iframe 指向:
       http://192.168.208.23:8787/chatbot?record_id=<record_id>

Hermes WebUI 容器 :8787
  -> HERMES_WEBUI_EID_RECORD_CONTEXT=1
  -> HERMES_WEBUI_CHAT_BACKEND=gateway
  -> http://192.168.208.23:8642/v1/chat/completions

Hermes Agent Gateway :8642
  -> 校验 API_SERVER_KEY
  -> 执行 Agent / Skill
```

### EID 页面 iframe 集成

EID 当前页面 URL：

```text
http://192.168.208.23:8080/?record_id=b9dea1d362fc4956a1274d0457ff12a3
```

EID 前端需要从当前 URL 或画布状态读取 `record_id`，然后拼出 Hermes WebUI
iframe。这里必须区分开发环境和生产环境，不要在代码中写死
`http://192.168.208.23:8787`。

推荐约定：

| 环境 | EID 页面地址 | iframe base URL | 说明 |
| --- | --- | --- | --- |
| 本地开发 | `http://localhost:5174/?record_id=...` | `/assistant/chatbot` | Vite 将 `/assistant` 代理到 `VITE_HERMES_ORIGIN` |
| 服务器生产，推荐 | `http://192.168.208.23:8080/?record_id=...` | `/assistant/chatbot` | EID nginx/网关把 `/assistant/` 反代到 WebUI 容器 |
| 服务器直连调试 | `http://192.168.208.23:8080/?record_id=...` | `http://192.168.208.23:8787/chatbot` | 浏览器直接访问 WebUI 端口，较容易先跑通 |

### EID 环境变量

eid-web 已有 `VITE_FLOATING_ROBOT_IFRAME_URL` 和 `VITE_HERMES_ORIGIN` 约定。
建议这样配置：

本地开发 `.env.development`：

```env
# EID 前端 iframe 使用同源路径，避免跨端口 iframe 调试问题
VITE_FLOATING_ROBOT_IFRAME_URL=/assistant/chatbot

# Vite dev server 将 /assistant/* 代理到本机 WebUI
VITE_HERMES_ORIGIN=http://localhost:8787
```

服务器生产，推荐反代方案 `docker/.env.production`：

```env
# 浏览器只访问 EID :8080，由 nginx/网关反代 /assistant 到 WebUI :8787
VITE_FLOATING_ROBOT_IFRAME_URL=/assistant/chatbot
```

服务器快速直连调试：

```env
# 不经过 EID 反代，浏览器直接访问 WebUI 容器端口
VITE_FLOATING_ROBOT_IFRAME_URL=http://192.168.208.23:8787/chatbot
```

### iframe 拼接函数

EID 前端不要自己判断 `localhost` 或服务器 IP，优先读取构建时环境变量：

```html
<iframe
  id="hermes-assistant"
  src=""
  style="width: 100%; height: 100%; border: 0;"
  allow="clipboard-read; clipboard-write; microphone"
></iframe>

<script>
  function normalizeAssistantBaseUrl(raw) {
    const value = (raw || "/assistant/chatbot").trim();
    return value || "/assistant/chatbot";
  }

  function buildAssistantUrl(recordId) {
    const base = normalizeAssistantBaseUrl(
      // Vite 项目中实际写法是 import.meta.env.VITE_FLOATING_ROBOT_IFRAME_URL
      window.__EID_FLOATING_ROBOT_IFRAME_URL__
    );

    const url = new URL(base, window.location.origin);
    url.searchParams.set("record_id", recordId);
    return url.href;
  }

  const params = new URLSearchParams(window.location.search);
  const recordId = params.get("record_id") || "";
  const assistant = document.getElementById("hermes-assistant");

  if (recordId && assistant) {
    assistant.src = buildAssistantUrl(recordId);
  }
</script>
```

在 eid-web 的 Vite/React 代码中，对应写法应类似：

```ts
const DEFAULT_ASSISTANT_IFRAME_URL = '/assistant/chatbot'

export function buildHermesAssistantUrl(recordId: string): string {
  const normalizedRecordId = recordId.trim()
  if (!normalizedRecordId) return ''

  const base =
    import.meta.env.VITE_FLOATING_ROBOT_IFRAME_URL?.trim() ||
    DEFAULT_ASSISTANT_IFRAME_URL

  const url = new URL(base, window.location.origin)
  url.searchParams.set('record_id', normalizedRecordId)
  return url.href
}
```

Hermes WebUI 会在 `chatbot.html` 启动时读取 `record_id`，调用
`/api/session/resolve`，恢复或创建该 record 对应的会话。

### 开发环境 Vite 代理

本地开发时，EID 页面通常运行在 `http://localhost:5174`，Hermes WebUI 运行在
`http://localhost:8787`。eid-web 的 Vite 配置已经支持把 `/assistant` 代理到
`VITE_HERMES_ORIGIN`。因此开发环境 iframe 仍写同源路径：

```text
/assistant/chatbot?record_id=<record_id>
```

浏览器实际请求：

```text
http://localhost:5174/assistant/chatbot?record_id=<record_id>
```

Vite 转发到：

```text
http://localhost:8787/chatbot?record_id=<record_id>
```

### WebUI 容器配置

因为当前 record-only 逻辑还在本仓库代码中，部署时应先用本仓库构建镜像，而不是
直接使用还未包含该改动的远端 `latest` 镜像。

建议新增一个部署专用 compose 文件，例如：

```yaml
# docker-compose.eid-webui.yml
services:
  hermes-webui:
    build: .
    container_name: hermes-webui-eid
    ports:
      - "8787:8787"
    volumes:
      - hermes-webui-home:/home/hermeswebui/.hermes
      - ${HERMES_WORKSPACE:-./workspace}:/workspace
    environment:
      - HERMES_WEBUI_HOST=0.0.0.0
      - HERMES_WEBUI_PORT=8787
      - HERMES_WEBUI_STATE_DIR=/home/hermeswebui/.hermes/webui

      # EID record-only integration
      - HERMES_WEBUI_EID_RECORD_CONTEXT=1
      - HERMES_WEBUI_EMBED_ALLOWED_ORIGIN=http://192.168.208.23:8080

      # Remote Hermes Agent Gateway
      - HERMES_WEBUI_CHAT_BACKEND=gateway
      - HERMES_WEBUI_GATEWAY_BASE_URL=http://192.168.208.23:8642
      - HERMES_WEBUI_GATEWAY_API_KEY=${HERMES_WEBUI_GATEWAY_API_KEY}

      # 当前方案依赖 EID 页面入口控制；如果要公网暴露 WebUI，必须另行加认证或反代保护。
      - HERMES_WEBUI_PASSWORD=
    restart: unless-stopped

volumes:
  hermes-webui-home:
```

对应 `.env` 文件放在部署目录，**不要提交到 git**：

```env
HERMES_WEBUI_GATEWAY_API_KEY=<与 Hermes Agent API_SERVER_KEY 一致>
HERMES_WORKSPACE=/opt/hermes-workspace
```

> 注意：用户已经在对话中贴出过 `API_SERVER_KEY`。生产环境建议轮换该 key，
> 然后只把新值写入服务器 `.env` 或容器 secret，不要写入规格、README 或镜像。

启动：

```bash
docker compose -f docker-compose.eid-webui.yml up -d --build
```

### WebUI 到 Gateway 的连通性

WebUI 容器内访问 Gateway 使用：

```text
HERMES_WEBUI_GATEWAY_BASE_URL=http://192.168.208.23:8642
```

前提：

- Gateway 必须监听 `0.0.0.0:8642` 或至少监听服务器内网 IP。
- 如果 Gateway 只绑定 `127.0.0.1:8642`，Docker bridge 容器无法通过
  `192.168.208.23:8642` 访问它。
- 服务器防火墙需要允许 WebUI 容器访问 `8642`。

验证：

```bash
curl -sS http://192.168.208.23:8642/health/detailed
curl -sS \
  -H "Authorization: Bearer <GATEWAY_API_KEY>" \
  http://192.168.208.23:8642/health
```

验证 WebUI 容器内连通性：

```bash
docker exec hermes-webui-eid sh -lc \
  'curl -sS http://192.168.208.23:8642/health/detailed | head -50'
```

### WebUI 被 EID iframe 嵌入

WebUI 必须允许 `http://192.168.208.23:8080` 作为 iframe 父页面：

```env
HERMES_WEBUI_EMBED_ALLOWED_ORIGIN=http://192.168.208.23:8080
```

如果该值不匹配，浏览器会因为 CSP `frame-ancestors` 拒绝嵌入，EID 页面中会看到
iframe 空白或控制台报错。

验证响应头：

```bash
curl -I http://192.168.208.23:8787/chatbot
```

期望看到类似：

```text
Content-Security-Policy: frame-ancestors 'self' http://192.168.208.23:8080
```

### record_id 流转

以样例 record 为例：

```text
b9dea1d362fc4956a1274d0457ff12a3
```

完整流转：

```text
EID URL
  /?record_id=b9dea1d362fc4956a1274d0457ff12a3

EID iframe
  /chatbot?record_id=b9dea1d362fc4956a1274d0457ff12a3

Hermes WebUI
  POST /api/session/resolve
  { "record_id": "b9dea1d362fc4956a1274d0457ff12a3" }

Hermes Gateway request
  X-EID-Record-Id: b9dea1d362fc4956a1274d0457ff12a3

Agent / ship-lighting runtime
  HERMES_EID_RECORD_ID=b9dea1d362fc4956a1274d0457ff12a3
```

## Optional: 同源反向代理方案

如果不希望浏览器直接访问 `:8787`，可以让 EID 的 nginx 或网关把
`/assistant/` 反代到 WebUI：

```nginx
location /assistant/ {
    proxy_pass http://127.0.0.1:8787/;
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_set_header X-Forwarded-Host $host;
    proxy_set_header X-Forwarded-Prefix /assistant;
}
```

此时生产环境不需要在前端代码里写完整 IP，只需要设置：

```env
VITE_FLOATING_ROBOT_IFRAME_URL=/assistant/chatbot
```

最终 iframe 地址会由 `buildHermesAssistantUrl(recordId)` 拼为：

```text
http://192.168.208.23:8080/assistant/chatbot?record_id=<record_id>
```

同源方案的好处是浏览器只看到 `:8080`，部署边界更清晰；直接端口方案
`VITE_FLOATING_ROBOT_IFRAME_URL=http://192.168.208.23:8787/chatbot` 更容易先跑通。

## Plan

- [ ] 在服务器上拉取包含 008 record-only 改动的 Hermes WebUI 代码。
- [ ] 创建 `.env`，写入 `HERMES_WEBUI_GATEWAY_API_KEY`，不要提交。
- [ ] 创建 `docker-compose.eid-webui.yml`。
- [ ] `docker compose -f docker-compose.eid-webui.yml up -d --build`。
- [ ] 验证 `http://192.168.208.23:8787/health`。
- [ ] 验证 WebUI 容器能访问 `http://192.168.208.23:8642/health/detailed`。
- [ ] EID 页面把 `record_id` 拼到 WebUI iframe。
- [ ] 浏览器打开 EID 样例 URL，确认 iframe 正常加载。
- [ ] 确认 record A/B 的会话列表互不混合。
- [ ] 确认一次聊天请求能通过 Gateway 返回响应。
- [ ] 确认 ship-lighting 或诊断工具收到相同 `record_id`。

## Test

### 1. WebUI 服务健康

```bash
curl -i http://192.168.208.23:8787/health
```

期望：`HTTP 200`。

### 2. Gateway 配置健康

```bash
curl -i http://192.168.208.23:8787/api/health/agent
```

期望：响应中能看到 Gateway 已启用，且 base URL 指向 `192.168.208.23:8642`。

### 3. iframe 嵌入

打开：

```text
http://192.168.208.23:8080/?record_id=b9dea1d362fc4956a1274d0457ff12a3
```

期望：

- 页面中出现 Hermes 聊天 iframe。
- 浏览器控制台没有 `frame-ancestors` / CSP 拒绝。
- WebUI 网络请求包含 `record_id=b9dea1d362fc4956a1274d0457ff12a3`。

### 4. record 会话隔离

分别打开：

```text
http://192.168.208.23:8080/?record_id=record-a
http://192.168.208.23:8080/?record_id=record-b
```

期望：

- record A 与 record B 各自创建或恢复自己的会话。
- A 的会话列表不显示 B 的会话。
- B 的会话列表不显示 A 的会话。

### 5. Gateway 聊天

在 iframe 中发送一句：

```text
ping
```

期望：

- WebUI 不报 `gateway_auth_error`。
- Agent 有响应。
- 如果触发 ship-lighting，工具侧使用当前 iframe record。

## Notes

- 当前方案不做用户级安全隔离。知道或构造 `record_id` 的调用方可以进入该 record
  分区。这个限制来自 008 的 record-only 需求。
- 如果未来 EID 要区分用户、权限或私有 record，需要新增身份认证与 record 授权方案。
- `HERMES_WEBUI_GATEWAY_API_KEY` 必须与 Agent 的 `API_SERVER_KEY` 一致，但真实值不得
  写入仓库。
- 生产上建议不要长期暴露 `:8787` 到公网；优先放在内网，或使用 EID/nginx 反代。
