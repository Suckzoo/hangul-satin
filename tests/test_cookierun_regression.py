"""Local only: fonts are not committed. Set INKSTITCH_TEST_FONT_DIR to run these."""
import os
from pathlib import Path

import pytest
from fontTools.ttLib import TTFont

from hangul_satin.outline import glyph_outline

FONT_DIR = os.environ.get("INKSTITCH_TEST_FONT_DIR")
pytestmark = pytest.mark.skipif(not FONT_DIR, reason="local font only")


@pytest.mark.parametrize("weight", ["Regular", "Bold", "Black"])
@pytest.mark.parametrize("char", ["가", "감", "꺪", "앙"])
@pytest.mark.parametrize("size", [30, 15])
def test_cookierun_meets_gap_and_tilt(inkstitch, weight, char, size):
    from hangul_satin.inkstitch_bridge import glyph_report
    font = TTFont(Path(FONT_DIR).expanduser() / f"CookieRun {weight}.otf")
    report = glyph_report(glyph_outline(font, char), size)
    assert report.gap_mm <= 0.5
    assert report.stem_tilt_p95 is None or report.stem_tilt_p95_ok


@pytest.mark.parametrize("weight,count", [("Regular", 2), ("Bold", 2), ("Black", 2)])
def test_ae_vowel_in_kkae_has_two_pillars(weight, count):
    from hangul_satin.pillars import find_pillars
    font = TTFont(Path(FONT_DIR).expanduser() / f"CookieRun {weight}.otf")
    shape = glyph_outline(font, "꺪").shape
    assert sum(len(find_pillars(p)) for p in shape.geoms) >= count
