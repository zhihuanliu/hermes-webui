import urllib.error
import urllib.request
from contextlib import contextmanager
from types import SimpleNamespace
from urllib.parse import urlparse

import pytest

from api.eid_context import (
    EidAuthenticationError,
    EidAuthorizationError,
    EidAuthorizationUnavailableError,
    TrustedEidContext,
    authorize_record_access,
    clear_authorize_cache,
    session_matches_record,
    session_owned_by_context,
    trusted_eid_context,
    validate_record_id,
)
from api.models import Session
from api.streaming import _build_agent_thread_env, _webui_ephemeral_system_prompt


def _handler(headers=None):
    return SimpleNamespace(headers=headers or {})


def test_record_id_validation_accepts_eid_ids_and_rejects_untrusted_shapes():
    assert validate_record_id("ad862e249e08461386f1fc86c9297719") == "ad862e249e08461386f1fc86c9297719"
    assert validate_record_id("record_A-17") == "record_A-17"
    with pytest.raises(ValueError):
        validate_record_id("../other-user")
    with pytest.raises(ValueError):
        validate_record_id("record id")


def test_development_identity_requires_explicit_subject():
    env = {
        "HERMES_WEBUI_EID_CONTEXT": "1",
        "HERMES_WEBUI_EID_DEVELOPMENT_MODE": "1",
    }
    with pytest.raises(EidAuthenticationError):
        trusted_eid_context(_handler(), env)

    env["HERMES_WEBUI_EID_DEVELOPMENT_SUBJECT"] = "developer-user"
    context = trusted_eid_context(_handler({"X-EID-Subject": "forged-user"}), env)
    assert context == TrustedEidContext(subject="developer-user")


def test_proxy_identity_ignores_url_and_uses_only_trusted_headers():
    env = {
        "HERMES_WEBUI_EID_CONTEXT": "true",
        "HERMES_WEBUI_EID_TRUST_PROXY": "true",
    }
    context = trusted_eid_context(
        _handler({
            "X-EID-Subject": "user-a",
            "X-EID-Tenant": "tenant-1",
            "X-EID-Delegation": "short-lived-token",
        }),
        env,
    )
    assert context.subject == "user-a"
    assert context.tenant == "tenant-1"
    assert context.delegation_token == "short-lived-token"


def test_production_authorization_is_fail_closed_without_endpoint():
    context = TrustedEidContext(subject="user-a")
    with pytest.raises(EidAuthorizationUnavailableError):
        authorize_record_access(context, "record-a", {"HERMES_WEBUI_EID_CONTEXT": "1"})


def _fake_urlopen(calls, status=200, error_code=None):
    @contextmanager
    def opener(request, timeout=None):
        calls.append(request)
        if error_code is not None:
            raise urllib.error.HTTPError(request.full_url, error_code, "denied", {}, None)
        yield SimpleNamespace(status=status)
    return opener


def test_authorization_caches_positive_grants_within_ttl(monkeypatch):
    clear_authorize_cache()
    env = {
        "HERMES_WEBUI_EID_CONTEXT": "1",
        "HERMES_WEBUI_EID_AUTHORIZE_URL": "http://eid.internal/authorize",
        "HERMES_WEBUI_EID_AUTHORIZE_CACHE_TTL": "30",
    }
    context = TrustedEidContext(subject="user-a", tenant="tenant-1")
    calls = []
    monkeypatch.setattr(urllib.request, "urlopen", _fake_urlopen(calls))
    authorize_record_access(context, "record-a", env)
    authorize_record_access(context, "record-a", env)
    assert len(calls) == 1, "second authorization within TTL must use the cache"

    # Different subject or record must never reuse another grant.
    authorize_record_access(TrustedEidContext(subject="user-b"), "record-a", env)
    authorize_record_access(context, "record-b", env)
    assert len(calls) == 3
    clear_authorize_cache()


