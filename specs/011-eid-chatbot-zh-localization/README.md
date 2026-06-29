---
status: complete
created: '2026-06-16'
tags: [eid, chatbot, i18n, iframe, ux]
priority: medium
---

# EID 嵌入 Chatbot 简体中文本地化

> **Status**: complete · **Priority**: medium · **Created**: 2026-06-16

## Overview

EID 通过 iframe 嵌入 Hermes WebUI 的 `/chatbot?record_id=<id>` 页面。生产入口
为 eid-web 同站点反代 `/assistant/chatbot`，开发环境可直接访问 WebUI 的
`/chatbot`。

嵌入页面向最终用户展示，但原先存在汉化不彻底的问题：

- 服务端 `language` 默认为 `en`，覆盖浏览器 locale，大量 `data-i18n` 文案仍为英文
- 消息时间戳使用浏览器 12 小时制（如 `02:51 PM`）
- 助手名显示为 `Hermes` 而非业务侧期望的「助手」
- 部分 HTML 静态文案、`sessions.js` / `panels.js` 动态注入字符串无 i18n 键
- 启动阶段在 WSL/慢存储上 boot 耗时较长时，空状态长期停留在「加载中…」

本规格记录 **仅作用于 chatbot 嵌入页** 的汉化与启动体验修复，不改动主站
`index.html` 的全局语言策略。

```text
eid-web iframe
  -> /assistant/chatbot?record_id=R
  -> static/chatbot.html
       -> __HERMES_CHATBOT_CONTEXT__ { locale, botDisplayName, recordId }
       -> boot.js（嵌入页优先 locale / 助手名）
       -> i18n.js zh 补键 + 运行时补丁
```

## User Requirements

### UR-01：嵌入页默认简体中文

- chatbot 页打开后 UI 文案以简体中文为主，不依赖 Settings 中 `language: en`。
- 覆盖范围：空状态、侧栏、输入框、按钮 tooltip、排队/拖放提示、消息操作按钮等。
- 主站 `index.html` 行为不变。

### UR-02：助手展示名

- 嵌入页助手角色名显示为「助手」，而非配置中的 `bot_name`（默认 Hermes）。
- 仅 chatbot 视图生效；其他 profile/主站仍按原有 `bot_name` 规则。

### UR-03：时间与格式

- 消息 footer 时间使用 `zh-CN` locale。
- 当天消息使用 24 小时制（如 `14:51`），避免 `PM` 英文后缀。

### UR-04：启动 loading 不无限阻塞

- 首次进入显示「加载中…」startup spinner。
- boot 完成（`S._bootReady` 或 `S.session` 就绪）后移除 spinner。
- 慢环境（如 Windows WebUI + WSL UNC 状态目录）下，**最多 12 秒**强制结束
  startup loading，避免用户误以为页面卡死。

### UR-05：改动范围隔离

- 逻辑通过 `__HERMES_CHATBOT_CONTEXT__` 与 `body.chatbot-view` 限定在
  `chatbot.html` 嵌入场景。
- 不新增 npm 依赖、不修改主站布局。

## Design

### 嵌入上下文扩展

`static/chatbot.html` 在解析 `record_id` 时同步注入：

```javascript
window.__HERMES_CHATBOT_CONTEXT__ = {
  recordId: '...',
  invalidRecordId: null,
  locale: 'zh',
  botDisplayName: '助手',
};
localStorage.setItem('hermes-lang', 'zh');
```

`<html lang="zh-CN">` 与上述 context 在 i18n 加载前生效，减少英文闪屏。

### boot.js 嵌入页优先规则

当 `__HERMES_CHATBOT_CONTEXT__.locale` 存在时：

1. `setLocale(forced)` 优先于 `resolvePreferredLocale(serverLanguage, localStorage)`
2. `botDisplayName` 覆盖 `window._botName`

主站 boot 路径不受影响（无 context 时不走强制分支）。

### chatbot.html 运行时补丁

页面底部脚本（boot 完成后执行）负责 i18n 系统未覆盖的字符串：

