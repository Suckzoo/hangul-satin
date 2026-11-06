"""Build the strokes of one glyph: pillars first, then what remains, then any gap. Sort them for sewing."""
import math

import numpy as np
from shapely.affinity import translate
from shapely.geometry import LineString, MultiPolygon, Polygon
from shapely.ops import unary_union

from .medial import medial_strokes
from .outline import GlyphOutline
from .pillars import find_pillars
from .scan_satin import scan_satin
from .types import SatinStroke

OVERLAP = 12.0
OPEN = 4.0
MIN_PART_AREA = 300.0
MIN_GAP_AREA = 100.0
TOUCH = 1.0
RESCAN_WIDTH = 1.35
MERGE_WIDTH = 1.2
BAR_SLICES = 12
GAP_ID = -1000


def compose_glyph(outline: GlyphOutline) -> list[SatinStroke]:
    shape = outline.shape
    parts = list(shape.geoms) if isinstance(shape, MultiPolygon) else [shape]
    strokes, position = [], None
    for part in sorted(parts, key=lambda p: (-p.bounds[3], p.bounds[0])):
        ordered = _order(compose_part(part), position)
        if ordered:
            strokes.extend(ordered)
            position = ordered[-1].left[-1]
    return strokes


def compose_component(poly: Polygon) -> list[SatinStroke]:
    return _order(compose_part(poly), None)


def compose_part(poly: Polygon) -> list[SatinStroke]:
    pillars = find_pillars(poly)
    strokes = _with_pillars(poly, pillars) if pillars else _straighten(medial_strokes(poly))
    if not strokes:
        # a dot: every medial ridge counts as a spur, so the whole part is one piece
        whole = _own_axis_stroke(poly)
        return [whole] if whole else []
    return _fill_gaps(strokes, poly)


def _with_pillars(poly, pillars):
    regions = [p.region for p in pillars]
    strokes = []
    for part in _opened(poly.difference(unary_union([r.buffer(0.1) for r in regions]))):
        if part.area >= MIN_PART_AREA:
            strokes.extend(_residual_strokes(poly, part, pillars))
    for index, pillar in enumerate(pillars):
        stroke = scan_satin(pillar.region, pillar.axis)
        if stroke:
            stroke.over = {-1 - index}
            strokes.append(stroke)
    return strokes


def _opened(geometry):
    """Remove slivers: a thin strip beside a pillar must not join the piece next to it."""
    opened = geometry.buffer(-OPEN).buffer(OPEN)
    return [g for g in getattr(opened, "geoms", [opened]) if g.geom_type == "Polygon" and not g.is_empty]


def _residual_strokes(poly, part, pillars):
    near = min(range(len(pillars)), key=lambda i: pillars[i].region.distance(part))
    if pillars[near].region.distance(part) > TOUCH:
        return _straighten(medial_strokes(part))
    ax, ay = pillars[near].axis
    axis = np.array([-ay, ax])
    if _is_bar(part, axis):
        grown = _largest(_grow_along(part, axis, OVERLAP).intersection(poly))
        stroke = scan_satin(grown, axis)
        if stroke:
            # the piece grows both ways, so it tucks under every pillar it reaches
            stroke.under = {-1 - i for i, p in enumerate(pillars) if p.region.intersects(grown)}
            return [stroke]
    strokes = _straighten(medial_strokes(part))
    for stroke in strokes:
        stroke.under = stroke.under | {-1 - near}
    return strokes


def _is_bar(part, axis):
    """A bar has one solid slice at every position across the axis, and they all have about the same width."""
    n = np.array([-axis[1], axis[0]])
    coords = np.array(part.exterior.coords)
    along, across = coords @ axis, coords @ n
    widths = []
    for t in np.linspace(along.min() + 1, along.max() - 1, BAR_SLICES):
        cut = LineString([axis * t + n * (across.min() - 1), axis * t + n * (across.max() + 1)]).intersection(part)
        if hasattr(cut, "geoms"):
            return False
        widths.append(cut.length)
    # a rounded end narrows a bar only at the tip, so compare the middle of the bar
    middle = widths[2:-2]
    return max(middle) <= RESCAN_WIDTH * min(middle)


def _grow_along(part, axis, distance):
    """Extend along the sewing axis only, so a piece tucks under its pillar without taking in slivers."""
    moved = [part, translate(part, *(axis * distance)), translate(part, *(-axis * distance))]
    return unary_union(moved).convex_hull.intersection(part.buffer(distance, join_style=2))


