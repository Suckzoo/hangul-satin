"""Satin from a region and an axis: slice across the axis, so every stitch runs perpendicular to it."""
import numpy as np
from shapely.geometry import LineString, Polygon

from .types import SatinStroke

MIN_SLICE = 0.5
START_OFFSET = 0.3
MIN_RUNGS = 3
RUNG_RANGE = (0.1, 0.9)


def scan_satin(region: Polygon, axis: tuple[float, float], step: float = 5.0, rung_step: float = 35.0) -> SatinStroke | None:
    u = np.asarray(axis, dtype=float)
    u = u / np.linalg.norm(u)
    n = np.array([-u[1], u[0]])
    coords = np.array(region.exterior.coords)
    along, across = coords @ u, coords @ n
    low, high = across.min() - 5, across.max() + 5

    left, right = [], []
    # the last slice sits at the far end, otherwise the piece stops up to one step short
    start, end = along.min() + START_OFFSET, along.max() - START_OFFSET
    for t in np.append(np.arange(start, end, step), end):
        pair = _slice(region, u, n, t, low, high)
        if pair:
            left.append(pair[0])
            right.append(pair[1])
    if len(left) < 2:
        return None

    widths = [np.hypot(a[0] - b[0], a[1] - b[1]) for a, b in zip(left, right)]
    return SatinStroke(left=left, right=right, rungs=_rungs(left, right, step, rung_step), width=float(np.median(widths)),
                       axis=(float(u[0]), float(u[1])), region=region)


def _slice(region, u, n, t, low, high):
    cut = LineString([u * t + n * low, u * t + n * high]).intersection(region)
    if cut.is_empty:
        return None
    seg = max(cut.geoms, key=lambda g: g.length) if hasattr(cut, "geoms") else cut
    if seg.geom_type != "LineString" or seg.length < MIN_SLICE:
        return None
    a, b = np.array(seg.coords[0]), np.array(seg.coords[-1])
    if a @ n > b @ n:
        a, b = b, a
    return (float(a[0]), float(a[1])), (float(b[0]), float(b[1]))


def _rungs(left, right, step, rung_step):
    """Rungs stay inside the rail span and number at least three.

    A rung at a rail end can miss the rail after rounding. InkStitch then falls back to the longest
    paths as rails (SatinColumn.rail_indices), and in a short wide piece the longest paths are rungs.
    """
    last = len(left) - 1
    count = min(len(left), max(MIN_RUNGS, int(last * step / rung_step)))
    picks = sorted({int(round(i)) for i in np.linspace(RUNG_RANGE[0] * last, RUNG_RANGE[1] * last, count)})
    return [(left[i], right[i]) for i in picks]
