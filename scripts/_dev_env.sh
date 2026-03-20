#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="$ROOT_DIR/.env"

if [[ -f "$ENV_FILE" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "$ENV_FILE"
  set +a
fi

if [[ -n "${NANOBOT_CONFIG:-}" && "${NANOBOT_CONFIG}" != /* ]]; then
  export NANOBOT_CONFIG="$ROOT_DIR/$NANOBOT_CONFIG"
fi

if [[ -n "${NANOBOT_HOME:-}" && "${NANOBOT_HOME}" != /* ]]; then
  export NANOBOT_HOME="$ROOT_DIR/$NANOBOT_HOME"
fi
