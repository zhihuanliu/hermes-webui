#!/usr/bin/env bash
set -Eeuo pipefail

usage() {
  cat <<'EOF'
Usage: bash deploy.sh [options]

This script deploys only Hermes WebUI. Hermes Agent/Gateway, EID frontend, and
other backend services are expected to be deployed separately on the same host
and connected to the same Docker network.

Options:
  --image-tar PATH       Image tar produced on Windows. Default: hermes-webui-eid.tar
  --env-file PATH        Env file. Default: deploy.env
  --compose-file PATH    Compose file. Default: docker-compose.yml
  --network NAME         Docker network. Default: eid-2-net
  --no-load              Skip docker load.
  --help                 Show this help.
EOF
}

image_tar="hermes-webui-eid.tar"
env_file="deploy.env"
compose_file="docker-compose.yml"
network_name="eid-2-net"
load_image=1

while [ "$#" -gt 0 ]; do
  case "$1" in
    --image-tar)
      image_tar="${2:?--image-tar requires a value}"
      shift 2
      ;;
    --env-file)
      env_file="${2:?--env-file requires a value}"
      shift 2
      ;;
    --compose-file)
      compose_file="${2:?--compose-file requires a value}"
      shift 2
      ;;
    --network)
      network_name="${2:?--network requires a value}"
      shift 2
      ;;
    --no-load)
      load_image=0
      shift
      ;;
    --help|-h)
      usage
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

if ! command -v docker >/dev/null 2>&1; then
  echo "Docker is required on the deployment host." >&2
  exit 1
fi

if ! docker compose version >/dev/null 2>&1; then
  echo "Docker Compose v2 is required: docker compose ..." >&2
  exit 1
fi

if [ ! -f "$compose_file" ]; then
  echo "Compose file not found: $compose_file" >&2
  exit 1
fi

if [ ! -f "$env_file" ]; then
  if [ -f "deploy.env.example" ]; then
    cp "deploy.env.example" "$env_file"
    echo "Created $env_file from deploy.env.example"
    echo "Edit $env_file before production use: set EID origin and Gateway API key."
  elif [ -f ".env.eid-webui.deploy.example" ]; then
    cp ".env.eid-webui.deploy.example" "$env_file"
    echo "Created $env_file from .env.eid-webui.deploy.example"
    echo "Edit $env_file before production use: set EID origin and Gateway API key."
  else
    echo "Env file not found: $env_file" >&2
    exit 1
  fi
fi

if ! docker network inspect "$network_name" >/dev/null 2>&1; then
  docker network create "$network_name" >/dev/null
  echo "Created Docker network: $network_name"
fi

if [ "$load_image" -eq 1 ]; then
  if [ ! -f "$image_tar" ]; then
    echo "Image tar not found: $image_tar" >&2
    exit 1
  fi
  echo "Loading image: $image_tar"
  docker load -i "$image_tar"
fi

workspace_path="$(grep -E '^HERMES_WORKSPACE=' "$env_file" | tail -n 1 | cut -d= -f2- || true)"
if [ -n "$workspace_path" ]; then
  mkdir -p "$workspace_path"
fi

echo "Stopping existing Hermes WebUI containers (if any)..."
EID_WEBUI_ENV_FILE="$env_file" \
EID_DOCKER_NETWORK="$network_name" \
docker compose --env-file "$env_file" -f "$compose_file" down --remove-orphans

echo "Starting Hermes WebUI..."
EID_WEBUI_ENV_FILE="$env_file" \
EID_DOCKER_NETWORK="$network_name" \
docker compose --env-file "$env_file" -f "$compose_file" up -d --remove-orphans

echo ""
EID_WEBUI_ENV_FILE="$env_file" \
EID_DOCKER_NETWORK="$network_name" \
docker compose --env-file "$env_file" -f "$compose_file" ps

webui_port="$(grep -E '^HERMES_WEBUI_HOST_PORT=' "$env_file" | tail -n 1 | cut -d= -f2- || true)"
webui_port="${webui_port:-8787}"

if command -v curl >/dev/null 2>&1; then
  echo ""
  echo "Checking WebUI health: http://127.0.0.1:${webui_port}/health"
  curl -fsS "http://127.0.0.1:${webui_port}/health" >/dev/null \
    && echo "WebUI health check passed." \
    || echo "WebUI health check did not pass yet. Check container logs."
fi

echo ""
echo "Done."
