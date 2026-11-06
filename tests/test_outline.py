import pytest
from fontTools.fontBuilder import FontBuilder
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.ttLib import TTFont

from hangul_satin.outline import glyph_outline


def _build_font(path, upm):
    def square(x0, y0, x1, y1, pen):
        pen.moveTo((x0, y0))
        pen.lineTo((x0, y1))
        pen.lineTo((x1, y1))
        pen.lineTo((x1, y0))
        pen.closePath()

    k = upm / 1000
    a = TTGlyphPen(None)
    # two overlapping contours and one quadratic curve
    square(0, 0, int(500 * k), int(700 * k), a)
    square(int(300 * k), 0, int(800 * k), int(300 * k), a)
    a.moveTo((int(900 * k), 0))
    a.qCurveTo((int(1000 * k), int(100 * k)), (int(900 * k), int(200 * k)))
    a.closePath()
    fb = FontBuilder(upm, isTTF=True)
    fb.setupGlyphOrder([".notdef", "A", "space"])
    fb.setupCharacterMap({0x41: "A", 0x20: "space"})
    fb.setupGlyf({".notdef": TTGlyphPen(None).glyph(), "A": a.glyph(), "space": TTGlyphPen(None).glyph()})
    fb.setupHorizontalMetrics({".notdef": (0, 0), "A": (int(1100 * k), 0), "space": (int(300 * k), 0)})
    fb.setupHorizontalHeader(ascent=int(800 * k), descent=0)
    fb.setupNameTable({"familyName": "Test", "styleName": "Regular"})
    fb.setupOS2()
    fb.setupPost()
    fb.save(path)
    return TTFont(path)


@pytest.fixture
def font_2048(tmp_path):
    return _build_font(tmp_path / "f2048.ttf", 2048)


@pytest.fixture
def font_1000(tmp_path):
    return _build_font(tmp_path / "f1000.ttf", 1000)


def test_outline_normalizes_units_per_em(font_2048, font_1000):
    big, small = glyph_outline(font_2048, "A"), glyph_outline(font_1000, "A")
    assert big.shape.bounds[3] == pytest.approx(small.shape.bounds[3], abs=1)
    assert big.advance == pytest.approx(1100, abs=1)


def test_overlapping_contours_are_merged(font_1000):
    shape = glyph_outline(font_1000, "A").shape
    assert shape.is_valid and shape.area < 500 * 700 + 500 * 300


def test_quadratic_curve_is_flattened(font_1000):
    shape = glyph_outline(font_1000, "A").shape
    assert shape.bounds[2] > 900


def test_missing_glyph_returns_none(font_1000):
    assert glyph_outline(font_1000, "가") is None


def test_empty_glyph_returns_none(font_1000):
    assert glyph_outline(font_1000, " ") is None
