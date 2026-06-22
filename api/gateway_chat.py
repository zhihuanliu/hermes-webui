"""Default-off Hermes Gateway bridge for browser-originated chat turns."""
from __future__ import annotations

import json
import logging
import os
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from api.config import (
    CANCEL_FLAGS,
    STREAMS,
    STREAMS_LOCK,
    STREAM_LAST_EVENT_ID,
    STREAM_LIVE_TOOL_CALLS,
    STREAM_PARTIAL_TEXT,
    STREAM_REASONING_TEXT,
    _get_session_agent_lock,
    register_active_run,
    unregister_active_run,
    update_active_run,
)
from api.helpers import _redact_text, redact_session_data
from api.models import get_session, merge_session_messages_append_only
from api.run_journal import RunJournalWriter

logger = logging.getLogger(__name__)

_WEBUI_CHAT_BACKEND_ENV = "HERMES_WEBUI_CHAT_BACKEND"
_WEBUI_GATEWAY_BASE_URL_ENV = "HERMES_WEBUI_GATEWAY_BASE_URL"
_WEBUI_GATEWAY_API_KEY_ENV = "HERMES_WEBUI_GATEWAY_API_KEY"
_WEBUI_GATEWAY_TRANSPORT_ENV = "HERMES_WEBUI_GATEWAY_TRANSPORT"
_GATEWAY_CHAT_BACKENDS = {"gateway", "api_server", "api-server"}
_GATEWAY_COMPLETIONS_TRANSPORTS = {"completions", "chat", "chat_completions", "chat-completions"}

# Hermes Gateway approval/clarify contract (api_server):
# - GET /v1/runs/{run_id}/events emits JSON SSE lines:
#     data: {"event":"approval.request","run_id":"...","command":"...",
#            "description":"...","pattern_key":"...","pattern_keys":[...],...}
# - POST /v1/runs/{run_id}/approval  body: {"choice":"once|session|always|deny"}
# - {"event":"clarify.request","clarify_id":"...", ...}
# - POST /v1/runs/{run_id}/clarifications/{clarify_id}/respond
#     body: {"response":"..."}
# Chat completions (/v1/chat/completions) only guarantees hermes.tool.progress;
# approval blocking there is invisible unless transport=runs (default).
_GATEWAY_SESSION_RUNS: dict[str, dict[str, Any]] = {}
_GATEWAY_SESSION_RUNS_LOCK = threading.Lock()


def webui_chat_backend_mode(config_data=None, environ: dict[str, str] | None = None) -> str:
    """Return the explicitly selected browser chat backend.

    The default remains the in-process WebUI runtime. Only explicit gateway
    values opt browser chat into the Hermes API server bridge; generic truthy
    strings are deliberately ignored so deployments do not change execution
    ownership by accident.
    """
    source = os.environ if environ is None else environ
    cfg = config_data if isinstance(config_data, dict) else {}
    raw = str(
        source.get(_WEBUI_CHAT_BACKEND_ENV)
        or cfg.get("webui_chat_backend")
        or ""
    ).strip().lower()
    if raw in _GATEWAY_CHAT_BACKENDS:
        return "gateway"
    return "legacy"


def webui_gateway_chat_enabled(config_data=None, environ: dict[str, str] | None = None) -> bool:
    return webui_chat_backend_mode(config_data, environ) == "gateway"


def _gateway_base_url(config_data=None, environ: dict[str, str] | None = None) -> str:
    source = os.environ if environ is None else environ
    cfg = config_data if isinstance(config_data, dict) else {}
    raw = str(
        source.get(_WEBUI_GATEWAY_BASE_URL_ENV)
        or cfg.get("webui_gateway_base_url")
        or "http://127.0.0.1:8642"
    ).strip()
    return raw.rstrip("/") or "http://127.0.0.1:8642"


def _gateway_api_key(environ: dict[str, str] | None = None) -> str:
    source = os.environ if environ is None else environ
    return str(
        source.get(_WEBUI_GATEWAY_API_KEY_ENV)
        or source.get("API_SERVER_KEY")
        or ""
    ).strip()


def gateway_chat_config_status(config_data=None, environ: dict[str, str] | None = None) -> dict:
    """Return redacted Gateway-backed chat configuration status."""
    mode = webui_chat_backend_mode(config_data, environ)
    base_url = _gateway_base_url(config_data, environ)
    return {
        "enabled": mode == "gateway",
        "backend": mode,
        "base_url_configured": bool(base_url),
        "api_key_configured": bool(_gateway_api_key(environ)),
    }


