import pytest
from shapely.affinity import rotate

from hangul_satin.pillars import find_pillars

from .shapes import bar_with_tick_up, corner_shape, rect_ring, rect_with_kink, rounded_ring, stem_with_tick, two_stems_two_bars


@pytest.mark.parametrize("shape,count,orientation", [
    (stem_with_tick(), 1, 'V'), (two_stems_two_bars(), 2, 'V'), (bar_with_tick_up(), 1, 'H'),
    (rounded_ring(), 0, None), (rect_ring(), 0, None), (corner_shape(), 0, None),
])
def test_find_pillars(shape, count, orientation):
    found = find_pillars(shape)
    assert len(found) == count and all(p.orientation == orientation for p in found)


def test_kink_in_straight_side_is_not_a_pillar():
    assert find_pillars(rect_with_kink()) == []


def test_italic_shape_beyond_15_degrees_has_no_pillar():
    assert find_pillars(rotate(stem_with_tick(), 20)) == []


def test_slightly_slanted_stem_is_still_a_pillar():
    assert len(find_pillars(rotate(stem_with_tick(), 4))) == 1


def test_tiny_hole_still_finds_two_pillars():
    assert len(find_pillars(two_stems_two_bars(hole=20))) == 2


def test_pillar_region_covers_stem_only():
    p = find_pillars(stem_with_tick())[0]
    assert p.region.bounds == pytest.approx((0, 0, 120, 700), abs=1) and p.width == pytest.approx(120, abs=1)


def test_pillar_axis_runs_along_the_stem():
    p = find_pillars(stem_with_tick())[0]
    assert abs(p.axis[1]) == pytest.approx(1, abs=0.01)
