"""Shared quality gates for temporal reference-plate selection."""

from __future__ import annotations

import math


MAX_REFERENCE_OUTSIDE_MAD = 24.0
MIN_REFERENCE_INSIDE_MAD = 8.0
MIN_REFERENCE_INSIDE_GAIN = 3.0


def reference_plate_candidate_score(
    *, outside_mad: float, inside_mad: float
) -> float:
    """Prefer a stable scene whose text ROI changes materially."""

    return float(outside_mad) + max(0.0, 20.0 - float(inside_mad)) * 2.0


def is_usable_reference_plate_candidate(
    *,
    outside_mad: float,
    inside_mad: float,
    max_outside_mad: float = MAX_REFERENCE_OUTSIDE_MAD,
    min_inside_mad: float = MIN_REFERENCE_INSIDE_MAD,
    min_inside_gain: float = MIN_REFERENCE_INSIDE_GAIN,
) -> bool:
    """Reject references that still contain text or belong to another scene.

    A clean plate must keep pixels outside the cover ROI stable and provide
    positive evidence that the ROI itself changed more than its surroundings.
    Merely choosing the least-bad candidate can otherwise copy the original
    overlay back into a preflight sample or final render.
    """

    outside = float(outside_mad)
    inside = float(inside_mad)
    return (
        math.isfinite(outside)
        and math.isfinite(inside)
        and outside <= float(max_outside_mad)
        and inside >= float(min_inside_mad)
        and inside - outside >= float(min_inside_gain)
    )