def _gateway_http_error_event(exc: urllib.error.HTTPError, err_body: str, *, api_key_configured: bool) -> dict:
    safe = _redact_text(err_body or str(exc))[:500]
    if exc.code == 401:
        return {
            "label": "Gateway authentication failed",
            "type": "gateway_auth_error",
            "message": "Gateway rejected the WebUI API key (HTTP 401).",
            "hint": (
                "Set HERMES_WEBUI_GATEWAY_API_KEY to the same value as the Hermes Gateway "
                "API_SERVER_KEY, or disable HERMES_WEBUI_CHAT_BACKEND=gateway."
                if not api_key_configured
                else "Check that HERMES_WEBUI_GATEWAY_API_KEY matches the Hermes Gateway API_SERVER_KEY."
            ),
        }
    return {
        "label": "Gateway request failed",
        "type": "gateway_http_error",
        "message": f"Gateway returned HTTP {exc.code}.",
        "hint": safe or "Check the configured Gateway API server.",
    }


def _gateway_sse_delta(payload: dict) -> str:
    """Extract assistant text from an OpenAI-compatible streaming chunk."""
    try:
        choices = payload.get("choices") or []
        if not choices:
            return ""
        choice = choices[0] or {}
        delta = choice.get("delta") or {}
        content = delta.get("content")
        if isinstance(content, str):
            return content
        message = choice.get("message") or {}
        content = message.get("content")
        return content if isinstance(content, str) else ""
    except Exception:
        return ""


def _gateway_stream_usage(payload: dict) -> dict:
    usage = payload.get("usage") if isinstance(payload, dict) else None
    if not isinstance(usage, dict):
        return {}
    return {
        "input_tokens": int(usage.get("prompt_tokens") or usage.get("input_tokens") or 0),
        "output_tokens": int(usage.get("completion_tokens") or usage.get("output_tokens") or 0),
        "estimated_cost": usage.get("estimated_cost") or usage.get("estimated_cost_usd") or 0,
    }


def _gateway_transport_mode(config_data=None, environ: dict[str, str] | None = None) -> str:
    """Return the Gateway HTTP transport used for browser chat turns."""
    source = os.environ if environ is None else environ
    cfg = config_data if isinstance(config_data, dict) else {}
    raw = str(
        source.get(_WEBUI_GATEWAY_TRANSPORT_ENV)
        or cfg.get("webui_gateway_transport")
        or "runs"
    ).strip().lower()
    if raw in _GATEWAY_COMPLETIONS_TRANSPORTS:
        return "completions"
    return "runs"


def register_gateway_session_run(
    session_id: str,
    *,
    run_id: str,
    stream_id: str,
) -> None:
    """Track the active remote Gateway run for approval/clarify respond routing."""
    with _GATEWAY_SESSION_RUNS_LOCK:
        _GATEWAY_SESSION_RUNS[session_id] = {
            "run_id": str(run_id),
            "stream_id": str(stream_id),
            "registered_at": time.time(),
        }


def clear_gateway_session_run(session_id: str, stream_id: str | None = None) -> None:
    with _GATEWAY_SESSION_RUNS_LOCK:
        entry = _GATEWAY_SESSION_RUNS.get(session_id)
        if entry is None:
            return
        if stream_id and entry.get("stream_id") != stream_id:
            return
        _GATEWAY_SESSION_RUNS.pop(session_id, None)


def get_gateway_session_run(session_id: str) -> dict[str, Any] | None:
    with _GATEWAY_SESSION_RUNS_LOCK:
        entry = _GATEWAY_SESSION_RUNS.get(session_id)
        return dict(entry) if isinstance(entry, dict) else None


def gateway_session_has_active_run(session_id: str, stream_id: str | None = None) -> bool:
    entry = get_gateway_session_run(session_id)
    if not entry:
        return False
    if stream_id and entry.get("stream_id") != stream_id:
        return False
    return bool(entry.get("run_id"))


def _gateway_request_headers(
    session_id: str,
    session: Any,
    api_key: str,
    *,
    accept: str = "application/json",
) -> dict[str, str]:
    headers = {
        "Content-Type": "application/json",
        "Accept": accept,
        "X-Hermes-Session-Id": session_id,
    }
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
        headers["X-Hermes-Session-Key"] = f"webui:{session_id}"
    if getattr(session, "record_id", None):
        headers["X-EID-Record-Id"] = str(session.record_id)
    return headers


