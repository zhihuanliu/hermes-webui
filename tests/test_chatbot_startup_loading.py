from pathlib import Path


CHATBOT_HTML = Path("static/chatbot.html").read_text(encoding="utf-8")
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
