try:
    from ..api_path import ensure_api_src_on_path
except ImportError:  # Allows `python src/main.py` from apps/worker during local dev.
    from api_path import ensure_api_src_on_path

ensure_api_src_on_path()

from src.services.job_runner import PlaceholderStepHandler, StepHandlerRegistry


def build_mock_handler_registry() -> StepHandlerRegistry:
    return StepHandlerRegistry(default_handler=PlaceholderStepHandler())
