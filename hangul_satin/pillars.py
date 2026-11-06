"""Find pillars: straight strokes that another stroke branches from.

A pillar is a strip between two facing straight sides. At least one side is cut by a real branch and
continues on the same line after it. A curved ring has only short near-straight runs, a square ring has
no cut side, and a corner has no continuation, so none of them is a pillar.
"""
import math
from dataclasses import dataclass

import numpy as np
from shapely.geometry import MultiPolygon, Point, Polygon

SIMPLIFY = 1.5
MIN_EDGE = 18.0
MAX_TILT_DEG = 15.0
COLLINEAR = 8.0
MIN_OVERLAP = 30.0
MIN_WIDTH = 15.0
MIN_ASPECT = 1.3
LONG_SIDE_SHARE = 0.7
SHORT_SIDE_SHARE = 0.2
LONGEST_EDGE_SHARE = 0.6
MIN_GAP_PER_WIDTH = 0.4
MIN_INSIDE = 0.92
REGION_GROW = 0.5


@dataclass
class Pillar:
    orientation: str
    width: float
    axis: tuple[float, float]
    region: Polygon


def find_pillars(poly: Polygon) -> list[Pillar]:
    sides = _group_collinear(_straight_edges(poly))
    vertical = _pair_sides(poly, sides, "V")
    pairs = vertical or _pair_sides(poly, sides, "H")
    return [_make_pillar(poly, *pair) for pair in pairs]


def _straight_edges(poly):
    limit = math.sin(math.radians(MAX_TILT_DEG))
    edges = []
    for ring in [poly.exterior, *poly.interiors]:
        coords = list(ring.simplify(SIMPLIFY).coords)
        for p, q in zip(coords, coords[1:]):
            edge = _classify_edge(poly, np.array(p), np.array(q), limit)
            if edge:
                edges.append(edge)
    return edges


def _classify_edge(poly, p, q, limit):
    v = q - p
    length = float(np.linalg.norm(v))
    if length < MIN_EDGE:
        return None
    if abs(v[0]) / length <= limit:
        orientation, along, across = "V", 1, 0
    elif abs(v[1]) / length <= limit:
        orientation, along, across = "H", 0, 1
    else:
        return None
    normal = np.array([-v[1], v[0]]) / length
    mid = (p + q) / 2
    inward = normal if poly.contains(Point(*(mid + normal * 2))) else -normal
    a, b = (p, q) if p[along] < q[along] else (q, p)
    return dict(orientation=orientation, side="lo" if inward[across] > 0 else "hi", a0=a[along], a1=b[along], c0=a[across], c1=b[across])


def _group_collinear(edges):
    groups = []
    for edge in sorted(edges, key=lambda e: e["a0"] - e["a1"]):
        group = next((g for g in groups if _fits(g, edge)), None)
        if group:
            group["edges"].append(edge)
        else:
            slope = (edge["c1"] - edge["c0"]) / (edge["a1"] - edge["a0"] + 1e-9)
            groups.append(dict(orientation=edge["orientation"], side=edge["side"], m=slope, b=edge["c0"] - slope * edge["a0"], edges=[edge]))
    for group in groups:
        _fit_line(group)
    return groups


def _fits(group, edge):
    if group["orientation"] != edge["orientation"] or group["side"] != edge["side"]:
        return False
    mid = (edge["a0"] + edge["a1"]) / 2
    if abs(group["b"] + group["m"] * mid - (edge["c0"] + edge["c1"]) / 2) > COLLINEAR:
        return False
    return not any(min(edge["a1"], e["a1"]) - max(edge["a0"], e["a0"]) > 5 for e in group["edges"])


def _fit_line(group):
    along = [x for e in group["edges"] for x in (e["a0"], e["a1"])]
    across = [x for e in group["edges"] for x in (e["c0"], e["c1"])]
    if len(group["edges"]) > 1:
        group["m"], group["b"] = (float(v) for v in np.polyfit(along, across, 1))
    group["a0"], group["a1"] = min(along), max(along)


def _largest_gap(group):
    edges = sorted(group["edges"], key=lambda e: e["a0"])
    return max([b["a0"] - a["a1"] for a, b in zip(edges, edges[1:])] or [0.0])


def _is_pillar(poly, lo, hi, orientation):
    """Return the width when the two sides bound a pillar, otherwise None."""
    a0, a1 = max(lo["a0"], hi["a0"]), min(lo["a1"], hi["a1"])
    if a1 - a0 < MIN_OVERLAP:
        return None
    mid = (a0 + a1) / 2
    width = (hi["b"] + hi["m"] * mid) - (lo["b"] + lo["m"] * mid)
    if width <= MIN_WIDTH:
        return None
    span = max(lo["a1"], hi["a1"]) - min(lo["a0"], hi["a0"])
    if span / width < MIN_ASPECT or not _side_shares_ok(lo, hi, span):
        return None
    if max(_largest_gap(lo), _largest_gap(hi)) < MIN_GAP_PER_WIDTH * width:
        return None
    strip = _strip(lo, hi, a0, a1, orientation)
    if strip.is_empty or strip.intersection(poly).area / strip.area < MIN_INSIDE:
        return None
    return width


def _side_shares_ok(lo, hi, span):
    shares = sorted(sum(e["a1"] - e["a0"] for e in g["edges"]) / span for g in (lo, hi))
    longest = max(e["a1"] - e["a0"] for g in (lo, hi) for e in g["edges"])
    return shares[1] >= LONG_SIDE_SHARE and shares[0] >= SHORT_SIDE_SHARE and longest >= LONGEST_EDGE_SHARE * span


def _pair_sides(poly, sides, orientation):
    los = [g for g in sides if g["orientation"] == orientation and g["side"] == "lo"]
    his = [g for g in sides if g["orientation"] == orientation and g["side"] == "hi"]
    candidates = []
    for lo in los:
        for hi in his:
            if len(lo["edges"]) < 2 and len(hi["edges"]) < 2:
                continue
            width = _is_pillar(poly, lo, hi, orientation)
            if width:
                candidates.append((width, id(lo), id(hi), lo, hi))
    used, pairs = set(), []
    for width, lo_id, hi_id, lo, hi in sorted(candidates, key=lambda c: c[0]):
        if lo_id not in used and hi_id not in used:
            used.update((lo_id, hi_id))
            pairs.append((lo, hi, width, orientation))
    return pairs


def _strip(lo, hi, a0, a1, orientation, grow=0.0):
    at = lambda g, a: g["b"] + g["m"] * a  # noqa: E731
    points = [(a0, at(lo, a0) - grow), (a1, at(lo, a1) - grow), (a1, at(hi, a1) + grow), (a0, at(hi, a0) + grow)]
    if orientation == "V":
        points = [(c, a) for a, c in points]
    return Polygon(points).buffer(0)


def _make_pillar(poly, lo, hi, width, orientation):
    x0, y0, x1, y1 = poly.bounds
    a0, a1 = (y0 - 50, y1 + 50) if orientation == "V" else (x0 - 50, x1 + 50)
    region = _strip(lo, hi, a0, a1, orientation, grow=REGION_GROW).intersection(poly)
    if isinstance(region, MultiPolygon):
        region = max(region.geoms, key=lambda g: g.area)
    slope = (lo["m"] + hi["m"]) / 2
    axis = np.array([slope, 1.0]) if orientation == "V" else np.array([1.0, slope])
    axis = axis / np.linalg.norm(axis)
    return Pillar(orientation, float(width), (float(axis[0]), float(axis[1])), region)
