---
status: complete
created: '2026-06-09'
tags: [security, iframe, csp, ddd]
priority: high
---

# Iframe Embedding Security Headers

> **Status**: complete | **Priority**: high | **Created**: 2026-06-09

## Overview

Hermes WebUI will be deployed as an independently served application and embedded
by another local development application through an iframe. The current parent
page origin is `http://localhost:5174`; the parent URL may include a variable
query parameter such as `?record_id=ad862e249e08461386f1fc86c9297719`.

The domain goal is to allow that host application to frame Hermes WebUI without
opening the WebUI to arbitrary framing. Modern browsers must rely on CSP
`frame-ancestors`, while legacy browsers receive an `X-Frame-Options` fallback.

## Domain Model

Bounded context: Web delivery security headers.

Aggregate: `SecurityHeaderPolicy`

Entities and values:

- `AllowedFrameAncestor`: origin allowed to embed Hermes WebUI.
- `ModernFramePolicy`: enforced CSP `frame-ancestors` directive.
- `LegacyFramePolicy`: `X-Frame-Options` fallback for older user agents.

Current values:

- `AllowedFrameAncestor`: `http://localhost:5174`
- `ModernFramePolicy`: `frame-ancestors 'self' http://localhost:5174`
- `LegacyFramePolicy`: `ALLOW-FROM http://localhost:5174`

Invariant:

- The query string of the parent page, including `record_id`, is not part of the
  frame policy. Browsers evaluate frame ancestors by origin, so any
  `http://localhost:5174/?record_id=<value>` parent page is covered by the same
  origin rule.

## Design

The policy is centralized in `api/helpers.py`:

- `EMBED_ALLOWED_ORIGIN`
- `FRAME_ANCESTORS_VALUE`
- `LEGACY_X_FRAME_OPTIONS_VALUE`

All normal text and JSON responses receive:

- `Content-Security-Policy` with `frame-ancestors 'self' http://localhost:5174`
- `X-Frame-Options: ALLOW-FROM http://localhost:5174`

The report-only CSP emitted by `server.py` reuses `FRAME_ANCESTORS_VALUE`, so
monitoring reflects the same allowed ancestor as the enforced policy.

`X-Frame-Options: DENY` was removed from the normal helper path because it would
block the target iframe use case in legacy browsers before the application can
render. `ALLOW-FROM` is intentionally scoped to one origin, matching the current
development host app.

## Plan

- [x] Add a shared iframe ancestor policy value in `api/helpers.py`.
- [x] Add enforced CSP `frame-ancestors` for normal WebUI responses.
- [x] Replace the old XFO `DENY` fallback with `ALLOW-FROM http://localhost:5174`.
- [x] Reuse the same frame ancestor value in report-only CSP.
- [x] Update automated tests that pinned the old no-frame behavior.
- [x] Document the behavior in README, TESTING, CHANGELOG, and this spec.

## Test

- [x] `tests/test_iframe_embedding_headers.py` verifies the shared constants and
  emitted response headers.
- [x] `tests/test_sprint19.py` verifies the legacy XFO fallback value on real
  JSON responses.
- [x] `tests/test_issue1909_csp_report_only.py` verifies report-only CSP reports
  the same allowed parent origin.

Manual verification:

- Start Hermes WebUI and confirm `/health` or `/api/auth/status` includes
  `Content-Security-Policy` with `frame-ancestors 'self' http://localhost:5174`.
- Confirm the same response includes `X-Frame-Options: ALLOW-FROM
  http://localhost:5174`.
- Embed the WebUI URL from a page served at `http://localhost:5174` and verify
  changing `record_id` does not affect iframe loading.

## Notes

When the embedding host changes for server deployment, update the centralized
allowed origin first, then update this spec, README, and tests together. If more
than one external parent origin is required, CSP can list multiple origins, but
the legacy XFO fallback only has practical single-origin semantics.
