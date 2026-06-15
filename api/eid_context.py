"""Trusted EID identity and record-authorization boundary for embedded chat."""

from __future__ import annotations

import json
import os
import re
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass


_RECORD_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,128}$")
_IDENTITY_RE = re.compile(r"^[^\x00-\x1f\x7f]{1,256}$")

# Positive-grant cache for authorize_record_access. The ownership guard runs on
# every request that names a record session (including stream-status polling and
# sidebar refreshes), so without this every poll would issue a blocking HTTP
# round-trip to the EID backend. Only successful grants are cached — denials,
# missing records, and transport failures are always re-checked. Revocation
# latency is bounded by the TTL.
_AUTHORIZE_CACHE: dict[tuple[str, str, str], float] = {}
_AUTHORIZE_CACHE_LOCK = threading.Lock()
_AUTHORIZE_CACHE_MAX_ENTRIES = 4096
_AUTHORIZE_CACHE_DEFAULT_TTL = 30.0
_AUTHORIZE_CACHE_MAX_TTL = 300.0


class EidContextError(ValueError):
    """Base error with an HTTP status suitable for route responses."""

    status = 400


class EidAuthenticationError(EidContextError):
    status = 401


class EidAuthorizationError(EidContextError):
    status = 403


class EidRecordNotFoundError(EidContextError):
    status = 404


class EidAuthorizationUnavailableError(EidContextError):
    status = 503


@dataclass(frozen=True)
class TrustedEidContext:
    subject: str
    tenant: str | None = None
    delegation_token: str | None = None


def _truthy(value: object) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def eid_context_enabled(environ: dict[str, str] | None = None) -> bool:
    source = os.environ if environ is None else environ
    return _truthy(source.get("HERMES_WEBUI_EID_CONTEXT"))


def eid_development_mode(environ: dict[str, str] | None = None) -> bool:
    source = os.environ if environ is None else environ
    return _truthy(source.get("HERMES_WEBUI_EID_DEVELOPMENT_MODE"))


def validate_record_id(value: object, *, required: bool = True) -> str | None:
    record_id = str(value or "").strip()
    if not record_id:
        if required:
            raise EidContextError("record_id is required")
        return None
    if not _RECORD_ID_RE.fullmatch(record_id):
        raise EidContextError("invalid record_id")
    return record_id


def _validated_identity(value: object, label: str, *, required: bool) -> str | None:
    normalized = str(value or "").strip()
    if not normalized:
        if required:
            raise EidAuthenticationError(f"missing trusted EID {label}")
        return None
    if not _IDENTITY_RE.fullmatch(normalized):
        raise EidAuthenticationError(f"invalid trusted EID {label}")
    return normalized


def trusted_eid_context(handler, environ: dict[str, str] | None = None) -> TrustedEidContext | None:
    """Resolve identity only from trusted proxy headers or explicit dev config."""
    source = os.environ if environ is None else environ
    if not eid_context_enabled(source):
        return None

    if eid_development_mode(source):
        subject = _validated_identity(
            source.get("HERMES_WEBUI_EID_DEVELOPMENT_SUBJECT"),
            "development subject",
            required=True,
        )
        tenant = _validated_identity(
            source.get("HERMES_WEBUI_EID_DEVELOPMENT_TENANT"),
            "development tenant",
            required=False,
        )
        return TrustedEidContext(subject=subject or "", tenant=tenant)

    if not _truthy(source.get("HERMES_WEBUI_EID_TRUST_PROXY")):
        raise EidAuthenticationError("trusted EID proxy mode is not enabled")

    headers = getattr(handler, "headers", None)
    get_header = headers.get if headers is not None and hasattr(headers, "get") else lambda *_: None
    subject = _validated_identity(get_header("X-EID-Subject"), "subject", required=True)
    tenant = _validated_identity(get_header("X-EID-Tenant"), "tenant", required=False)
    delegation = str(get_header("X-EID-Delegation") or "").strip() or None
    return TrustedEidContext(subject=subject or "", tenant=tenant, delegation_token=delegation)


