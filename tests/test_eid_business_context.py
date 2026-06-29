import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import urlparse

import pytest

from api.eid_record_context import (
    EidRecordContextError,
    eid_record_context_enabled,
    session_matches_record,
    validate_record_id,
)
from api.models import Session
from api.streaming import _build_agent_thread_env, _webui_ephemeral_system_prompt


def _handler(headers=None):
    return SimpleNamespace(headers=headers or {})


def _load_ship_lighting_module(name):
    scripts_dir = Path("Skills/ship-lighting/scripts").resolve()
    if str(scripts_dir) not in sys.path:
        sys.path.insert(0, str(scripts_dir))
    spec = importlib.util.spec_from_file_location(name, scripts_dir / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_record_id_validation_accepts_eid_ids_and_rejects_untrusted_shapes():
    assert validate_record_id("ad862e249e08461386f1fc86c9297719") == "ad862e249e08461386f1fc86c9297719"
    assert validate_record_id("record_A-17") == "record_A-17"
    with pytest.raises(EidRecordContextError):
        validate_record_id("../other-record")
    with pytest.raises(EidRecordContextError):
        validate_record_id("record id")


def test_record_context_requires_explicit_feature_flag():
    assert not eid_record_context_enabled({})
    assert eid_record_context_enabled({"HERMES_WEBUI_EID_RECORD_CONTEXT": "true"})


def test_session_record_match_uses_record_only():
    session = Session(
        record_id="record-a",
        context_type="eid-record",
    )
    assert session_matches_record(session, "record-a")
    assert not session_matches_record(session, "record-b")


def test_agent_context_contains_record_without_identity_or_token():
    prompt = _webui_ephemeral_system_prompt(
        None,
        surface_context={
            "source": "webui",
            "session_id": "session-a",
            "record_id": "record-a",
            "context_type": "eid-record",
        },
    )
    assert "Current EID record ID: record-a" in prompt
    assert "Business context type: eid-record" in prompt
    assert "delegation" not in prompt.lower()


def test_agent_thread_context_uses_only_dynamic_record_context():
    env = _build_agent_thread_env(
        {"SHIP_LIGHTING_RECORD_ID": "legacy-default"},
        "/workspace",
        "session-a",
        "/profile",
        "record-a",
    )
    assert env["HERMES_EID_RECORD_ID"] == "record-a"
    assert "HERMES_EID_DELEGATION" not in env
    streaming_source = open("api/streaming.py", encoding="utf-8").read()
    assert "_profile_runtime_env.pop('SHIP_LIGHTING_RECORD_ID', None)" in streaming_source


def test_ship_lighting_requires_record_but_not_identity(monkeypatch):
    dispatcher = _load_ship_lighting_module("tool_dispatcher")

    monkeypatch.delenv("HERMES_EID_RECORD_ID", raising=False)
    missing = dispatcher._bind_trusted_eid_context("get_decks", {})
    assert missing["error_type"] == "missing_record_context"

    monkeypatch.setenv("HERMES_EID_RECORD_ID", "record-a")
    params = {}
    assert dispatcher._bind_trusted_eid_context("get_decks", params) is None
    assert params["record_id"] == "record-a"
    assert "user_id" not in params
    assert "delegation_token" not in params


def test_ship_lighting_rejects_model_supplied_record(monkeypatch):
    dispatcher = _load_ship_lighting_module("tool_dispatcher")
    monkeypatch.setenv("HERMES_EID_RECORD_ID", "record-a")
    rejected = dispatcher._bind_trusted_eid_context("get_decks", {"record_id": "record-b"})
    assert rejected["error_type"] == "caller_supplied_eid_context"


def test_chatbot_scopes_all_api_requests_to_record():
    chatbot = open("static/chatbot.html", encoding="utf-8").read()
    sessions = open("static/sessions.js", encoding="utf-8").read()
    workspace = open("static/workspace.js", encoding="utf-8").read()
    boot = open("static/boot.js", encoding="utf-8").read()

    assert "__HERMES_CHATBOT_CONTEXT__" in chatbot
    assert "'/api/session/resolve'" in sessions
    assert "url.searchParams.set('record_id',recordId)" in workspace
    assert "await newSession(false,{resolveRecord:true})" in boot


def test_session_list_filter_uses_record_only(monkeypatch):
    import api.routes as routes

    monkeypatch.setenv("HERMES_WEBUI_EID_RECORD_CONTEXT", "1")
    rows = [
        Session(session_id="a", record_id="record-a").compact(),
        Session(session_id="b", record_id="record-b").compact(),
        Session(session_id="general").compact(),
    ]
    filtered, error_sent = routes._eid_filter_session_rows(
        _handler(), rows, urlparse("http://localhost/api/sessions?record_id=record-a")
    )
    assert error_sent is False
    assert [row["session_id"] for row in filtered] == ["a"]


def test_session_access_rejects_a_different_requested_record(monkeypatch):
    import api.routes as routes

    monkeypatch.setenv("HERMES_WEBUI_EID_RECORD_CONTEXT", "1")
    response = {}
    monkeypatch.setattr(
        routes,
        "bad",
        lambda _handler, message, status=400: response.update(error=message, status=status),
    )
    allowed = routes._eid_session_access_allowed(
        _handler(), Session(record_id="record-a"), "record-b"
    )
    assert allowed is False
    assert response == {"error": "Session not found", "status": 404}


def test_session_resolve_creates_record_session_without_identity(monkeypatch):
    import api.routes as routes

    monkeypatch.setenv("HERMES_WEBUI_EID_RECORD_CONTEXT", "1")
    monkeypatch.setattr(routes, "_check_csrf", lambda _handler: True)
    monkeypatch.setattr(routes, "read_body", lambda _handler: {
        "record_id": "record-a",
        "profile": "default",
    })
    captured_all_sessions_kwargs = {}
    monkeypatch.setattr(
        routes,
        "all_sessions",
        lambda **kwargs: captured_all_sessions_kwargs.update(kwargs) or [],
    )
    monkeypatch.setattr(routes, "_session_model_state_from_request", lambda *_: ("model-a", "provider-a"))
    monkeypatch.setattr(routes, "publish_session_list_changed", lambda *_: None)

    created = Session(workspace=".")
    created.save = lambda *_, **__: None
    captured_kwargs = {}

    def fake_new_session(**kwargs):
        captured_kwargs.update(kwargs)
        created.record_id = kwargs["record_id"]
        created.context_type = kwargs["context_type"]
        return created

    monkeypatch.setattr(routes, "new_session", fake_new_session)
    response = {}
    monkeypatch.setattr(routes, "j", lambda _handler, payload, status=200, **_: response.update(payload=payload, status=status))
    monkeypatch.setattr(routes, "bad", lambda _handler, message, status=400: response.update(error=message, status=status))

    routes.handle_post(_handler(), urlparse("http://localhost/api/session/resolve?record_id=record-a"))
    assert response["status"] == 200
    assert response["payload"]["created"] is True
    assert captured_kwargs["record_id"] == "record-a"
    assert captured_kwargs["context_type"] == "eid-record"
    assert captured_all_sessions_kwargs == {"record_id": "record-a"}


def test_session_resolve_accepts_record_id_from_query_when_body_omits_it(monkeypatch):
    import api.routes as routes

    monkeypatch.setenv("HERMES_WEBUI_EID_RECORD_CONTEXT", "1")
    monkeypatch.setattr(routes, "_check_csrf", lambda _handler: True)
    monkeypatch.setattr(routes, "read_body", lambda _handler: {"profile": "default"})
    captured_all_sessions_kwargs = {}
    monkeypatch.setattr(
        routes,
        "all_sessions",
        lambda **kwargs: captured_all_sessions_kwargs.update(kwargs) or [],
    )
    monkeypatch.setattr(routes, "_session_model_state_from_request", lambda *_: ("model-a", "provider-a"))
    monkeypatch.setattr(routes, "publish_session_list_changed", lambda *_: None)

    created = Session(workspace=".")
    created.save = lambda *_, **__: None
    captured_kwargs = {}

    def fake_new_session(**kwargs):
        captured_kwargs.update(kwargs)
        created.record_id = kwargs["record_id"]
        created.context_type = kwargs["context_type"]
        return created

    monkeypatch.setattr(routes, "new_session", fake_new_session)
    response = {}
    monkeypatch.setattr(routes, "j", lambda _handler, payload, status=200, **_: response.update(payload=payload, status=status))
    monkeypatch.setattr(routes, "bad", lambda _handler, message, status=400: response.update(error=message, status=status))

    routes.handle_post(_handler(), urlparse("http://localhost/api/session/resolve?record_id=record-a"))
    assert response["status"] == 200
    assert captured_kwargs["record_id"] == "record-a"
    assert captured_all_sessions_kwargs == {"record_id": "record-a"}


def test_session_resolve_restores_latest_session_for_record(monkeypatch):
    import api.routes as routes

    monkeypatch.setenv("HERMES_WEBUI_EID_RECORD_CONTEXT", "1")
    monkeypatch.setattr(routes, "_check_csrf", lambda _handler: True)
    monkeypatch.setattr(routes, "read_body", lambda _handler: {"record_id": "record-a"})

    older = Session(session_id="older", record_id="record-a", updated_at=1)
    latest = Session(session_id="latest", record_id="record-a", updated_at=2)
    other = Session(session_id="other", record_id="record-b", updated_at=3)
    captured_all_sessions_kwargs = {}
    monkeypatch.setattr(
        routes,
        "all_sessions",
        lambda **kwargs: (
            captured_all_sessions_kwargs.update(kwargs)
            or [older.compact(), other.compact(), latest.compact()]
        ),
    )
    monkeypatch.setattr(routes, "get_session", lambda sid, **_: {"older": older, "latest": latest, "other": other}[sid])
    monkeypatch.setattr(routes, "new_session", lambda **_: pytest.fail("must restore instead of creating"))
    response = {}
    monkeypatch.setattr(routes, "j", lambda _handler, payload, status=200, **_: response.update(payload=payload, status=status))
    monkeypatch.setattr(routes, "bad", lambda _handler, message, status=400: response.update(error=message, status=status))

    routes.handle_post(_handler(), urlparse("http://localhost/api/session/resolve?record_id=record-a"))
    assert response["payload"]["created"] is False
    assert response["payload"]["session"]["session_id"] == "latest"
    assert captured_all_sessions_kwargs == {"record_id": "record-a"}


def test_session_resolve_force_new_archives_record_candidates(monkeypatch):
    import api.routes as routes

    monkeypatch.setenv("HERMES_WEBUI_EID_RECORD_CONTEXT", "1")
    monkeypatch.setattr(routes, "_check_csrf", lambda _handler: True)
    monkeypatch.setattr(routes, "read_body", lambda _handler: {
        "record_id": "record-a",
        "force_new": True,
    })

    previous = Session(session_id="previous", record_id="record-a", updated_at=1)
    previous.save = lambda *_, **__: None
    captured_all_sessions_kwargs = {}
    monkeypatch.setattr(
        routes,
        "all_sessions",
        lambda **kwargs: captured_all_sessions_kwargs.update(kwargs) or [previous.compact()],
    )
    monkeypatch.setattr(routes, "get_session", lambda _sid, **_: previous)
    monkeypatch.setattr(routes, "_session_model_state_from_request", lambda *_: ("model-a", "provider-a"))
    monkeypatch.setattr(routes, "publish_session_list_changed", lambda *_: None)

    created = Session(session_id="created", record_id="record-a")
    created.save = lambda *_, **__: None
    monkeypatch.setattr(routes, "new_session", lambda **_: created)
    response = {}
    monkeypatch.setattr(routes, "j", lambda _handler, payload, status=200, **_: response.update(payload=payload, status=status))
    monkeypatch.setattr(routes, "bad", lambda _handler, message, status=400: response.update(error=message, status=status))

    routes.handle_post(_handler(), urlparse("http://localhost/api/session/resolve?record_id=record-a"))
    assert previous.archived is True
    assert response["payload"]["created"] is True
    assert response["payload"]["session"]["session_id"] == "created"
    assert captured_all_sessions_kwargs == {"record_id": "record-a"}
