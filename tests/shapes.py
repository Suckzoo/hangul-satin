"""Synthetic glyph parts. Coordinates are em-1000 units, y up. Fonts are not committed, so tests use these."""
from shapely.geometry import Polygon, box
from shapely.ops import unary_union


def stem_with_tick(proud_side=0.0):
    """ㅏ: a vertical pillar with one tick on the right."""
    stem = box(0, 0, 120, 700)
    tick = box(120 + proud_side, 300, 240, 420)
    return unary_union([stem, tick])


def two_stems_two_bars(hole=120):
    """ㅒ: two pillars joined by two bars, with a hole between the bars."""
    mid = 350
    return unary_union([box(0, 0, 120, 700), box(240, 0, 360, 700),
                        box(120, mid + hole / 2, 240, mid + hole / 2 + 100),
                        box(120, mid - hole / 2 - 100, 240, mid - hole / 2)])


def bar_with_tick_up():
    """ㅗ: a horizontal pillar with one tick on top."""
    return unary_union([box(0, 0, 700, 120), box(300, 120, 420, 300)])


def rounded_ring(outer=260, inner=120):
    from shapely.geometry import Point
    return Point(0, 0).buffer(outer, 64).difference(Point(0, 0).buffer(inner, 64))


def rect_ring():
    """ㅁ: square outside, square hole."""
    return box(0, 0, 500, 400).difference(box(120, 120, 380, 280))


def corner_shape():
    """ㄱ: a bar and a leg joined by one sharp corner."""
    return Polygon([(0, 700), (500, 700), (500, 0), (380, 0), (380, 580), (0, 580)])


def rect_with_kink():
    """One side has a small dent. A dent is not a branch."""
    return Polygon([(0, 0), (120, 0), (120, 340), (124, 350), (120, 360), (120, 700), (0, 700)])


def stepped_double_corner():
    """ㄲ join: first bar sits lower than the second bar and the first leg hangs between them."""
    first_bar = box(0, 440, 200, 560)
    first_leg = box(120, 0, 240, 480)
    second_bar = box(180, 500, 560, 640)
    second_leg = box(440, 0, 560, 640)
    return unary_union([first_bar, first_leg, second_bar, second_leg])


def wide_bar():
    return box(0, 0, 800, 300)


def fat_s_shape():
    """Black ㄹ: three thick bars joined by thick connectors, with narrow slots."""
    return unary_union([box(0, 600, 500, 800), box(380, 400, 500, 800), box(0, 300, 500, 500),
                        box(0, 0, 120, 500), box(0, 0, 500, 200)])