def test_authorization_cache_disabled_and_denials_never_cached(monkeypatch):
    clear_authorize_cache()
    env = {
        "HERMES_WEBUI_EID_CONTEXT": "1",
        "HERMES_WEBUI_EID_AUTHORIZE_URL": "http://eid.internal/authorize",
        "HERMES_WEBUI_EID_AUTHORIZE_CACHE_TTL": "0",
    }
    context = TrustedEidContext(subject="user-a")
    calls = []
    monkeypatch.setattr(urllib.request, "urlopen", _fake_urlopen(calls))
    authorize_record_access(context, "record-a", env)
    authorize_record_access(context, "record-a", env)
    assert len(calls) == 2, "TTL=0 must disable the cache"

    denied_calls = []
    monkeypatch.setattr(urllib.request, "urlopen", _fake_urlopen(denied_calls, error_code=403))
    env["HERMES_WEBUI_EID_AUTHORIZE_CACHE_TTL"] = "30"
    for _ in range(2):
        with pytest.raises(EidAuthorizationError):
            authorize_record_access(context, "record-denied", env)
    assert len(denied_calls) == 2, "denials must always be re-checked"
    clear_authorize_cache()


def test_session_ownership_requires_subject_tenant_and_record_match():
    session = Session(
        eid_subject="user-a",
        eid_tenant="tenant-1",
        record_id="record-a",
        context_type="eid-record",
    )
    assert session_owned_by_context(session, TrustedEidContext("user-a", "tenant-1"))
    assert not session_owned_by_context(session, TrustedEidContext("user-b", "tenant-1"))
    assert not session_owned_by_context(session, TrustedEidContext("user-a", "tenant-2"))
    assert session_matches_record(session, "record-a")
    assert not session_matches_record(session, "record-b")


def test_browser_session_payloads_omit_trusted_identity_fields():
    from api.helpers import redact_session_data
    from api.routes import _public_eid_session_data

    payload = Session(
        eid_subject="user-a",
        eid_tenant="tenant-1",
        record_id="record-a",
        context_type="eid-record",
    ).compact()
    redacted = redact_session_data(payload | {"messages": []})
    assert "eid_subject" not in redacted
    assert "eid_tenant" not in redacted
    assert redacted["record_id"] == "record-a"
    public = _public_eid_session_data(payload)
    assert "eid_subject" not in public
    assert "eid_tenant" not in public


def test_session_compact_persists_eid_domain_metadata():
    compact = Session(
        eid_subject="user-a",
        eid_tenant="tenant-1",
        record_id="record-a",
        context_type="eid-record",
    ).compact()
    assert compact["eid_subject"] == "user-a"
    assert compact["eid_tenant"] == "tenant-1"
    assert compact["record_id"] == "record-a"
    assert compact["context_type"] == "eid-record"


def test_agent_context_contains_authorized_record_without_delegation_secret():
    prompt = _webui_ephemeral_system_prompt(
        None,
        surface_context={
            "source": "webui",
            "session_id": "session-a",
            "record_id": "record-a",
            "context_type": "eid-record",
        },
    )
    assert "Authorized EID record ID: record-a" in prompt
    assert "Business context type: eid-record" in prompt
    assert "delegation" not in prompt.lower()


def test_agent_thread_context_uses_eid_names_without_legacy_fixed_record():
    env = _build_agent_thread_env(
        {"SHIP_LIGHTING_RECORD_ID": "legacy-default"},
        "/workspace",
        "session-a",
        "/profile",
        "user-a",
        "record-a",
    )
    assert env["HERMES_EID_SUBJECT"] == "user-a"
    assert env["HERMES_EID_RECORD_ID"] == "record-a"
    # The caller removes the profile-level legacy value before constructing
    # EID session context; the new dynamic value uses a dedicated name.
    assert env["SHIP_LIGHTING_RECORD_ID"] == "legacy-default"
    streaming_source = open("api/streaming.py", encoding="utf-8").read()
    assert "_profile_runtime_env.pop('SHIP_LIGHTING_RECORD_ID', None)" in streaming_source