def _largest(geometry):
    return max(geometry.geoms, key=lambda g: g.area) if hasattr(geometry, "geoms") else geometry


def _scan_width(stroke):
    return max(math.dist(a, b) for a, b in zip(stroke.left, stroke.right))


def _straighten(strokes):
    """Straight pieces get parallel stitches, which also removes pile-ups at inner corners. Curves stay radial."""
    out = []
    for stroke in strokes:
        rescanned = scan_satin(stroke.region, stroke.axis) if stroke.axis and stroke.region is not None else None
        if rescanned and _scan_width(rescanned) <= RESCAN_WIDTH * stroke.width:
            rescanned.under, rescanned.over = stroke.under, stroke.over
            out.append(rescanned)
        else:
            out.append(stroke)
    return out


def _region_of(stroke):
    if stroke.region is not None:
        return stroke.region
    if stroke.closed:
        return Polygon(stroke.left).buffer(0).symmetric_difference(Polygon(stroke.right).buffer(0))
    return Polygon(stroke.left + stroke.right[::-1]).buffer(0)


def _fill_gaps(strokes, poly):
    """A gap joins a neighbouring straight stroke when that keeps its width. Otherwise it is a patch sewn under it."""
    if not strokes:
        return strokes
    regions = [_region_of(s) for s in strokes]
    rest = poly.difference(unary_union([r.buffer(0.5) for r in regions]))
    patches = []
    for gap in _opened(rest):
        if gap.area < MIN_GAP_AREA:
            continue
        host = _gap_host(strokes, regions, gap)
        if host is None:
            patch = _own_axis_stroke(gap)
            patches += [patch] if patch else []
            continue
        patch = _absorb(strokes, regions, host, gap, poly)
        if patch:
            patch.under = {GAP_ID - host}
            strokes[host].over = strokes[host].over | {GAP_ID - host}
            patches.append(patch)
    return patches + strokes


def _own_axis_stroke(region):
    """Sew a stand-alone piece across its short side."""
    corners = list(region.minimum_rotated_rectangle.exterior.coords)
    sides = [np.subtract(corners[i + 1], corners[i]) for i in (0, 1)]
    return scan_satin(region, tuple(max(sides, key=np.linalg.norm)))


def _gap_host(strokes, regions, gap):
    candidates = [i for i, s in enumerate(strokes) if s.axis and regions[i].distance(gap) < 2]
    if not candidates:
        return None
    return max(candidates, key=lambda i: regions[i].buffer(1).intersection(gap.boundary).length)


def _absorb(strokes, regions, host, gap, poly):
    """Merge the gap into the host and return None, or return a separate patch."""
    stroke = strokes[host]
    grown = _largest(gap.buffer(OVERLAP, join_style=2).intersection(poly))
    merged = unary_union([regions[host], grown])
    if merged.geom_type == "Polygon" and not merged.interiors:
        rescanned = scan_satin(merged, stroke.axis)
        if rescanned and _scan_width(rescanned) <= MERGE_WIDTH * _scan_width(stroke):
            rescanned.under, rescanned.over = stroke.under, stroke.over
            strokes[host], regions[host] = rescanned, merged
            return None
    patch = scan_satin(grown, stroke.axis)
    if patch and _scan_width(patch) <= MERGE_WIDTH * stroke.width:
        return patch
    # too wide to follow the host, but it must still be sewn
    return _own_axis_stroke(grown)


def _order(strokes, position):
    """A stroke that ends at a junction goes first, and the stroke that crosses there goes on top."""
    remaining = list(strokes)
    out = []
    while remaining:
        ready = [s for s in remaining if not any(_must_precede(o, s) for o in remaining if o is not s)] or remaining
        chosen = min(ready, key=lambda s: _distance_to(s, position))
        remaining.remove(chosen)
        if position is not None and not chosen.closed and math.dist(position, chosen.left[-1]) < math.dist(position, chosen.left[0]):
            chosen = _reversed(chosen)
        out.append(chosen)
        position = chosen.left[-1]
    return out


def _must_precede(first, second):
    return bool(first.under & second.over)


def _distance_to(stroke, position):
    if position is None:
        return 0.0
    return min(math.dist(position, stroke.left[0]), math.dist(position, stroke.left[-1]))


def _reversed(stroke):
    stroke.left, stroke.right = stroke.left[::-1], stroke.right[::-1]
    stroke.rungs = stroke.rungs[::-1]
    return stroke
