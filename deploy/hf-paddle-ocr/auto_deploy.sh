#!/usr/bin/env bash
# Thin wrapper — prefer Python on Windows; this works in Git Bash / WSL / Linux.
#
# Effective Cloud Run flags (from README_DEPLOY.md / auto_deploy.py):
#   --memory 4Gi
#   --timeout 300
#   --min-instances 0
#   --max-instances 3
#   --cpu 1 --port 8080 --allow-unauthenticated
#
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec python3 "${SCRIPT_DIR}/auto_deploy.py" "$@"