| 补丁 | 说明 |
|------|------|
| `_applyChatbotLocale()` | 再次 `setLocale('zh')` + `applyLocaleToDOM()` |
| `_patchDateFormatting()` | 包装 `_formatMessageFooterTimestamp` 为 `zh-CN` |
| `_patchUnassigned()` | `Unassigned` 项目 chip →「未分配」 |
| `_patchLoadingText()` | `Loading conversation...` →「正在加载…」 |
| `_patchDropHint()` | 拖放提示英中映射 |
| `_clearStartupLoading()` | 移除 `chatbot-startup-loading` / `aria-busy` |

Startup 结束条件：

```javascript
S._bootReady || (S.session && S.session.session_id)
```

兜底：`setTimeout(..., 12000)` 无条件清除 startup spinner。

### i18n 补键

`static/i18n.js` 简体中文 locale 增加：

```javascript
undo_exchange: '撤销上一条问答',
```

修复撤销按钮 tooltip 回退英文的问题。

### 静态 HTML 汉化

直接在 `chatbot.html` 写入中文或 `data-i18n-*` 的属性，包括但不限于：

- 会话筛选 placeholder / 清除按钮
- 排队区域 `aria-label`
- 发送按钮 `data-i18n-title="composer_send"`
- 拖放、麦克风状态默认文案

## Changed Files

| 文件 | 变更摘要 |
|------|----------|
| `static/chatbot.html` | lang、context、静态汉化、startup loader CSS、运行时补丁 |
| `static/boot.js` | 嵌入页强制 locale 与 botDisplayName |
| `static/i18n.js` | `zh.undo_exchange` |
| `tests/test_chatbot_startup_loading.py` | startup loading 与 locale context 断言 |

**未修改**：`index.html`、`api/routes.py`（chatbot 路由本身已存在）。

## Plan

- [x] 扩展 `__HERMES_CHATBOT_CONTEXT__`（locale、botDisplayName）
- [x] boot.js 嵌入页 locale / 助手名优先
- [x] chatbot.html 静态文案与 `data-i18n` 属性
- [x] 运行时补丁（时间格式、Unassigned、拖放、loading 文案）
- [x] startup loading UX（spinner + 12s 兜底）
- [x] i18n `undo_exchange` 中文补键
- [x] 自动化测试更新

## Test

### 自动化

```bash
python -m pytest tests/test_chatbot_startup_loading.py -q
```

断言包含：

- `chatbot-startup-loading` / spinner / `aria-busy`
- `locale:'zh'`、`botDisplayName:'助手'`、`lang="zh-CN"`
- `_clearStartupLoading()` 存在

### 手动（嵌入页）

1. 启动 WebUI（Gateway 或 in-process 均可）：

   ```text
   http://127.0.0.1:8789/chatbot?record_id=<valid-record-id>
   ```

2. 验证：
   - [ ] 助手名显示「助手」
   - [ ] 消息时间为 24 小时制中文 locale
   - [ ] 复制/编辑/重新生成/撤销等 tooltip 为中文
   - [ ] 输入框 placeholder「输入消息…」
   - [ ] 启动后 12 秒内离开「加载中…」状态（慢存储可接受更短即完成）

3. 生产路径（eid-web iframe）：

   ```text
   /assistant/chatbot?record_id=<activeRecordId>
   ```

   强刷 iframe（Ctrl+F5）后重复上述检查。

### 本地开发注意事项（非本 spec 代码，但影响验证）

- Windows 原生 `start.ps1` + WSL `HERMES_HOME` UNC 路径会导致
  `/api/sessions` 等 API 变慢，boot 可能需 10–30 秒；属 I/O 环境 issue，
  不是汉化逻辑缺陷。
- Gateway 模式（`HERMES_WEBUI_CHAT_BACKEND=gateway`）推荐用于 Windows WebUI +
  WSL Agent 分离部署。
- 使用 `hermes-webui/.venv` 或明确指定的 Python，避免 Windows Store
  `python3.exe` 缺依赖导致 WebUI 无法监听端口。

## Notes

- 本 spec 与 [008-eid-record-scoped-hermes-integration](../008-eid-record-scoped-hermes-integration/README.md)
  互补：008 定义 record 会话模型，011 定义嵌入 chatbot 面向用户的中文 UX。
- 若未来需要多语言嵌入（不仅中文），可将 `locale` / `botDisplayName` 改为
  eid-web 通过 query 或 postMessage 传入，而非写死在 chatbot.html。
- 部署时只需同步上述静态文件并重启 WebUI；无需数据库迁移。