def _gateway_approval_payload(payload: dict) -> dict:
    """Normalize Gateway approval.request payloads to WebUI approval dict shape."""
    data = dict(payload or {})
    command = str(data.get("command") or data.get("cmd") or "").strip()
    description = str(
        data.get("description")
        or data.get("message")
        or data.get("summary")
        or ""
    ).strip()
    pattern_key = str(data.get("pattern_key") or data.get("pattern") or "").strip()
    pattern_keys = data.get("pattern_keys")
    if not isinstance(pattern_keys, list):
        pattern_keys = [pattern_key] if pattern_key else []
    else:
        pattern_keys = [str(k).strip() for k in pattern_keys if str(k).strip()]
    normalized = {
        "command": command,
        "description": description,
        "pattern_key": pattern_key or (pattern_keys[0] if pattern_keys else ""),
        "pattern_keys": pattern_keys,
    }
    gateway_approval_id = data.get("approval_id") or data.get("id")
    if gateway_approval_id:
        normalized["gateway_approval_id"] = str(gateway_approval_id)
    return normalized


def _gateway_clarify_payload(payload: dict) -> dict:
    data = dict(payload or {})
    choices = data.get("choices") or data.get("choices_offered") or []
    if not isinstance(choices, list):
        choices = []
    normalized = {
        "question": str(data.get("question") or data.get("prompt") or "").strip(),
        "choices_offered": [str(c) for c in choices if str(c).strip()],
        "kind": "clarify",
        "requested_at": time.time(),
    }
    gateway_clarify_id = data.get("clarify_id") or data.get("clarification_id") or data.get("id")
    if gateway_clarify_id:
        # Keep the remote id separately so the WebUI queue can retain its stable
        # local clarify_id contract while the response is routed back to Gateway.
        normalized["gateway_clarify_id"] = str(gateway_clarify_id)
    return normalized


def _bridge_gateway_approval_to_webui(session_id: str, payload: dict, put_gateway_event) -> dict:
    """Register a remote Gateway approval with WebUI polling/SSE + chat stream."""
    from api.routes import _lock, _pending, submit_pending

    normalized = _gateway_approval_payload(payload)
    submit_pending(session_id, normalized)
    with _lock:
        queue_list = _pending.get(session_id)
        if isinstance(queue_list, list) and queue_list:
            head = dict(queue_list[0])
        else:
            head = normalized
    put_gateway_event("approval", head)
    return head


def _bridge_gateway_clarify_to_webui(session_id: str, payload: dict, put_gateway_event) -> dict:
    from api.clarify import submit_pending as submit_clarify_pending

    data = _gateway_clarify_payload(payload)
    data["session_id"] = session_id
    entry = submit_clarify_pending(session_id, data)
    head = dict(entry.data)
    put_gateway_event("clarify", head)
    return head


def forward_gateway_approval_response(session_id: str, choice: str) -> bool:
    """Forward a browser approval choice to the remote Hermes Gateway run."""
    entry = get_gateway_session_run(session_id)
    run_id = (entry or {}).get("run_id")
    if not run_id:
        return False
    from api.config import get_config

    cfg = get_config()
    base_url = _gateway_base_url(cfg)
    api_key = _gateway_api_key()
    url = f"{base_url}/v1/runs/{run_id}/approval"
    try:
        session = get_session(session_id)
    except KeyError:
        session = None
    headers = _gateway_request_headers(session_id, session, api_key, accept="application/json")
    body = json.dumps({"choice": choice}).encode("utf-8")
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
        payload = json.loads(raw or "{}")
        if isinstance(payload, dict) and payload.get("resolved", 0) > 0:
            return True
        return resp.status in (200, 201, 202)
    except urllib.error.HTTPError as exc:
        if exc.code in (409, 404):
            return False
        logger.warning(
            "Gateway approval respond failed for session %s run %s: HTTP %s",
            session_id,
            run_id,
            exc.code,
        )
        return False
    except Exception:
        logger.debug("Gateway approval respond failed for session %s", session_id, exc_info=True)
        return False


