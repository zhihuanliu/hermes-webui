---
status: complete
created: '2026-06-23'
tags: [eid, hermes-webui, docker, packaging, deployment]
priority: high
---

# EID Hermes WebUI 打包与部署流程

> **Status**: complete · **Priority**: high · **Created**: 2026-06-23

## Scope

本规格只负责 **hermes-webui** 这个工程的镜像打包和容器部署。

不负责：

- Hermes Agent 后端镜像的打包和部署。
- EID 前端工程的打包和部署。
- 其他后端服务的打包和部署。

部署约定：

- hermes-webui、Hermes Agent、EID 前端和其他后端服务部署在同一台 Linux 服务器上。
- 这些容器都加入同一个 Docker 网络：`eid-2-net`。
- WebUI 通过 Docker 网络服务名访问 Hermes Agent Gateway，不写死服务器 IP。

默认网络访问地址：

```env
HERMES_WEBUI_GATEWAY_BASE_URL=http://hermes-agent:8642
```

如果后端容器在 `eid-2-net` 中的名字不是 `hermes-agent`，改成真实容器名或网络 alias：

```env
HERMES_WEBUI_GATEWAY_BASE_URL=http://<backend-container-or-alias>:8642
```

## Files

| 文件 | 作用 |
|---|---|
| `scripts/windows/package_eid_webui.ps1` | Windows 打包脚本，自动执行 build、验证、save |
| `scripts/linux/deploy_eid_webui.sh` | Linux 部署脚本，自动执行 load、建网络、compose up |
| `docker-compose.eid-webui.yml` | 只启动 hermes-webui 容器 |
| `.env.eid-webui.deploy.example` | Linux 部署配置模板 |

## Windows 打包

### 原手动命令

之前手动打包执行的是：

```bash
docker build -t hermes-webui-eid:latest .

# 若存在代码没有更新
docker build --no-cache -t hermes-webui-eid:latest .

# 验证改动
docker run --rm hermes-webui-eid:latest head -50 /apptoo/static/chatbot.html

# 保存镜像
docker save hermes-webui-eid:latest -o hermes-webui-eid.tar
```

### 自动化脚本

在 Windows PowerShell 中进入仓库根目录：

```powershell
cd E:\liuzhihuan\workspace\hermes\hermes-webui
```

正常打包：

```powershell
powershell -ExecutionPolicy Bypass -File scripts\windows\package_eid_webui.ps1
```

等价于：

```bash
docker build -t hermes-webui-eid:latest .
docker run --rm hermes-webui-eid:latest head -50 /apptoo/static/chatbot.html
docker save hermes-webui-eid:latest -o release\hermes-webui-eid\hermes-webui-eid.tar
```

强制无缓存打包：

```powershell
powershell -ExecutionPolicy Bypass -File scripts\windows\package_eid_webui.ps1 -NoCache
```

等价于：

```bash
docker build --no-cache -t hermes-webui-eid:latest .
docker run --rm hermes-webui-eid:latest head -50 /apptoo/static/chatbot.html
docker save hermes-webui-eid:latest -o release\hermes-webui-eid\hermes-webui-eid.tar
```

指定镜像名或 tar 输出路径：

```powershell
powershell -ExecutionPolicy Bypass -File scripts\windows\package_eid_webui.ps1 `
  -Image hermes-webui-eid:latest `
  -OutputDir E:\deploy\hermes-webui-eid
```

跳过 `chatbot.html` 验证：

```powershell
powershell -ExecutionPolicy Bypass -File scripts\windows\package_eid_webui.ps1 -SkipVerify
```

### 打包产物

默认输出部署目录：

```text
release/
  hermes-webui-eid/
    hermes-webui-eid.tar
    docker-compose.yml
    deploy.sh
    deploy.env
    deploy.env.example
```

把整个目录复制到 Linux 部署机即可：

```powershell
scp -r .\release\hermes-webui-eid root@<server-ip>:/opt/hermes-webui-eid
```

## Linux 部署

### 1. 准备部署目录

示例：

