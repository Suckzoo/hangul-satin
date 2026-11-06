"""Satin from a region and an axis: slice across the axis, so every stitch runs perpendicular to it."""
import math

import numpy as np
from shapely.geometry import LineString, Polygon

from .types import SatinStroke

MIN_SLICE = 0.5
START_OFFSET = 0.3
MIN_RUNGS = 3
MIN_SPAN = 5.0
MIN_SLICES = 8
WIDTH_CHANGE = 0.04


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
    if end - start < MIN_SPAN:
        return None
    # a short piece gets finer slices, so its rungs can sit inside the rail span
    step = min(step, (end - start) / MIN_SLICES)
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
    """One rung per spacing, plus more where the width changes, such as a rounded end.

    Rails are paired by proportion between rungs, so a stretch with changing width and no rung slants its
    stitches. The first and last rung sit one slice in: a rung at a rail end can miss the rail after rounding.
    InkStitch then falls back to the longest paths as rails (SatinColumn.rail_indices), and in a short wide
    piece the longest paths are rungs. Three rungs are the minimum for rail_indices to work.
    """
    last = len(left) - 1
    first, final = 1, last - 1
    widths = [math.dist(a, b) for a, b in zip(left, right)]
    picks = [first]
    for i in range(first + 1, final):
        far = (i - picks[-1]) * step >= rung_step
        changed = abs(widths[i] - widths[picks[-1]]) > WIDTH_CHANGE * max(widths[picks[-1]], 1.0)
        if far or changed:
            picks.append(i)
    if final > picks[-1]:
        picks.append(final)
    if len(picks) < MIN_RUNGS:
        picks = sorted({int(round(i)) for i in np.linspace(first, final, MIN_RUNGS)})
    return [(left[i], right[i]) for i in picks]
