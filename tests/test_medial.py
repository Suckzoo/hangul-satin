import math

from hangul_satin.medial import medial_strokes

from .shapes import corner_shape, rect_ring, rounded_ring


def rung_points_to_center(rung, tol_deg, center=(0.0, 0.0)):
    (ax, ay), (bx, by) = rung
    mx, my = (ax + bx) / 2, (ay + by) / 2
    rung_angle = math.atan2(by - ay, bx - ax)
    radial = math.atan2(my - center[1], mx - center[0])
    diff = abs((rung_angle - radial + math.pi / 2) % math.pi - math.pi / 2)
    return math.degrees(diff) <= tol_deg


def test_ring_is_one_closed_radial_stroke():
    strokes = medial_strokes(rounded_ring())
    assert len(strokes) == 1 and strokes[0].closed
    assert all(rung_points_to_center(r, tol_deg=8) for r in strokes[0].rungs)


def test_ring_has_enough_rungs_to_keep_stitches_radial():
    assert len(medial_strokes(rounded_ring())[0].rungs) >= 16


def test_corner_shape_splits_into_two_mitered_pieces():
    strokes = medial_strokes(corner_shape())
    assert len(strokes) == 2
    assert strokes[0].left[-1] == strokes[0].right[-1] == strokes[1].left[0] == strokes[1].right[0]


def test_corner_pieces_are_straight_and_know_their_axis():
    a, b = medial_strokes(corner_shape())
    assert a.axis and b.axis
    dot = abs(a.axis[0] * b.axis[0] + a.axis[1] * b.axis[1])
    assert dot < 0.2


def test_rect_ring_has_four_pieces():
    assert len(medial_strokes(rect_ring())) == 4


def test_rung_contacts_never_repeat_on_one_side():
    for s in medial_strokes(corner_shape()):
        lefts = [r[0] for r in s.rungs]
        rights = [r[1] for r in s.rungs]
        assert len(lefts) == len(set(lefts)) and len(rights) == len(set(rights))


def test_ring_keeps_rungs_all_the_way_round_for_any_seam():
    from shapely.affinity import rotate, scale
    for angle in range(0, 360, 30):
        ring = rotate(scale(rounded_ring(), 1.0, 0.7), angle, origin=(0, 0))
        stroke = medial_strokes(ring)[0]
        assert len(stroke.rungs) >= 16, angle