```bash
mkdir -p /opt/hermes-webui-eid
cd /opt/hermes-webui-eid
```

把 Windows 打包出的文件放到该目录，最终目录类似：

```text
/opt/hermes-webui-eid/
  hermes-webui-eid.tar
  docker-compose.yml
  deploy.sh
  deploy.env
  deploy.env.example
```

### 2. 准备配置文件

```bash
vi deploy.env
```

关键配置：

```env
HERMES_WEBUI_IMAGE=hermes-webui-eid:latest
HERMES_WEBUI_CONTAINER_NAME=hermes-webui-eid
EID_DOCKER_NETWORK=eid-2-net

HERMES_WEBUI_HOST_BIND=127.0.0.1
HERMES_WEBUI_HOST_PORT=8787

HERMES_WEBUI_EMBED_ALLOWED_ORIGIN=http://<server-ip>:8080

HERMES_WEBUI_CHAT_BACKEND=gateway
HERMES_WEBUI_GATEWAY_BASE_URL=http://hermes-agent:8642
HERMES_WEBUI_GATEWAY_API_KEY=<same value as Hermes Agent API_SERVER_KEY>
HERMES_WEBUI_GATEWAY_TRANSPORT=runs

HERMES_WEBUI_EID_RECORD_CONTEXT=1
```

说明：

- `HERMES_WEBUI_GATEWAY_BASE_URL` 使用容器网络地址，不写服务器 IP。
- 如果 Hermes Agent 容器名或网络 alias 是 `hermes-agent`，默认值可直接使用。
- `HERMES_WEBUI_EMBED_ALLOWED_ORIGIN` 是浏览器安全头 `frame-ancestors` 使用的父页面 origin，必须写浏览器实际看到的 EID origin，不能写 Docker 容器名。
- 如果 EID 前端通过浏览器访问的 origin 是 `http://服务器IP:8080`，则配置为：

```env
HERMES_WEBUI_EMBED_ALLOWED_ORIGIN=http://服务器IP:8080
```

- 如果 EID 通过 nginx 同源反代 WebUI，WebUI 端口可以保持只绑定本机：

```env
HERMES_WEBUI_HOST_BIND=127.0.0.1
```

### 3. 确认后端容器网络

如果后端容器还没有加入 `eid-2-net`：

```bash
docker network inspect eid-2-net >/dev/null 2>&1 || docker network create eid-2-net
docker network connect --alias hermes-agent eid-2-net <hermes-agent-container-name>
```

如果 EID 前端容器也需要访问 WebUI，也应加入同一个网络：

```bash
docker network connect eid-2-net <eid-web-container-name>
```

### 4. 执行部署脚本

```bash
bash deploy.sh
```

脚本等价于做这些事：

```bash
docker network inspect eid-2-net >/dev/null 2>&1 || docker network create eid-2-net
docker load -i hermes-webui-eid.tar
docker compose --env-file deploy.env -f docker-compose.yml up -d --remove-orphans
curl -fsS http://127.0.0.1:8787/health
```

指定 tar 路径：

```bash
bash deploy.sh --image-tar /tmp/hermes-webui-eid.tar
```

指定网络名：

```bash
bash deploy.sh --network eid-2-net
```

如果镜像已经手动 `docker load` 过：

```bash
bash deploy.sh --no-load
```

## docker-compose.eid-webui.yml

该 compose 文件只定义一个服务：

```yaml
services:
  hermes-webui:
    image: ${HERMES_WEBUI_IMAGE:-hermes-webui-eid:latest}
    container_name: ${HERMES_WEBUI_CONTAINER_NAME:-hermes-webui-eid}
    networks:
      - eid-2-net
```

关键环境变量：

```yaml
HERMES_WEBUI_GATEWAY_BASE_URL=${HERMES_WEBUI_GATEWAY_BASE_URL:-http://hermes-agent:8642}
HERMES_WEBUI_EMBED_ALLOWED_ORIGIN=${HERMES_WEBUI_EMBED_ALLOWED_ORIGIN:-http://localhost:8080}
```

