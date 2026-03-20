#!/usr/bin/env bash
set -euo pipefail

# Keep test runs on the same local nanobot instance as manual CLI runs.
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/_dev_env.sh"

exec uv run --with pytest --with pytest-asyncio pytest "$@"