def forward_gateway_clarify_response(
    session_id: str,
    gateway_clarify_id: str,
    response: str,
) -> bool:
    """Forward a WebUI clarification answer to the active remote Gateway run."""
    entry = get_gateway_session_run(session_id)
    run_id = str((entry or {}).get("run_id") or "").strip()
    clarify_id = str(gateway_clarify_id or "").strip()
    if not run_id or not clarify_id:
        return False

    from api.config import get_config

    cfg = get_config()
    base_url = _gateway_base_url(cfg)
    api_key = _gateway_api_key()
    quoted_run_id = urllib.parse.quote(run_id, safe="")
    quoted_clarify_id = urllib.parse.quote(clarify_id, safe="")
    url = f"{base_url}/v1/runs/{quoted_run_id}/clarifications/{quoted_clarify_id}/respond"
    try:
        session = get_session(session_id)
    except KeyError:
        session = None
    headers = _gateway_request_headers(session_id, session, api_key, accept="application/json")
    body = json.dumps({"response": str(response or "")}).encode("utf-8")
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            resp.read()
            return resp.status in (200, 201, 202)
    except urllib.error.HTTPError as exc:
        if exc.code in (404, 409):
            return False
        logger.warning(
            "Gateway clarify respond failed for session %s run %s: HTTP %s",
            session_id,
            run_id,
            exc.code,
        )
        return False
    except Exception:
        logger.debug("Gateway clarify respond failed for session %s", session_id, exc_info=True)
        return False


def _gateway_sse_named_event(sse_event: str, payload: dict) -> tuple[str, dict] | None:
    """Translate non-run Gateway SSE event names (chat completions transport)."""
    if sse_event in {"hermes.approval", "approval", "approval.request"}:
        return ("__approval__", payload)
    if sse_event in {"hermes.clarify", "clarify", "clarify.request"}:
        return ("__clarify__", payload)
    return None


def _gateway_run_event(payload: dict) -> tuple[str, Any] | None:
    """Translate /v1/runs/{run_id}/events payloads to WebUI stream events."""
    if not isinstance(payload, dict):
        return None
    event_type = str(payload.get("event") or "").strip()
    if event_type == "message.delta":
        delta = payload.get("delta")
        if isinstance(delta, str) and delta:
            return ("token", {"text": delta})
        return None
    if event_type == "approval.request":
        return ("__approval__", payload)
    if event_type == "clarify.request":
        return ("__clarify__", payload)
    if event_type == "tool.started":
        name = str(payload.get("tool") or payload.get("name") or "").strip()
        if not name or name.startswith("_"):
            return None
        event_payload = {
            "event_type": "tool.started",
            "name": name,
            "preview": payload.get("preview"),
            "args": payload.get("args") if isinstance(payload.get("args"), dict) else {},
            "is_error": False,
        }
        tid = payload.get("tool_call_id") or payload.get("toolCallId") or payload.get("id")
        if tid:
            event_payload["tid"] = str(tid)
        return ("tool", event_payload)
    if event_type == "tool.completed":
        name = str(payload.get("tool") or payload.get("name") or "").strip()
        if not name or name.startswith("_"):
            return None
        event_payload = {
            "event_type": "tool.completed",
            "name": name,
            "preview": payload.get("preview"),
            "args": payload.get("args") if isinstance(payload.get("args"), dict) else {},
            "is_error": bool(payload.get("error")),
        }
        tid = payload.get("tool_call_id") or payload.get("toolCallId") or payload.get("id")
        if tid:
            event_payload["tid"] = str(tid)
        return ("tool_complete", event_payload)
    if event_type == "run.completed":
        return ("__run_completed__", payload)
    if event_type in {"run.failed", "error"}:
        return ("__run_failed__", payload)
    return None


def _record_gateway_tool_live_event(stream_id: str, event_name: str, event_payload: dict) -> None:
    if stream_id not in STREAM_LIVE_TOOL_CALLS:
        return
    if event_name == "tool":
        STREAM_LIVE_TOOL_CALLS[stream_id].append({
            "name": event_payload.get("name"),
            "args": event_payload.get("args") or {},
            "done": False,
            **({"tid": event_payload.get("tid")} if event_payload.get("tid") else {}),
        })
    elif event_name == "tool_complete":
        for shared_tc in reversed(STREAM_LIVE_TOOL_CALLS[stream_id]):
            if shared_tc.get("done"):
                continue
            if (
                event_payload.get("tid") and shared_tc.get("tid") == event_payload.get("tid")
            ) or shared_tc.get("name") == event_payload.get("name"):
                shared_tc["done"] = True
                shared_tc["is_error"] = bool(event_payload.get("is_error"))
                break


def _gateway_tool_progress_event(payload: dict) -> tuple[str, dict] | None:
    """Translate Hermes Gateway tool-progress SSE payloads to WebUI events."""
    if not isinstance(payload, dict):
        return None
    name = str(payload.get("tool") or payload.get("name") or payload.get("function_name") or "").strip()
    if not name or name.startswith("_"):
        return None
    status = str(payload.get("status") or "running").strip().lower()
    tid = payload.get("toolCallId") or payload.get("tool_call_id") or payload.get("id")
    is_complete = status in {"completed", "complete", "success", "error", "failed"}
    event_payload = {
        "event_type": "tool.completed" if is_complete else "tool.started",
        "name": name,
        "preview": payload.get("label") or payload.get("preview"),
        "args": payload.get("args") if isinstance(payload.get("args"), dict) else {},
        "is_error": status in {"error", "failed"},
    }
    if tid:
        event_payload["tid"] = str(tid)
    return ("tool_complete" if is_complete else "tool"), event_payload


