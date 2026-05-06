"""Pre-publish gates: enforce per-platform daily caps and min intervals."""
from src.publish.guard import GuardResult, can_publish

__all__ = ["GuardResult", "can_publish"]