def test_chatbot_wires_record_resolution_and_scoped_session_lists():
    chatbot = open("static/chatbot.html", encoding="utf-8").read()
    sessions = open("static/sessions.js", encoding="utf-8").read()
    boot = open("static/boot.js", encoding="utf-8").read()

    assert "__HERMES_CHATBOT_CONTEXT__" in chatbot
    assert "forceNewRecord:true" in chatbot
    assert "'/api/session/resolve'" in sessions
    assert "_withEidSessionScope" in sessions
    assert "await newSession(false,{resolveRecord:true})" in boot


def test_session_resolve_creates_owned_record_session(monkeypatch):
    import api.routes as routes

    monkeypatch.setenv("HERMES_WEBUI_EID_CONTEXT", "1")
    monkeypatch.setenv("HERMES_WEBUI_EID_DEVELOPMENT_MODE", "1")
    monkeypatch.setenv("HERMES_WEBUI_EID_DEVELOPMENT_SUBJECT", "user-a")
    monkeypatch.setattr(routes, "_check_csrf", lambda _handler: True)
    monkeypatch.setattr(routes, "read_body", lambda _handler: {
        "record_id": "record-a",
        "profile": "default",
    })
    monkeypatch.setattr(routes, "all_sessions", lambda: [])
    monkeypatch.setattr(routes, "_session_model_state_from_request", lambda *_: ("model-a", "provider-a"))
    monkeypatch.setattr(routes, "publish_session_list_changed", lambda *_: None)

    created = Session(workspace=".")
    created.save = lambda *_, **__: None
    captured_kwargs = {}

    def fake_new_session(**kwargs):
        captured_kwargs.update(kwargs)
        created.eid_subject = kwargs["eid_subject"]
        created.eid_tenant = kwargs["eid_tenant"]
        created.record_id = kwargs["record_id"]
        created.context_type = kwargs["context_type"]
        return created

    monkeypatch.setattr(routes, "new_session", fake_new_session)
    response = {}
    monkeypatch.setattr(routes, "j", lambda _handler, payload, status=200, **_: response.update(payload=payload, status=status))
    monkeypatch.setattr(routes, "bad", lambda _handler, message, status=400: response.update(error=message, status=status))

    assert routes.handle_post(_handler(), urlparse("http://localhost/api/session/resolve")) is None
    assert response["status"] == 200
    assert response["payload"]["created"] is True
    assert captured_kwargs["eid_subject"] == "user-a"
    assert captured_kwargs["record_id"] == "record-a"
    assert captured_kwargs["context_type"] == "eid-record"


def test_session_resolve_restores_only_current_users_record(monkeypatch):
    import api.routes as routes

    monkeypatch.setenv("HERMES_WEBUI_EID_CONTEXT", "1")
    monkeypatch.setenv("HERMES_WEBUI_EID_DEVELOPMENT_MODE", "1")
    monkeypatch.setenv("HERMES_WEBUI_EID_DEVELOPMENT_SUBJECT", "user-a")
    monkeypatch.setattr(routes, "_check_csrf", lambda _handler: True)
    monkeypatch.setattr(routes, "read_body", lambda _handler: {"record_id": "record-a"})

    owned = Session(session_id="owned-session", eid_subject="user-a", record_id="record-a")
    foreign = Session(session_id="foreign-session", eid_subject="user-b", record_id="record-a")
    monkeypatch.setattr(routes, "all_sessions", lambda: [foreign.compact(), owned.compact()])
    monkeypatch.setattr(routes, "get_session", lambda sid, **_: owned if sid == owned.session_id else foreign)
    monkeypatch.setattr(routes, "new_session", lambda **_: pytest.fail("must restore instead of creating"))
    response = {}
    monkeypatch.setattr(routes, "j", lambda _handler, payload, status=200, **_: response.update(payload=payload, status=status))
    monkeypatch.setattr(routes, "bad", lambda _handler, message, status=400: response.update(error=message, status=status))

    routes.handle_post(_handler(), urlparse("http://localhost/api/session/resolve"))
    assert response["payload"]["created"] is False
    assert response["payload"]["session"]["session_id"] == "owned-session"