def _stream_writeback_is_current(session: Any, stream_id: str) -> bool:
    return bool(stream_id and getattr(session, "active_stream_id", None) == stream_id)


def _clear_gateway_pending_state(session: Any, stream_id: str) -> None:
    if not _stream_writeback_is_current(session, stream_id):
        return
    session.active_stream_id = None
    session.pending_user_message = None
    session.pending_attachments = None
    session.pending_started_at = None
    session.save()


def _finalize_gateway_turn(
    session_id,
    stream_id,
    msg_text,
    attachments,
    workspace,
    model,
    model_provider,
    assistant_text,
    usage,
    put_gateway_event,
):
    with _get_session_agent_lock(session_id):
        s = get_session(session_id)
        if not _stream_writeback_is_current(s, stream_id):
            return None
        now = time.time()
        assistant_ts = now + 0.000001
        user_msg = {"role": "user", "content": str(msg_text or ""), "timestamp": now}
        if attachments:
            user_msg["attachments"] = list(attachments)
        assistant_msg = {"role": "assistant", "content": assistant_text, "timestamp": assistant_ts}
        previous_context = list(getattr(s, "context_messages", None) or getattr(s, "messages", None) or [])
        s.context_messages = previous_context + [user_msg, assistant_msg]
        try:
            from api.streaming import _is_context_compression_marker

            display_context = [
                msg
                for msg in previous_context
                if not _is_context_compression_marker(msg)
            ]
        except Exception:
            logger.debug("Failed to filter gateway display context markers", exc_info=True)
            display_context = previous_context
        display = merge_session_messages_append_only(
            list(getattr(s, "messages", None) or []),
            display_context,
        )
        try:
            from api.streaming import _merge_display_messages_after_agent_result

            s.messages = _merge_display_messages_after_agent_result(
                display,
                previous_context,
                s.context_messages,
                str(msg_text or ""),
            )
        except Exception:
            logger.debug("Failed to merge gateway display transcript", exc_info=True)
            if display:
                latest = display[-1]
                if isinstance(latest, dict) and latest.get("role") == "user":
                    latest_text = " ".join(str(latest.get("content") or "").split())
                    msg_norm = " ".join(str(msg_text or "").split())
                    if latest_text == msg_norm:
                        display = display[:-1]
            s.messages = display + [user_msg, assistant_msg]
        s.active_stream_id = None
        s.pending_user_message = None
        s.pending_attachments = None
        s.pending_started_at = None
        s.workspace = str(workspace)
        s.model = model
        s.model_provider = model_provider
        s.save()
    gateway_session_payload = s.compact() | {"messages": s.messages, "tool_calls": []}
    put_gateway_event("done", {"session": redact_session_data(gateway_session_payload), "usage": usage})
    put_gateway_event("stream_end", {"session_id": session_id})
    return s


def _dispatch_gateway_stream_event(
    translated,
    *,
    session_id,
    stream_id,
    put_gateway_event,
    final_text_holder,
    usage,
):
    if not translated:
        return False
    event_name, event_payload = translated
    if event_name == "__approval__":
        _bridge_gateway_approval_to_webui(session_id, event_payload, put_gateway_event)
        update_active_run(stream_id, phase="gateway-approval")
        return False
    if event_name == "__clarify__":
        _bridge_gateway_clarify_to_webui(session_id, event_payload, put_gateway_event)
        update_active_run(stream_id, phase="gateway-clarify")
        return False
    if event_name == "__run_completed__":
        output = str(event_payload.get("output") or "").strip()
        if output:
            final_text_holder[0] = output
        run_usage = event_payload.get("usage") if isinstance(event_payload.get("usage"), dict) else {}
        usage.update({
            "input_tokens": int(run_usage.get("input_tokens") or 0),
            "output_tokens": int(run_usage.get("output_tokens") or 0),
            "estimated_cost": run_usage.get("estimated_cost") or run_usage.get("estimated_cost_usd") or 0,
        })
        return True
    if event_name == "__run_failed__":
        put_gateway_event("apperror", {
            "label": "Gateway run failed",
            "type": "gateway_run_failed",
            "message": str(event_payload.get("error") or event_payload.get("message") or "Gateway run failed."),
            "hint": "Check Hermes Gateway logs for this run.",
        })
        return True
    if event_name in {"tool", "tool_complete"}:
        _record_gateway_tool_live_event(stream_id, event_name, event_payload)
        put_gateway_event(event_name, event_payload)
        update_active_run(stream_id, phase="gateway-tool", latest_tool=event_payload.get("name"))
        return False
    if event_name == "token":
        delta = event_payload.get("text") or ""
        if delta:
            final_text_holder[0] += delta
            if stream_id in STREAM_PARTIAL_TEXT:
                STREAM_PARTIAL_TEXT[stream_id] += delta
            put_gateway_event("token", {"text": delta})
        return False
    put_gateway_event(event_name, event_payload)
    return False


