"""Record-scoped EID embedding without user authentication."""

from __future__ import annotations

import os
import re


_RECORD_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,128}$")


class EidRecordContextError(ValueError):
    """Invalid or missing EID record context."""

    status = 400


def _truthy(value: object) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def eid_record_context_enabled(environ: dict[str, str] | None = None) -> bool:
    source = os.environ if environ is None else environ
    return _truthy(source.get("HERMES_WEBUI_EID_RECORD_CONTEXT"))


def validate_record_id(value: object, *, required: bool = True) -> str | None:
    record_id = str(value or "").strip()
    if not record_id:
        if required:
            raise EidRecordContextError("record_id is required")
        return None
    if not _RECORD_ID_RE.fullmatch(record_id):
        raise EidRecordContextError("invalid record_id")
    return record_id


def session_matches_record(session, record_id: str | None) -> bool:
    value = getattr(session, "record_id", None) if not isinstance(session, dict) else session.get("record_id")
    return str(value or "") == str(record_id or "")
