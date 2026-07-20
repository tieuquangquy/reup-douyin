#!/usr/bin/env bash
# Thin wrapper — prefer Python on Windows; this works in Git Bash / WSL / Linux.
#
# Effective Cloud Run flags (from README_DEPLOY.md / auto_deploy.py):
#   --memory 8Gi --cpu 4 --concurrency 2
#   --timeout 300
#   --min-instances 0   (default / idle)
#   --min-instances 1   (auto_deploy.py --warm — Analyze OCR batch session)
#   --max-instances 5
#   --port 8080 --allow-unauthenticated
#
# Do NOT use 4Gi just to raise max-instances: PaddleOCR OOMs (~4.2–4.5Gi) → HTTP 503.
# Quota asia-southeast1 ~20 vCPU + ~40Gi → max 5 × (4 CPU / 8Gi).

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec python3 "${SCRIPT_DIR}/auto_deploy.py" "$@"