def _consume_gateway_sse_stream(
    resp,
    *,
    session_id,
    stream_id,
    cancel_event,
    put_gateway_event,
    final_text_holder,
    usage,
    transport,
):
    sse_event = "message"
    last_payload = {}
    terminal = False
    for raw_line in resp:
        if cancel_event.is_set():
            put_gateway_event("cancel", {"message": "Cancelled by user"})
            return True
        line = raw_line.decode("utf-8", errors="replace").strip()
        if not line:
            sse_event = "message"
            continue
        if line.startswith("event:"):
            sse_event = line[6:].strip() or "message"
            continue
        if not line.startswith("data:"):
            continue
        data = line[5:].strip()
        if data == "[DONE]":
            break
        try:
            payload = json.loads(data)
        except json.JSONDecodeError:
            continue
        if transport == "completions" and sse_event == "hermes.tool.progress":
            translated = _gateway_tool_progress_event(payload)
            if _dispatch_gateway_stream_event(
                translated,
                session_id=session_id,
                stream_id=stream_id,
                put_gateway_event=put_gateway_event,
                final_text_holder=final_text_holder,
                usage=usage,
            ):
                return True
            sse_event = "message"
            continue
        named = _gateway_sse_named_event(sse_event, payload)
        if named:
            if _dispatch_gateway_stream_event(
                named,
                session_id=session_id,
                stream_id=stream_id,
                put_gateway_event=put_gateway_event,
                final_text_holder=final_text_holder,
                usage=usage,
            ):
                return True
            sse_event = "message"
            continue
        if transport == "completions" and isinstance(payload, dict):
            inline_event = str(payload.get("event") or "").strip()
            if inline_event == "approval.request":
                if _dispatch_gateway_stream_event(
                    ("__approval__", payload),
                    session_id=session_id,
                    stream_id=stream_id,
                    put_gateway_event=put_gateway_event,
                    final_text_holder=final_text_holder,
                    usage=usage,
                ):
                    return True
                continue
            if inline_event == "clarify.request":
                if _dispatch_gateway_stream_event(
                    ("__clarify__", payload),
                    session_id=session_id,
                    stream_id=stream_id,
                    put_gateway_event=put_gateway_event,
                    final_text_holder=final_text_holder,
                    usage=usage,
                ):
                    return True
                continue
        if transport == "runs":
            translated = _gateway_run_event(payload)
            if _dispatch_gateway_stream_event(
                translated,
                session_id=session_id,
                stream_id=stream_id,
                put_gateway_event=put_gateway_event,
                final_text_holder=final_text_holder,
                usage=usage,
            ):
                terminal = True
                break
            continue
        last_payload = payload
        delta = _gateway_sse_delta(payload)
        if delta:
            final_text_holder[0] += delta
            if stream_id in STREAM_PARTIAL_TEXT:
                STREAM_PARTIAL_TEXT[stream_id] += delta
            put_gateway_event("token", {"text": delta})
        usage.update({k: v for k, v in _gateway_stream_usage(payload).items() if v})
    if transport == "completions":
        usage.update({k: v for k, v in _gateway_stream_usage(last_payload).items() if v})
    return terminal


