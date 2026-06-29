# Specs

This directory contains LeanSpec specifications for this project.

## Quick Start

```bash
# Create a new spec
lean-spec create my-feature

# List all specs
lean-spec list

# View the board
lean-spec board

# Validate specs
lean-spec validate
```

## Structure

Each spec lives in a numbered directory with a `README.md` file:

```
├── 001-feature-name/
│   └── README.md
└── 002-another-feature/
    └── README.md
```

## Spec Status Values

- `draft` - Being authored or refined
- `planned` - Not yet started
- `in-progress` - Currently being worked on
- `complete` - Finished
- `superseded` - Replaced by a newer spec; kept only for historical context
- `archived` - No longer relevant

## Specifications

- [005-iframe-embedding-security-headers](005-iframe-embedding-security-headers/README.md)
  - iframe embedding and response-header policy.
- [006-eid-auth-hermes-business-context](006-eid-auth-hermes-business-context/README.md)
  - **Superseded by 008**; historical EID login / per-user authorization proposal only.
- [007-eid-production-multi-user-deployment](007-eid-production-multi-user-deployment/README.md)
  - **Superseded by 008**; historical multi-user trusted-proxy deployment proposal only.
- [008-eid-record-scoped-hermes-integration](008-eid-record-scoped-hermes-integration/README.md)
  - Current record-only EID embedding model for session resolution, filtering, and Skill context.
- [009-eid-server-webui-container-deployment](009-eid-server-webui-container-deployment/README.md)
  - Server deployment plan for a standalone Hermes WebUI container embedded by EID and backed by remote Gateway.
- [010-eid-gateway-approval-bridge](010-eid-gateway-approval-bridge/README.md)
  - Gateway run approval bridge so EID iframe chat shows WebUI approval cards for remote gated tools.
- [011-eid-chatbot-zh-localization](011-eid-chatbot-zh-localization/README.md)
  - Simplified Chinese localization and startup loading UX for the EID-embedded chatbot page only.
- [012-eid-turn-complete-postmessage](012-eid-turn-complete-postmessage/README.md)
  - Approved postMessage contract for notifying eid-web after an embedded chatbot turn reaches SSE `done`.
- [013-eid-webui-package-deploy](013-eid-webui-package-deploy/README.md)
  - Windows packaging and Linux deployment procedure for Hermes WebUI only, assuming Hermes Agent/Gateway and EID frontend are deployed separately.

## Learn More

Visit [leanspec.dev](https://leanspec.dev) for documentation.
