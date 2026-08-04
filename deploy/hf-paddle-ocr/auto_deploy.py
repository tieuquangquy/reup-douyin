#!/usr/bin/env python3
"""
Auto-deploy PaddleOCR API to Google Cloud Run, then wire Phase 2 OCR_ENDPOINT_URL.

Reads deploy flags from README_DEPLOY.md (same directory), runs:
  gcloud run deploy ... --memory 8Gi --cpu 4 --concurrency 2
  --min-instances 0|1 --max-instances 5 --allow-unauthenticated --port 8080

After success:
  1) Extract service URL (describe --format=value(status.url) + regex fallback)
  2) Upsert repo-root .env: OCR_ENDPOINT_URL=<url>/predict

Usage (from repo root or this folder):
  python auto_deploy.py
  python auto_deploy.py --warm      # batch session: min-instances 1
  python auto_deploy.py --dry-run   # print command + .env update only

Requires: gcloud authenticated + project selected (see README_DEPLOY.md).
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
README_DEPLOY = SCRIPT_DIR / "README_DEPLOY.md"
REPO_ROOT = SCRIPT_DIR.parents[1]  # deploy/hf-paddle-ocr → deploy → repo
ENV_PATH = REPO_ROOT / ".env"
# Keep Local↔Cloud switchable from the same key in all app env files.
ENV_PATHS = (
    ENV_PATH,
    REPO_ROOT / "apps" / "api" / ".env",
    REPO_ROOT / "apps" / "worker" / ".env",
)
OCR_ENV_KEY = "OCR_ENDPOINT_URL"

DEFAULT_SERVICE = "paddle-ocr-vl16"
DEFAULT_REGION = "us-central1"
# Cloud Run env for PaddleOCR-VL-1.6 (must match Dockerfile / README_DEPLOY).
DEFAULT_SET_ENV_VARS = (
    "OCR_PADDLE_ENGINE=vl16,"
    "OCR_PADDLE_NO_FALLBACK=1,"
    "OCR_PADDLE_VL_DEVICE=cpu,"
    "OCR_PADDLE_VL_SKIP_PROBE=1"
)

RUN_APP_URL_RE = re.compile(
    r"https://[a-z0-9][a-z0-9\-]*\.a\.run\.app",
    re.IGNORECASE,
)


def resolve_gcloud() -> str | None:
    """Locate gcloud (.cmd on Windows). CreateProcess cannot launch .cmd without cmd.exe."""
    found = shutil.which("gcloud")
    if found:
        return found
    candidates = [
        Path(os.environ.get("LOCALAPPDATA", ""))
        / "Google"
        / "Cloud SDK"
        / "google-cloud-sdk"
        / "bin"
        / "gcloud.cmd",
        Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"))
        / "Google"
        / "Cloud SDK"
        / "google-cloud-sdk"
        / "bin"
        / "gcloud.cmd",
        Path(os.environ.get("ProgramFiles", r"C:\Program Files"))
        / "Google"
        / "Cloud SDK"
        / "google-cloud-sdk"
        / "bin"
        / "gcloud.cmd",
    ]
    for path in candidates:
        if path.is_file():
            return str(path)
    return None


def run_gcloud(args: list[str], *, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    """Run gcloud safely on Windows (gcloud.cmd via cmd /c) and Unix."""
    gcloud = resolve_gcloud()
    if not gcloud:
        raise FileNotFoundError("gcloud not found on PATH")
    # Replace leading 'gcloud' token with resolved path.
    tail = args[1:] if args and args[0].lower() in {"gcloud", "gcloud.cmd"} else args
    if os.name == "nt":
        # shell=True + quoted path so .cmd works under CreateProcess.
        cmdline = subprocess.list2cmdline([gcloud, *tail])
        return subprocess.run(
            cmdline,
            cwd=str(cwd) if cwd else None,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            shell=True,
        )
    return subprocess.run(
        [gcloud, *tail],
        cwd=str(cwd) if cwd else None,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


def parse_deploy_defaults_from_readme(readme: Path) -> dict[str, str]:
    """Pull service name / region / memory flags from the documented gcloud block."""
    defaults = {
        "service": DEFAULT_SERVICE,
        "region": DEFAULT_REGION,
        "memory": "16Gi",
        "cpu": "4",
        "concurrency": "1",
        "min_instances": "0",
        "max_instances": "1",
        "port": "8080",
        "timeout": "3600",
        "set_env_vars": DEFAULT_SET_ENV_VARS,
    }
    if not readme.is_file():
        return defaults
    text = readme.read_text(encoding="utf-8")
    m = re.search(
        r"gcloud\s+run\s+deploy\s+(\S+)(.*?)(?=\n```|\n## |\Z)",
        text,
        re.DOTALL | re.IGNORECASE,
    )
    if not m:
        return defaults
    defaults["service"] = m.group(1).strip()
    block = m.group(2)
    for key, pattern in (
        ("region", r"--region\s+(\S+)"),
        ("memory", r"--memory\s+(\S+)"),
        ("cpu", r"--cpu\s+(\S+)"),
        ("concurrency", r"--concurrency\s+(\S+)"),
        ("min_instances", r"--min-instances\s+(\S+)"),
        ("max_instances", r"--max-instances\s+(\S+)"),
        ("port", r"--port\s+(\S+)"),
        ("timeout", r"--timeout\s+(\S+)"),
        ("set_env_vars", r"--set-env-vars\s+(\S+)"),
    ):
        hit = re.search(pattern, block)
        if hit:
            defaults[key] = hit.group(1).strip()
    return defaults


def build_deploy_command(cfg: dict[str, str], *, source_dir: Path) -> list[str]:
    set_env = (cfg.get("set_env_vars") or DEFAULT_SET_ENV_VARS).strip()
    return [
        "gcloud",
        "run",
        "deploy",
        cfg["service"],
        "--source",
        str(source_dir),
        "--region",
        cfg["region"],
        "--platform",
        "managed",
        "--memory",
        cfg["memory"],
        "--cpu",
        cfg["cpu"],
        "--concurrency",
        cfg.get("concurrency", "1"),
        "--min-instances",
        cfg["min_instances"],
        "--max-instances",
        cfg["max_instances"],
        "--allow-unauthenticated",
        "--port",
        cfg["port"],
        "--timeout",
        cfg.get("timeout", "900"),
        "--set-env-vars",
        set_env,
        "--quiet",
    ]


def extract_url_from_text(text: str) -> str | None:
    match = RUN_APP_URL_RE.search(text)
    return match.group(0).rstrip("/") if match else None


def describe_service_url(service: str, region: str) -> str | None:
    cmd = [
        "gcloud",
        "run",
        "services",
        "describe",
        service,
        "--region",
        region,
        "--platform",
        "managed",
        "--format=value(status.url)",
    ]
    try:
        proc = run_gcloud(cmd)
    except FileNotFoundError:
        return None
    if proc.returncode != 0:
        return None
    url = (proc.stdout or "").strip().rstrip("/")
    return url or None


def upsert_env_var(env_path: Path, key: str, value: str) -> None:
    line = f"{key}={value}"
    if env_path.is_file():
        existing = env_path.read_text(encoding="utf-8")
        pattern = re.compile(rf"^{re.escape(key)}=.*$", re.MULTILINE)
        if pattern.search(existing):
            updated = pattern.sub(line, existing)
        else:
            sep = "" if existing.endswith("\n") or not existing else "\n"
            updated = existing + sep + line + "\n"
        env_path.write_text(updated, encoding="utf-8")
    else:
        env_path.write_text(line + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Deploy PaddleOCR to Cloud Run and set OCR_ENDPOINT_URL")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print deploy command and sample .env line without calling gcloud",
    )
    parser.add_argument("--service", default=None, help="Override Cloud Run service name")
    parser.add_argument("--region", default=None, help="Override region")
    parser.add_argument(
        "--skip-deploy",
        action="store_true",
        help="Only describe existing service URL and update .env",
    )
    parser.add_argument(
        "--warm",
        action="store_true",
        help="Batch/session profile: --min-instances 1 (avoid cold start between Analyze OCR jobs)",
    )
    parser.add_argument(
        "--concurrency",
        default=None,
        help="Override Cloud Run --concurrency (default from README: 2)",
    )
    parser.add_argument(
        "--min-instances",
        default=None,
        dest="min_instances",
        help="Override --min-instances (default 0; --warm forces 1)",
    )
    args = parser.parse_args(argv)

    cfg = parse_deploy_defaults_from_readme(README_DEPLOY)
    if args.service:
        cfg["service"] = args.service
    if args.region:
        cfg["region"] = args.region
    if args.concurrency:
        cfg["concurrency"] = str(args.concurrency).strip()
    if args.min_instances is not None:
        cfg["min_instances"] = str(args.min_instances).strip()
    if args.warm:
        cfg["min_instances"] = "1"
    # Env overrides (CI / local)
    cfg["service"] = os.environ.get("OCR_CLOUD_RUN_SERVICE", cfg["service"])
    cfg["region"] = os.environ.get("OCR_CLOUD_RUN_REGION", cfg["region"])

    deploy_cmd = build_deploy_command(cfg, source_dir=SCRIPT_DIR)
    print("=== auto_deploy (Cloud Run -> OCR_ENDPOINT_URL) ===")
    print(f"readme:  {README_DEPLOY}")
    print(f"source:  {SCRIPT_DIR}")
    print(f"env:     {ENV_PATH}")
    print(f"command: {' '.join(deploy_cmd)}")
    if cfg.get("min_instances") == "1":
        print(
            "note:    warm/batch profile (min-instances=1). "
            "Redeploy without --warm when the session ends to save idle cost."
        )
    else:
        print(
            "note:    scale-to-zero (min-instances=0). "
            "For Analyze OCR batch sessions use: python auto_deploy.py --warm"
        )

    if args.dry_run:
        sample = f"https://{cfg['service']}-xxxxx-xx.a.run.app/predict"
        print(f"[dry-run] would set {OCR_ENV_KEY}={sample}")
        return 0

    gcloud_bin = resolve_gcloud()
    if not gcloud_bin:
        print("ERROR: gcloud not found on PATH. Install Google Cloud SDK first.", file=sys.stderr)
        return 1
    print(f"gcloud:  {gcloud_bin}")

    combined_output = ""
    if not args.skip_deploy:
        print("\n--- running gcloud run deploy (this may take several minutes) ---\n")
        try:
            proc = run_gcloud(deploy_cmd, cwd=SCRIPT_DIR)
        except FileNotFoundError as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 1
        combined_output = (proc.stdout or "") + "\n" + (proc.stderr or "")
        print(combined_output)
        log_path = SCRIPT_DIR / "auto_deploy.last.log"
        log_path.write_text(combined_output, encoding="utf-8")
        print(f"(deploy log saved to {log_path})")
        if proc.returncode != 0:
            print(f"ERROR: gcloud run deploy failed with exit code {proc.returncode}", file=sys.stderr)
            return proc.returncode

    service_url = describe_service_url(cfg["service"], cfg["region"])
    if not service_url:
        service_url = extract_url_from_text(combined_output)
    if not service_url:
        print(
            "ERROR: could not extract Cloud Run URL. "
            "Check auto_deploy.last.log or run: "
            f"gcloud run services describe {cfg['service']} --region {cfg['region']} --format=value(status.url)",
            file=sys.stderr,
        )
        return 2

    base = service_url.rstrip("/")
    predict_url = base if base.endswith("/predict") else f"{base}/predict"
    for env_path in ENV_PATHS:
        if env_path.is_file() or env_path == ENV_PATH:
            upsert_env_var(env_path, OCR_ENV_KEY, predict_url)
            print(f"OK: wrote {env_path}")
    print(f"\nOK: service URL = {service_url}")
    print(f"OK: {OCR_ENV_KEY}={predict_url}")
    print("\nPhase 2 will call this via os.environ / .env (RestOcrEndpointProvider).")
    print("Restart API/worker after changing OCR_ENDPOINT_URL.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
