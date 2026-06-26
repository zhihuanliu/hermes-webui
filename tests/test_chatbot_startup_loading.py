from pathlib import Path
import json
from urllib.parse import urlparse


CHATBOT_HTML = Path("static/chatbot.html").read_text(encoding="utf-8")
EID_EMBED_JS = Path("static/eid_embed.js").read_text(encoding="utf-8")
BOOT_JS = Path("static/boot.js").read_text(encoding="utf-8")
SESSIONS_JS = Path("static/sessions.js").read_text(encoding="utf-8")
MESSAGES_JS = Path("static/messages.js").read_text(encoding="utf-8")


def test_chatbot_empty_state_starts_with_loading_indicator():
    assert 'id="emptyState" aria-busy="true"' in CHATBOT_HTML
    assert "chatbot-startup-loading" in CHATBOT_HTML
    assert "chatbot-startup-spinner" in CHATBOT_HTML
    assert 'role="status" aria-live="polite"' in CHATBOT_HTML


def test_chatbot_forces_chinese_embed_locale():
    assert "locale:'zh'" in CHATBOT_HTML
    assert "botDisplayName:'助手'" in CHATBOT_HTML
    assert 'lang="zh-CN"' in CHATBOT_HTML
    assert "function _clearStartupLoading()" in CHATBOT_HTML
    assert "empty.classList.remove('chatbot-startup-loading')" in CHATBOT_HTML
    assert "empty.removeAttribute('aria-busy')" in CHATBOT_HTML
    assert "function _bootProgressReady()" in CHATBOT_HTML
    assert "S._bootReady" in CHATBOT_HTML


def test_chatbot_requires_record_id_before_boot_session_requests():
    assert "missingRecordId:!raw" in CHATBOT_HTML
    assert "recordRequired:true" in CHATBOT_HTML
    assert "id=\"chatbotRecordRequiredNotice\"" in CHATBOT_HTML
    assert "id=\"chatbotRecordRequiredError\"" in CHATBOT_HTML
    assert "function(reason)" in CHATBOT_HTML
    assert "缺少 record_id" in CHATBOT_HTML
    assert "错误描述：URL 中没有提供 record_id" in CHATBOT_HTML
    assert "body.chatbot-record-blocked .empty-state > h2" in CHATBOT_HTML
    assert "body.chatbot-record-blocked .composer-status" in CHATBOT_HTML

    guard = "if(invalidEidRecordId||missingChatbotRecord)"
    first_guard = BOOT_JS.index(guard)
    first_boot_session_list = BOOT_JS.index("// Start independent boot fetches")
    assert first_guard < first_boot_session_list

    assert "window.__HERMES_CHATBOT_CONTEXT__.recordBlocked" in SESSIONS_JS
    assert "window.__HERMES_CHATBOT_CONTEXT__.recordBlocked" in MESSAGES_JS


def test_chatbot_includes_eid_turn_complete_postmessage_bridge():
    assert "static/eid_embed.js" in CHATBOT_HTML
    assert "parentPostMessageOrigin:__EMBED_ALLOWED_ORIGIN_JSON__" in CHATBOT_HTML
    assert "turnNotifyEnabled:__EID_TURN_NOTIFY_ENABLED__" in CHATBOT_HTML
    eid_before_messages = CHATBOT_HTML.index("static/eid_embed.js") < CHATBOT_HTML.index("static/messages.js")
    assert eid_before_messages

    assert "function notifyEidParentTurnCompleted" in EID_EMBED_JS
    assert "hermes.chat.turn.completed" in EID_EMBED_JS
    assert "window.parent.postMessage" in EID_EMBED_JS
    assert "Hermes EID bridge" in EID_EMBED_JS
    assert "post turn-completed message to parent" in EID_EMBED_JS
    assert "canvas_updated" in EID_EMBED_JS
    assert "refresh_targets" in EID_EMBED_JS

    assert "notifyEidParentTurnCompleted" in MESSAGES_JS
    assert "assistant turn done; requesting parent canvas refresh" in MESSAGES_JS
    assert "completedAt:Date.now()/1000" in MESSAGES_JS
    assert "canvasUpdated:true" in MESSAGES_JS


class _FakeHandler:
    def __init__(self):
        self.status = None
        self.sent_headers = []
        self.body = bytearray()
        self.wfile = self
        self.headers = {}

    def send_response(self, status):
        self.status = status

    def send_header(self, name, value):
        self.sent_headers.append((name, value))

    def end_headers(self):
        pass

    def write(self, data):
        self.body.extend(data)


def test_chatbot_route_injects_embed_origin_and_turn_notify_flag(monkeypatch):
    from api import routes
    from api.helpers import EMBED_ALLOWED_ORIGIN

    monkeypatch.setenv("HERMES_WEBUI_EID_RECORD_CONTEXT", "1")
    handler = _FakeHandler()
    routes.handle_get(handler, urlparse("http://example.com/chatbot"))
    assert handler.status == 200

    body = bytes(handler.body).decode("utf-8")
    assert json.dumps(EMBED_ALLOWED_ORIGIN) in body
    assert "turnNotifyEnabled:true" in body
    assert "__EMBED_ALLOWED_ORIGIN_JSON__" not in body
    assert "__EID_TURN_NOTIFY_ENABLED__" not in body


def test_chatbot_route_disables_turn_notify_without_eid_record_context(monkeypatch):
    from api import routes

    monkeypatch.delenv("HERMES_WEBUI_EID_RECORD_CONTEXT", raising=False)
    handler = _FakeHandler()
    routes.handle_get(handler, urlparse("http://example.com/chatbot"))
    assert handler.status == 200

    body = bytes(handler.body).decode("utf-8")
    assert "turnNotifyEnabled:false" in body
