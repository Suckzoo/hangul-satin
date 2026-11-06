from shapely.geometry import box

from hangul_satin.scan_satin import scan_satin


def test_rectangle_rungs_are_perpendicular_to_axis():
    s = scan_satin(box(0, 0, 100, 400), (0, 1))
    assert all(abs(a[1] - b[1]) < 1e-6 for a, b in s.rungs)


def test_rails_keep_their_sides():
    s = scan_satin(box(0, 0, 100, 400), (0, 1))
    assert {round(p[0]) for p in s.left} == {100} or {round(p[0]) for p in s.right} == {100}
    assert {round(p[0]) for p in s.left} != {round(p[0]) for p in s.right}


def test_short_wide_piece_has_three_inner_rungs():
    # height 200, length 60: every rung is longer than the rails
    s = scan_satin(box(0, 0, 60, 200), (1, 0))
    assert len(s.rungs) >= 3
    assert s.rungs[0][0] != s.left[0] and s.rungs[-1][0] != s.left[-1]


def test_inkstitch_reads_rails_of_short_wide_piece(satin_from_stroke):
    satin = satin_from_stroke(scan_satin(box(0, 0, 60, 200), (1, 0)))
    assert satin.rail_indices == [0, 1]


def test_inkstitch_stitches_short_wide_piece_across_full_length(satin_from_stroke):
    satin = satin_from_stroke(scan_satin(box(0, 0, 60, 200), (1, 0)), scale=0.1134)
    groups = satin.plot_points_on_rails(3.0)
    assert len(groups) >= 3
    xs = [p.x for pair in groups for p in pair]
    assert max(xs) - min(xs) > 60 * 0.1134 * 0.9


def test_tiny_region_returns_none():
    assert scan_satin(box(0, 0, 1, 1), (1, 0)) is None
