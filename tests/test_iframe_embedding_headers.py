"""Regression tests for embedding Hermes WebUI in the local host app iframe."""

from api.helpers import (
    EMBED_ALLOWED_ORIGIN,
    FRAME_ANCESTORS_VALUE,
    LEGACY_X_FRAME_OPTIONS_VALUE,
    j,
)


class _HeaderCapture:
    def __init__(self):
        self.headers = {}
        self.wfile = self

    def send_response(self, status):
        self.status = status

    def send_header(self, key, value):
        self.headers[key] = value

    def end_headers(self):
        pass

    def write(self, body):
        self.body = body


def test_embedding_origin_is_the_local_host_app_origin():
    assert EMBED_ALLOWED_ORIGIN == "http://localhost:5174"
    assert FRAME_ANCESTORS_VALUE == "'self' http://localhost:5174"
    assert LEGACY_X_FRAME_OPTIONS_VALUE == "ALLOW-FROM http://localhost:5174"


def test_json_security_headers_allow_configured_iframe_parent():
    handler = _HeaderCapture()

    j(handler, {"ok": True})

    csp = handler.headers["Content-Security-Policy"]
    assert "frame-ancestors 'self' http://localhost:5174" in csp
    assert handler.headers["X-Frame-Options"] == "ALLOW-FROM http://localhost:5174"
    assert handler.headers["X-Content-Type-Options"] == "nosniff"