def _authorize_cache_ttl(source) -> float:
    raw = str(source.get("HERMES_WEBUI_EID_AUTHORIZE_CACHE_TTL") or "").strip()
    if not raw:
        return _AUTHORIZE_CACHE_DEFAULT_TTL
    try:
        ttl = float(raw)
    except ValueError:
        return _AUTHORIZE_CACHE_DEFAULT_TTL
    return max(0.0, min(_AUTHORIZE_CACHE_MAX_TTL, ttl))


def _authorize_cache_get(key: tuple[str, str, str]) -> bool:
    now = time.monotonic()
    with _AUTHORIZE_CACHE_LOCK:
        expires_at = _AUTHORIZE_CACHE.get(key)
        if expires_at is None:
            return False
        if expires_at <= now:
            _AUTHORIZE_CACHE.pop(key, None)
            return False
        return True


def _authorize_cache_put(key: tuple[str, str, str], ttl: float) -> None:
    if ttl <= 0:
        return
    now = time.monotonic()
    with _AUTHORIZE_CACHE_LOCK:
        if len(_AUTHORIZE_CACHE) >= _AUTHORIZE_CACHE_MAX_ENTRIES:
            expired = [k for k, exp in _AUTHORIZE_CACHE.items() if exp <= now]
            for k in expired:
                _AUTHORIZE_CACHE.pop(k, None)
            while len(_AUTHORIZE_CACHE) >= _AUTHORIZE_CACHE_MAX_ENTRIES:
                _AUTHORIZE_CACHE.pop(next(iter(_AUTHORIZE_CACHE)), None)
        _AUTHORIZE_CACHE[key] = now + ttl


def clear_authorize_cache() -> None:
    with _AUTHORIZE_CACHE_LOCK:
        _AUTHORIZE_CACHE.clear()


def authorize_record_access(
    context: TrustedEidContext,
    record_id: str,
    environ: dict[str, str] | None = None,
) -> None:
    """Ask EID to authorize the authenticated subject for one record."""
    source = os.environ if environ is None else environ
    record_id = validate_record_id(record_id) or ""
    if eid_development_mode(source):
        return

    url = str(source.get("HERMES_WEBUI_EID_AUTHORIZE_URL") or "").strip()
    if not url:
        raise EidAuthorizationUnavailableError("EID record authorization is not configured")

    cache_ttl = _authorize_cache_ttl(source)
    cache_key = (context.subject, str(context.tenant or ""), record_id)
    if cache_ttl > 0 and _authorize_cache_get(cache_key):
        return

    body = json.dumps({"record_id": record_id}).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "X-EID-Subject": context.subject,
    }
    if context.tenant:
        headers["X-EID-Tenant"] = context.tenant
    if context.delegation_token:
        headers["Authorization"] = f"Bearer {context.delegation_token}"
    request = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        timeout = max(0.1, min(30.0, float(source.get("HERMES_WEBUI_EID_AUTHORIZE_TIMEOUT") or 5)))
        with urllib.request.urlopen(request, timeout=timeout) as response:
            if response.status not in (200, 204):
                raise EidAuthorizationUnavailableError("unexpected EID authorization response")
        _authorize_cache_put(cache_key, cache_ttl)
    except urllib.error.HTTPError as exc:
        if exc.code == 403:
            raise EidAuthorizationError("record access denied") from exc
        if exc.code == 404:
            raise EidRecordNotFoundError("record not found") from exc
        if exc.code == 401:
            raise EidAuthenticationError("EID authentication expired") from exc
        raise EidAuthorizationUnavailableError("EID authorization service unavailable") from exc
    except (urllib.error.URLError, TimeoutError, ValueError) as exc:
        raise EidAuthorizationUnavailableError("EID authorization service unavailable") from exc


def session_owned_by_context(session, context: TrustedEidContext) -> bool:
    subject = getattr(session, "eid_subject", None) if not isinstance(session, dict) else session.get("eid_subject")
    tenant = getattr(session, "eid_tenant", None) if not isinstance(session, dict) else session.get("eid_tenant")
    return str(subject or "") == context.subject and str(tenant or "") == str(context.tenant or "")


def session_matches_record(session, record_id: str | None) -> bool:
    value = getattr(session, "record_id", None) if not isinstance(session, dict) else session.get("record_id")
    return str(value or "") == str(record_id or "")
