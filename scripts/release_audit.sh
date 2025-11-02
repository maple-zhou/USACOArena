#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

cd "${PROJECT_ROOT}"

if command -v uv >/dev/null 2>&1; then
  uv run python -m usacoarena.tools.release_audit "$@"
else
  python3 -m usacoarena.tools.release_audit "$@"
fi
