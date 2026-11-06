"""Quality numbers for one rendered glyph. All lengths are millimeters."""
import math
from dataclasses import dataclass, field

import numpy as np
from shapely import maximum_inscribed_circle
from shapely.geometry import LineString, Point
from shapely.ops import unary_union

THREAD_RADIUS = 0.2
MAX_GAP = 0.5
# 7 mm plus slack: InkStitch can leave a single stitch of about 7.2 mm on a stroke split at 6.5 mm
MAX_STITCH = 7.2
SPACING = 0.4
TILT_MARGIN_DEG = 1.5
PILLAR_INSET = 0.6
MIN_STITCH_FOR_TILT = 1.0
MIN_GAP_AREA = 0.01


@dataclass
class GlyphReport:
    gap_mm: float
    stem_tilt_p95: float | None
    stem_tilt_p95_ok: bool
    max_stitch_mm: float
    long_stitches: int
    reasons: list[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return not self.reasons


def evaluate(shape_mm, stitch_groups: list, pillars: list, size_mm: float) -> GlyphReport:
    """Stitch groups are dicts with el, underlay and pts. Shape, stitches and pillars share mm coordinates."""
    gap = _largest_gap(shape_mm, stitch_groups)
    tilt, tilt_ok = _pillar_tilt(stitch_groups, pillars)
    lengths = _stitch_lengths(stitch_groups)
    longest = float(lengths.max()) if len(lengths) else 0.0
    long_count = int((lengths > MAX_STITCH).sum())
    reasons = []
    if gap > MAX_GAP:
        reasons.append("gap")
    if not tilt_ok:
        reasons.append("tilt")
    if long_count:
        reasons.append("long")
    return GlyphReport(gap, tilt, tilt_ok, longest, long_count, reasons)


def _top_segments(stitch_groups):
    for group in stitch_groups:
        if group["underlay"]:
            continue
        pts = group["pts"]
        if pts and isinstance(pts[0], LineString):
            yield from pts
        else:
            for a, b in zip(pts, pts[1:]):
                yield LineString([a, b])


def _largest_gap(shape, stitch_groups):
    lines = [s for s in _top_segments(stitch_groups) if s.length > 0]
    if not lines:
        return _inscribed_diameter(shape)
    thread = unary_union([line.buffer(THREAD_RADIUS, cap_style="flat") for line in lines])
    return _inscribed_diameter(shape.difference(thread))


def _inscribed_diameter(geometry):
    best = 0.0
    for piece in getattr(geometry, "geoms", [geometry]):
        if piece.geom_type == "Polygon" and piece.area > MIN_GAP_AREA:
            best = max(best, 2 * maximum_inscribed_circle(piece).length)
    return float(best)


def _pillar_tilt(stitch_groups, pillars):
    """Worst pillar's 95th percentile tilt from the pillar normal. Satin zigzag makes atan(spacing/width) unavoidable."""
    worst, ok = None, True
    for pillar in pillars:
        tilts = _tilts_in(stitch_groups, pillar)
        if not tilts:
            continue
        p95 = float(np.percentile(tilts, 95))
        limit = math.degrees(math.atan(SPACING / pillar.width)) + TILT_MARGIN_DEG
        worst = p95 if worst is None else max(worst, p95)
        ok = ok and p95 <= limit
    return (None if worst is None else round(worst, 1)), ok


def _tilts_in(stitch_groups, pillar):
    """Measure the stroke that fills the pillar. Strokes tucked under it are hidden by it."""
    core = pillar.region.buffer(-PILLAR_INSET)
    axis = np.array(pillar.axis)
    counts = {}
    inside = []
    for group in stitch_groups:
        for segment in _top_segments([group]):
            if segment.length >= MIN_STITCH_FOR_TILT and core.contains(Point(segment.interpolate(0.5, normalized=True))):
                inside.append((group["el"], segment))
                counts[group["el"]] = counts.get(group["el"], 0) + 1
    if not counts:
        return []
    own = max(counts, key=counts.get)
    tilts = []
    for element, segment in inside:
        if element != own:
            continue
        (x0, y0), (x1, y1) = segment.coords[0], segment.coords[-1]
        v = np.array([x1 - x0, y1 - y0]) / segment.length
        tilts.append(math.degrees(math.asin(min(1.0, abs(float(v @ axis))))))
    return tilts


def _stitch_lengths(stitch_groups):
    lengths = [segment.length for segment in _top_segments(stitch_groups)]
    return np.array(lengths) if lengths else np.array([0.0])
