import math

import pytest
from shapely.affinity import scale as affine_scale
from shapely.geometry import Point, box
from shapely.ops import unary_union

from hangul_satin.compose import compose_component, compose_glyph, compose_part
from hangul_satin.inkstitch_bridge import satin_attributes
from hangul_satin.outline import GlyphOutline

from .shapes import fat_s_shape, wide_bar
from .test_compose import uncovered_diameter

NEEDLE_LIMIT = 12


def top_needle_density(groups):
    cells = {}
    for group in groups:
        if not group["underlay"]:
            for x, y in group["pts"]:
                cell = (int(x // 1), int(y // 1))
                cells[cell] = cells.get(cell, 0) + 1
    return max(cells.values())


def test_no_needle_pileup_at_inner_corner(inkstitch):
    from hangul_satin.inkstitch_bridge import stitch_strokes
    assert top_needle_density(stitch_strokes(compose_component(fat_s_shape()), 30)) <= NEEDLE_LIMIT


def test_wide_stroke_sets_stitch_split():
    stroke = compose_component(wide_bar())[0]
    assert satin_attributes(stroke, 30)["max_stitch_length_mm"] == "6.5"


def test_narrow_stroke_has_no_stitch_split():
    stroke = compose_component(box(0, 0, 800, 100))[0]
    assert "max_stitch_length_mm" not in satin_attributes(stroke, 30)


def test_split_setting_shortens_real_stitches(inkstitch):
    from hangul_satin.inkstitch_bridge import stitch_strokes
    stroke = compose_component(wide_bar())[0]
    groups = stitch_strokes([stroke], 30)
    top = [g for g in groups if not g["underlay"]]
    longest = max(math.dist(a, b) for g in top for a, b in zip(g["pts"], g["pts"][1:]))
    assert longest <= 7.0


def test_dot_without_medial_axis_is_still_sewn():
    # the dot of an i: round, so every medial ridge counts as a spur
    dot = Point(0, 0).buffer(60, 32)
    strokes = compose_component(dot)
    assert strokes and uncovered_diameter(dot, strokes) <= 17


def test_oval_dot_sews_across_its_short_side():
    oval = affine_scale(Point(0, 0).buffer(60, 32), 2.0, 1.0)
    stroke = compose_component(oval)[0]
    assert abs(stroke.axis[0]) > 0.9


def test_gap_far_from_any_straight_stroke_gets_its_own_stroke():
    ring = Point(0, 0).buffer(260, 64).difference(Point(0, 0).buffer(120, 64))
    blob = Point(0, 300).buffer(90, 32)
    shape = unary_union([ring, blob])
    assert uncovered_diameter(shape, compose_part(shape)) <= 17


def test_glyph_with_only_dot_is_composed():
    assert compose_glyph(GlyphOutline(Point(0, 0).buffer(60, 32), 500))


@pytest.mark.parametrize("size,expected", [(30, "6.5"), (15, None)])
def test_stitch_split_depends_on_render_size(size, expected):
    stroke = compose_component(wide_bar())[0]
    assert satin_attributes(stroke, size).get("max_stitch_length_mm") == expected


def test_every_medial_piece_has_three_rungs():
    from hangul_satin.medial import medial_strokes
    assert all(len(s.rungs) >= 3 for s in medial_strokes(fat_s_shape()))


def test_wide_gap_beside_a_narrow_stroke_is_not_dropped():
    from hangul_satin.compose import _fill_gaps
    from hangul_satin.scan_satin import scan_satin
    bar, blob = box(0, 0, 100, 600), box(100, 200, 500, 500)
    shape = unary_union([bar, blob])
    strokes = _fill_gaps([scan_satin(bar, (0, 1))], shape)
    assert uncovered_diameter(shape, strokes) <= 17


def test_split_looks_at_the_widest_slice_not_only_the_rungs():
    from hangul_satin.types import SatinStroke
    left = [(0.0, float(y)) for y in range(0, 100, 10)]
    right = [(100.0, float(y)) for y in range(0, 90, 10)] + [(300.0, 90.0)]
    stroke = SatinStroke(left=left, right=right, rungs=[(left[i], right[i]) for i in (1, 4, 7)], width=100.0)
    assert "max_stitch_length_mm" in satin_attributes(stroke, 30)


def test_split_follows_rung_sections_like_inkstitch():
    from hangul_satin.types import SatinStroke
    # one short rail stretch pairs with a long diagonal stretch, so one section has long stitches
    left = [(0.0, 0.0), (0.0, 100.0), (0.0, 120.0)]
    right = [(100.0, 0.0), (100.0, 100.0), (240.0, 120.0)]
    stroke = SatinStroke(left=left, right=right, rungs=[((0.0, 50.0), (100.0, 50.0)), ((0.0, 100.0), (100.0, 100.0))], width=100.0)
    assert "max_stitch_length_mm" in satin_attributes(stroke, 30)
