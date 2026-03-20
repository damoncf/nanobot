#!/usr/bin/env bash
set -euo pipefail

# Load project-local nanobot config before forwarding to the CLI.
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/_dev_env.sh"

exec uv run nanobot "$@"