这里的 `http://hermes-agent:8642` 是 Docker 网络里的服务名，不是服务器 IP。

## 验证

### 1. 容器状态

```bash
docker ps | grep hermes-webui-eid
docker logs --tail 100 hermes-webui-eid
```

### 2. WebUI health

```bash
curl -i http://127.0.0.1:8787/health
```

期望返回 `HTTP 200`。

### 3. 容器内访问 Hermes Agent Gateway

```bash
docker exec hermes-webui-eid sh -lc \
  'curl -sS "${HERMES_WEBUI_GATEWAY_BASE_URL%/}/health/detailed" | head -80'
```

如果后端开启 API key：

```bash
docker exec hermes-webui-eid sh -lc \
  'curl -sS -H "Authorization: Bearer $HERMES_WEBUI_GATEWAY_API_KEY" "${HERMES_WEBUI_GATEWAY_BASE_URL%/}/health" | head -80'
```

### 4. iframe 允许嵌入

```bash
curl -I http://127.0.0.1:8787/chatbot
```

检查响应头中 `Content-Security-Policy` 的 `frame-ancestors` 是否包含 EID 前端实际 origin。

### 5. EID 页面联调

浏览器打开：

```text
http://<eid-host>:<eid-port>/?record_id=<record_id>
```

期望：

- EID 页面 iframe 加载 `/chatbot?record_id=<record_id>`。
- WebUI 不提示 record 缺失。
- 发送消息后，WebUI 通过 Hermes Agent Gateway 返回响应。
- record A 和 record B 的会话互不混淆。

## 常见问题

### WebUI 访问不到后端

先检查网络：

```bash
docker network inspect eid-2-net
```

再检查后端名字能否解析：

```bash
docker exec hermes-webui-eid sh -lc 'getent hosts hermes-agent || true'
```

如果解析不到，给后端容器加 alias：

```bash
docker network connect --alias hermes-agent eid-2-net <hermes-agent-container-name>
```

或者改 `deploy.env`：

```env
HERMES_WEBUI_GATEWAY_BASE_URL=http://真实后端容器名:8642
```

### iframe 被 CSP 拦截

`HERMES_WEBUI_EMBED_ALLOWED_ORIGIN` 必须写浏览器实际打开的 EID origin。

正确：

```env
HERMES_WEBUI_EMBED_ALLOWED_ORIGIN=http://10.0.0.12:8080
```

错误：

```env
HERMES_WEBUI_EMBED_ALLOWED_ORIGIN=http://10.0.0.12:8080/?record_id=abc
```

### 代码看起来没有更新

Windows 重新无缓存打包：

```powershell
powershell -ExecutionPolicy Bypass -File scripts\windows\package_eid_webui.ps1 -NoCache
```

Linux 重新上传 `hermes-webui-eid.tar` 后执行：

```bash
bash deploy.sh
docker logs --tail 100 hermes-webui-eid
```

## Acceptance Criteria

- [x] Windows 脚本自动执行 `docker build -t hermes-webui-eid:latest .`。
- [x] Windows 脚本支持 `docker build --no-cache -t hermes-webui-eid:latest .`。
- [x] Windows 脚本自动执行 `docker run --rm hermes-webui-eid:latest head -50 /apptoo/static/chatbot.html`。
- [x] Windows 脚本自动执行 `docker save hermes-webui-eid:latest -o hermes-webui-eid.tar`。
- [x] Linux 脚本只部署 hermes-webui，不部署 Hermes Agent 和 EID 前端。
- [x] WebUI 默认通过 `http://hermes-agent:8642` 访问同网络后端。
- [x] WebUI 容器加入 `eid-2-net`。

## Related Specs

- [008 EID record-scoped integration](../008-eid-record-scoped-hermes-integration/README.md)
- [009 EID server WebUI container deployment](../009-eid-server-webui-container-deployment/README.md)
- [010 EID Gateway approval bridge](../010-eid-gateway-approval-bridge/README.md)
- [012 EID turn complete postMessage](../012-eid-turn-complete-postmessage/README.md)
