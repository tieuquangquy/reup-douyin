from pathlib import Path
import sys


def ensure_api_src_on_path() -> None:
    repo_root = Path(__file__).resolve().parents[3]
    api_root = repo_root / "apps" / "api"
    if str(api_root) not in sys.path:
        sys.path.insert(0, str(api_root))

