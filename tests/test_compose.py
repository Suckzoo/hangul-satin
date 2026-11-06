import math

import numpy as np
from shapely.geometry import Polygon
from shapely.ops import unary_union

from hangul_satin.compose import compose_component, compose_glyph
from hangul_satin.outline import GlyphOutline

from .shapes import corner_shape, rect_ring, rounded_ring, stem_with_arch, stem_with_tick, stepped_double_corner, two_stems_two_bars


def rung_dir(stroke):
    a, b = stroke.rungs[len(stroke.rungs) // 2]
    v = np.array(b) - np.array(a)
    return v / np.linalg.norm(v)


def angle_between(u, v):
    return math.degrees(math.acos(min(1.0, abs(float(np.dot(u, v))))))


def all_rungs_parallel(stroke, tol_deg):
    first = rung_dir(stroke)
    for a, b in stroke.rungs:
        v = np.array(b) - np.array(a)
        if angle_between(first, v / np.linalg.norm(v)) > tol_deg:
            return False
    return True


def covered(strokes):
    parts = []
    for s in strokes:
        if s.closed:
            parts.append(Polygon(s.left).buffer(0).symmetric_difference(Polygon(s.right).buffer(0)))
        else:
            parts.append(Polygon(s.left + s.right[::-1]).buffer(0))
    return unary_union(parts)


def uncovered_diameter(shape, strokes):
    from shapely import maximum_inscribed_circle
    rest = shape.difference(covered(strokes))
    pieces = list(rest.geoms) if hasattr(rest, "geoms") else [rest]
    return max([2 * maximum_inscribed_circle(p).length for p in pieces if p.geom_type == "Polygon" and p.area > 1] or [0.0])


def test_pillar_stitches_are_uniform_through_tick():
    strokes = compose_component(stem_with_tick())
    assert all_rungs_parallel(strokes[-1], tol_deg=1)


def test_tick_is_sewn_before_pillar_and_parallel_to_it():
    tick, pillar = compose_component(stem_with_tick())
    assert angle_between(rung_dir(tick), np.array(pillar.axis)) < 2


def test_tick_reaches_its_far_end():
    tick, _ = compose_component(stem_with_tick())
    assert max(p[0] for p in tick.left + tick.right) > 239


def test_tick_does_not_pick_up_slivers_along_the_pillar():
    tick, _ = compose_component(stem_with_tick(proud_side=1.5))
    ys = [p[1] for p in tick.left + tick.right]
    assert max(ys) - min(ys) < 120 + 30


def test_two_stems_two_bars_makes_four_strokes():
    strokes = compose_component(two_stems_two_bars())
    assert len(strokes) == 4 and all(all_rungs_parallel(s, tol_deg=1) for s in strokes)


def test_two_stems_with_tiny_hole_makes_four_strokes():
    assert len(compose_component(two_stems_two_bars(hole=20))) == 4


def test_ring_stays_one_radial_stroke():
    strokes = compose_component(rounded_ring())
    assert len(strokes) == 1 and strokes[0].closed


def test_corner_pieces_sew_with_parallel_stitches():
    strokes = compose_component(corner_shape())
    assert len(strokes) == 2 and all(all_rungs_parallel(s, tol_deg=2) for s in strokes)


def test_square_ring_covers_its_shape():
    assert uncovered_diameter(rect_ring(), compose_component(rect_ring())) <= 17


def test_stepped_corner_leaves_no_large_gap():
    assert uncovered_diameter(stepped_double_corner(), compose_component(stepped_double_corner())) <= 17


def test_curved_shoulder_does_not_become_a_straight_bar():
    shape = stem_with_arch()
    strokes = compose_component(shape)
    assert max(s.width for s in strokes) < 200
    assert uncovered_diameter(shape, strokes) <= 17


def test_compose_glyph_keeps_components_top_to_bottom():
    top, bottom = stem_with_tick(), rect_ring()
    from shapely.affinity import translate
    shape = unary_union([translate(top, 0, 800), bottom])
    strokes = compose_glyph(GlyphOutline(shape, 1000))
    tops = [max(p[1] for p in s.left) for s in strokes]
    assert tops[0] > 700 and tops[-1] < 500


def test_next_stroke_starts_at_the_near_end():
    strokes = compose_component(corner_shape())
    gap = math.dist(strokes[0].left[-1], strokes[1].left[0])
    assert gap < 5