def _run_gateway_chat_streaming(
    session_id,
    msg_text,
    model,
    workspace,
    stream_id,
    attachments=None,
    *,
    model_provider=None,
):
    """Bridge a WebUI chat turn through Hermes Gateway's API server.

    This default-off path keeps the browser contract unchanged: /api/chat/start
    still returns a local stream_id and /api/chat/stream still receives WebUI SSE
    event names. The worker translates OpenAI-compatible streaming chunks from
    the configured Gateway API server into those local events and persists the
    final user/assistant turn back into the WebUI session.
    """
    q = STREAMS.get(stream_id)
    if q is None:
        return
    register_active_run(
        stream_id,
        session_id=session_id,
        started_at=time.time(),
        phase="gateway-starting",
        workspace=str(workspace),
        model=model,
        provider=model_provider,
        backend="gateway",
    )
    try:
        run_journal = RunJournalWriter(session_id, stream_id)
    except Exception:
        run_journal = None
        logger.debug("Failed to initialize gateway run journal for stream %s", stream_id, exc_info=True)
    cancel_event = threading.Event()
    with STREAMS_LOCK:
        CANCEL_FLAGS[stream_id] = cancel_event
        STREAM_PARTIAL_TEXT[stream_id] = ""
        STREAM_REASONING_TEXT[stream_id] = ""
        STREAM_LIVE_TOOL_CALLS[stream_id] = []

    def put_gateway_event(event, data):
        if cancel_event.is_set() and event not in ("cancel", "error", "apperror"):
            return
        if run_journal is not None:
            try:
                journaled = run_journal.append_sse_event(event, data)
                event_id = (journaled or {}).get("event_id") if isinstance(journaled, dict) else None
                if event_id:
                    STREAM_LAST_EVENT_ID[stream_id] = event_id
            except Exception:
                logger.debug("Failed to append gateway event %s for stream %s", event, stream_id, exc_info=True)
        try:
            q.put_nowait((event, data))
        except Exception:
            logger.debug("Failed to put gateway event to queue")

    s = None
    usage = {"input_tokens": 0, "output_tokens": 0, "estimated_cost": 0}
    try:
        s = get_session(session_id)
        from api.config import get_config  # imported lazily to avoid config-cycle churn

        cfg = get_config()
        try:
            from api.streaming import (
                _load_webui_prefill_context,
                _prefill_messages_with_webui_context,
                _normalize_prefill_messages_before_user_turn,
                _public_prefill_context_status,
                _webui_ephemeral_system_prompt,
            )

            prefill_context = _load_webui_prefill_context(cfg)
            # #3324: the WebUI session/delivery context (connected platforms,
            # home channels, delivery hints, session framing) is now carried in
            # the ephemeral system prompt rather than a prefill `user` message.
            # The gateway-backed path must build the SAME system prompt so that
            # context is not silently dropped on Gateway-routed WebUI chats.
            _gateway_system_prompt = _webui_ephemeral_system_prompt(
                None,
                surface_context={
                    "source": "webui",
                    "session_id": session_id,
                    "profile": getattr(s, "profile", None),
                    "workspace": s.workspace if s is not None else str(workspace),
                    "record_id": getattr(s, "record_id", None),
                    "context_type": getattr(s, "context_type", None),
                },
                config_data=cfg,
            )
            prefill_messages = _prefill_messages_with_webui_context(prefill_context, cfg)
            prefill_messages = _normalize_prefill_messages_before_user_turn(prefill_messages)
            prefill_messages = [
                {"role": "system", "content": _gateway_system_prompt},
                *prefill_messages,
            ]
            put_gateway_event("context_status", {
                "session_id": session_id,
                "prefill": _public_prefill_context_status(prefill_context),
            })
        except Exception:
            logger.debug("Failed to load WebUI gateway prefill context", exc_info=True)
            prefill_messages = []
            _gateway_system_prompt = ""
        try:
            from api.streaming import _context_messages_for_new_turn, _sanitize_messages_for_api

            # /api/chat/start eagerly checkpoints the current user turn before
            # this worker starts. Reuse the native context helper so Gateway gets
            # the durable model-facing history without duplicating msg_text.
            session_history = _sanitize_messages_for_api(
                _context_messages_for_new_turn(s, str(msg_text or "")),
                cfg=cfg,
            )
        except Exception:
            logger.exception("Failed to reconstruct WebUI session history for Gateway chat")
            session_history = []
        base_url = _gateway_base_url(cfg)
        api_key = _gateway_api_key()
        headers = _gateway_request_headers(session_id, s, api_key, accept="text/event-stream")
        message_content: Any = str(msg_text or "")
        if attachments:
            try:
                from api.streaming import _build_native_multimodal_message

                message_content = _build_native_multimodal_message("", str(msg_text or ""), attachments, str(workspace), cfg=cfg)
            except Exception:
                logger.debug("Failed to build gateway multimodal attachment payload", exc_info=True)
                message_content = str(msg_text or "")
        transport = _gateway_transport_mode(cfg)
        final_text_holder = [""]
        update_active_run(stream_id, phase="gateway-request", transport=transport)
        if transport == "runs":
            run_history = [
                dict(m)
                for m in [*prefill_messages, *session_history]
                if isinstance(m, dict) and m.get("role") != "system"
            ]
            run_body = {
                "input": message_content,
                "session_id": session_id,
                "instructions": _gateway_system_prompt or None,
                "conversation_history": run_history,
                "model": model or "default",
            }
            if model_provider:
                run_body["provider"] = model_provider
            start_req = urllib.request.Request(
                f"{base_url}/v1/runs",
                data=json.dumps(run_body).encode("utf-8"),
                headers=_gateway_request_headers(session_id, s, api_key, accept="application/json"),
                method="POST",
            )
            with urllib.request.urlopen(start_req, timeout=60) as start_resp:
                start_payload = json.loads(start_resp.read().decode("utf-8", errors="replace") or "{}")
            gateway_run_id = str(start_payload.get("run_id") or "").strip()
            if not gateway_run_id:
                put_gateway_event("apperror", {
                    "label": "Gateway run start failed",
                    "type": "gateway_run_start_error",
                    "message": "Gateway did not return a run_id.",
                    "hint": "Check that Hermes Gateway supports POST /v1/runs and approval_events.",
                })
                return
            register_gateway_session_run(session_id, run_id=gateway_run_id, stream_id=stream_id)
            events_req = urllib.request.Request(
                f"{base_url}/v1/runs/{gateway_run_id}/events",
                headers=headers,
                method="GET",
            )
            with urllib.request.urlopen(events_req, timeout=600) as resp:
                _consume_gateway_sse_stream(
                    resp,
                    session_id=session_id,
                    stream_id=stream_id,
                    cancel_event=cancel_event,
                    put_gateway_event=put_gateway_event,
                    final_text_holder=final_text_holder,
                    usage=usage,
                    transport="runs",
                )
        else:
            body = {
                "model": model or "default",
                "stream": True,
                "messages": [
                    *prefill_messages,
                    *session_history,
                    {"role": "user", "content": message_content},
                ],
            }
            if model_provider:
                body["provider"] = model_provider
            req = urllib.request.Request(
                f"{base_url}/v1/chat/completions",
                data=json.dumps(body).encode("utf-8"),
                headers=headers,
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=600) as resp:
                _consume_gateway_sse_stream(
                    resp,
                    session_id=session_id,
                    stream_id=stream_id,
                    cancel_event=cancel_event,
                    put_gateway_event=put_gateway_event,
                    final_text_holder=final_text_holder,
                    usage=usage,
                    transport="completions",
                )
        final_text = final_text_holder[0].strip()
        if not final_text:
            put_gateway_event("apperror", {
                "label": "Gateway returned no response",
                "type": "gateway_empty_response",
                "message": "Gateway returned no assistant message for this turn.",
                "hint": "Check that Hermes Gateway API server is running and reachable.",
            })
            return
        s = _finalize_gateway_turn(
            session_id,
            stream_id,
            msg_text,
            attachments,
            workspace,
            model,
            model_provider,
            final_text,
            usage,
            put_gateway_event,
        )
        if s is None:
            return
    except urllib.error.HTTPError as exc:
        try:
            err_body = exc.read(2048).decode("utf-8", errors="replace")
        except Exception:
            err_body = ""
        put_gateway_event(
            "apperror",
            _gateway_http_error_event(exc, err_body, api_key_configured=bool(_gateway_api_key())),
        )
    except Exception as exc:
        safe = _redact_text(str(exc))[:500]
        put_gateway_event("apperror", {
            "label": "Gateway request failed",
            "type": "gateway_error",
            "message": safe or "Gateway request failed.",
            "hint": "Check HERMES_WEBUI_GATEWAY_BASE_URL and Gateway API server health.",
        })
    finally:
        clear_gateway_session_run(session_id, stream_id)
        if s is not None:
            try:
                with _get_session_agent_lock(session_id):
                    _clear_gateway_pending_state(get_session(session_id), stream_id)
            except Exception:
                logger.debug("Failed to clear gateway stream state", exc_info=True)
        with STREAMS_LOCK:
            CANCEL_FLAGS.pop(stream_id, None)
            STREAM_PARTIAL_TEXT.pop(stream_id, None)
            STREAM_REASONING_TEXT.pop(stream_id, None)
            STREAM_LIVE_TOOL_CALLS.pop(stream_id, None)
            STREAM_LAST_EVENT_ID.pop(stream_id, None)
            STREAMS.pop(stream_id, None)
        unregister_active_run(stream_id)
