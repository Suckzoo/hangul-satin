"""Findings of the whole-branch review. Each test failed before its fix."""
import os
from pathlib import Path

import pytest
from fontTools.ttLib import TTFont
from shapely.geometry import Polygon

from hangul_satin.compose import compose_component
from hangul_satin.font_writer import write_font
from hangul_satin.outline import glyph_outline
from hangul_satin.scan_satin import scan_satin
from hangul_satin.types import SatinStroke

from .shapes import two_stems_two_bars
from .test_font_writer import font_path  # noqa: F401

FONT_DIR = os.environ.get("INKSTITCH_TEST_FONT_DIR")


def test_tiny_slanted_piece_keeps_rungs_off_the_rail_ends():
    s = scan_satin(Polygon([(0, 0), (14, 40), (14, 240), (0, 200)]), (1, 0))
    assert s.rungs[0][0] != s.left[0] and s.rungs[-1][0] != s.left[-1]


def test_misread_rails_are_found(inkstitch):
    from hangul_satin.inkstitch_bridge import misread_strokes
    left, right = [(0.0, 0.0), (10.0, 0.0)], [(0.0, 100.0), (10.0, 100.0)]
    rungs = [((2.0, 0.0), (2.0, 100.0)), ((8.0, 0.0), (8.0, 100.0))]
    assert misread_strokes([SatinStroke(left=left, right=right, rungs=rungs, width=100.0)], 30) == [0]


def test_medial_part_never_keeps_a_zero_length_rail():
    from hangul_satin.medial import _has_usable_rails
    point = (5.0, 5.0)
    degenerate = SatinStroke(left=[point, point, point], right=[(0.0, 0.0), (10.0, 0.0)], rungs=[])
    assert not _has_usable_rails(degenerate)


@pytest.mark.skipif(not FONT_DIR, reason="local font only")
@pytest.mark.parametrize("weight,char", [("Bold", "뎋"), ("Black", "s"), ("Bold", "갢")])
def test_reported_glyphs_are_read_correctly_by_inkstitch(inkstitch, weight, char):
    from hangul_satin.compose import compose_glyph
    from hangul_satin.inkstitch_bridge import misread_strokes
    font = TTFont(Path(FONT_DIR).expanduser() / f"CookieRun {weight}.otf")
    assert misread_strokes(compose_glyph(glyph_outline(font, char)), 30) == []


def test_bar_goes_under_every_pillar_it_touches():
    strokes = compose_component(two_stems_two_bars())
    bars = [i for i, s in enumerate(strokes) if abs(s.axis[0]) > 0.5]
    pillars = [i for i, s in enumerate(strokes) if abs(s.axis[1]) > 0.5]
    assert len(bars) == 2 and len(pillars) == 2 and max(bars) < min(pillars)


def test_check_without_inkstitch_stops_before_writing(tmp_path, font_path, monkeypatch):  # noqa: F811
    monkeypatch.setenv("INKSTITCH_PATH", "/nonexistent")
    with pytest.raises(RuntimeError):
        write_font(font_path, "A", tmp_path / "f", 30, check=True)
    assert not (tmp_path / "f" / "font.json").exists()


def test_cli_reports_a_missing_inkstitch(tmp_path, font_path, monkeypatch, capsys):  # noqa: F811
    from hangul_satin.cli import main
    monkeypatch.setenv("INKSTITCH_PATH", "/nonexistent")
    assert main([str(font_path), "--chars", "A", "--out", str(tmp_path / "f"), "--check"]) == 2
    assert "INKSTITCH_PATH" in capsys.readouterr().err
