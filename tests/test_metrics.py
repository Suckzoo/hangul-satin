import numpy as np
from shapely.geometry import Polygon, box

from hangul_satin.metrics import evaluate
from hangul_satin.pillars import Pillar


def zigzag(x0, x1, y0, y1, spacing=0.4):
    pts, y, side = [], y0, 0
    while y <= y1:
        pts.append((x0 if side == 0 else x1, float(y)))
        y += spacing
        side = 1 - side
    return dict(el=0, underlay=False, pts=pts)


def test_gap_detects_hole_that_coverage_percent_misses():
    shape = box(0, 0, 20, 20)
    # stitches cover the square except one small triangle, so coverage stays near 99%
    covered = zigzag(0, 20, 0, 20)
    hole = Polygon([(9, 9), (11, 9), (10, 11)])
    groups = [dict(covered, pts=_outside(covered["pts"], hole))]
    report = evaluate(shape, groups, [], 30)
    assert report.gap_mm > 0.5 and not report.passed and "gap" in report.reasons


def _outside(points, hole):
    """Pull stitches that cross the hole back to its edge by splitting them around it."""
    from shapely.geometry import LineString
    out = []
    for a, b in zip(points, points[1:]):
        for piece in getattr(LineString([a, b]).difference(hole.buffer(0.2)), "geoms", [LineString([a, b]).difference(hole.buffer(0.2))]):
            out.append(piece)
    return out


def test_uniform_pillar_passes_tilt():
    shape = box(0, 0, 4.2, 30)
    pillar = Pillar("V", 4.2, (0.0, 1.0), shape)
    report = evaluate(shape, [zigzag(0, 4.2, 0, 30)], [pillar], 30)
    assert report.stem_tilt_p95 <= 6.5 and report.stem_tilt_p95_ok and report.passed


def test_slanted_stitches_fail_tilt():
    shape = box(0, 0, 4.2, 30)
    pillar = Pillar("V", 4.2, (0.0, 1.0), shape)
    pts = []
    for y in np.arange(1.0, 27.0, 0.4):
        pts += [(0.0, float(y)), (4.2, float(y) + 2.0)]
    report = evaluate(shape, [dict(el=0, underlay=False, pts=pts)], [pillar], 30)
    assert not report.stem_tilt_p95_ok and "tilt" in report.reasons


def test_glyph_without_pillar_fails_only_on_gap():
    shape = box(0, 0, 6, 20)
    report = evaluate(shape, [zigzag(0, 6, 0, 5)], [], 30)
    assert report.stem_tilt_p95 is None and report.reasons == ["gap"]


def test_long_stitches_are_reported():
    shape = box(0, 0, 9, 20)
    report = evaluate(shape, [zigzag(0, 9, 0, 20)], [], 30)
    assert report.long_stitches > 0 and report.max_stitch_mm > 7 and "long" in report.reasons


def test_no_stitches_fail():
    report = evaluate(box(0, 0, 5, 5), [], [], 30)
    assert not report.passed and "gap" in report.reasons


def test_tilt_ignores_a_stroke_sewn_under_the_pillar():
    shape = box(0, 0, 4.2, 30)
    pillar = Pillar("V", 4.2, (0.0, 1.0), shape)
    under = dict(el=0, underlay=False, pts=[(2.0, 10.0), (2.0, 14.0), (2.1, 10.0), (2.1, 14.0)])
    top = dict(zigzag(0, 4.2, 0, 30), el=1)
    report = evaluate(shape, [under, top], [pillar], 30)
    assert report.stem_tilt_p95_ok
