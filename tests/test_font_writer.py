import json

import pytest

from hangul_satin.font_writer import write_font

from .test_outline import _build_font


@pytest.fixture
def font_path(tmp_path):
    path = tmp_path / "f.ttf"
    _build_font(path, 2048)
    return path


def test_written_folder_renders_through_font(inkstitch, tmp_path, font_path):
    import inkex
    from lib.lettering import Font
    write_font(font_path, "A", tmp_path / "f", 30)
    dest = inkex.Group()
    Font(str(tmp_path / "f")).render_text("AA", dest, "ltr")
    assert len(list(dest.iter("{http://www.w3.org/2000/svg}path"))) >= 2


def test_missing_glyph_is_reported_not_raised(tmp_path, font_path):
    result = write_font(font_path, "A가", tmp_path / "f", 30)
    assert result.built == ["A"] and "가" in result.failed


def test_failed_glyph_is_listed_in_report_json(tmp_path, font_path):
    write_font(font_path, "A가", tmp_path / "f", 30)
    assert "가" in json.loads((tmp_path / "f" / "report.json").read_text(encoding="utf8"))["failed"]


def test_space_is_kept_as_word_spacing(tmp_path, font_path):
    result = write_font(font_path, "A ", tmp_path / "f", 30)
    meta = json.loads((tmp_path / "f" / "font.json").read_text(encoding="utf8"))
    assert result.built == ["A"] and " " not in result.failed and meta["horiz_adv_x_space"] > 0


def test_font_json_has_advance_for_each_glyph(tmp_path, font_path):
    write_font(font_path, "A", tmp_path / "f", 30)
    meta = json.loads((tmp_path / "f" / "font.json").read_text(encoding="utf8"))
    assert meta["glyphs"] == ["A"] and meta["horiz_adv_x"]["A"] > 0


def test_font_license_comes_from_the_font(tmp_path, font_path):
    from fontTools.ttLib import TTFont
    font = TTFont(font_path)
    font["name"].setName("Test License", 13, 3, 1, 0x409)
    font.save(font_path)
    write_font(font_path, "A", tmp_path / "f", 30)
    assert json.loads((tmp_path / "f" / "font.json").read_text(encoding="utf8"))["font_license"] == "Test License"


def test_each_batch_file_is_a_valid_glyph_file(tmp_path, font_path):
    write_font(font_path, "A", tmp_path / "f", 30, batch_size=1)
    assert list((tmp_path / "f" / "ltr").glob("*.svg"))


def test_cli_prints_summary_and_returns_zero(tmp_path, font_path, capsys):
    from hangul_satin.cli import main
    assert main([str(font_path), "--chars", "A가", "--size", "30", "--out", str(tmp_path / "f")]) == 0
    out = capsys.readouterr().out
    assert "1" in out and "가" in out


def test_cli_charset_ks_x_1001_covers_2350_syllables():
    from hangul_satin.cli import ks_x_1001_syllables
    syllables = ks_x_1001_syllables()
    assert len(syllables) == 2350 and "가" in syllables and "힝" in syllables and "꺪" not in syllables


def test_check_lists_glyphs_that_miss_the_quality_limits(inkstitch, tmp_path, font_path):
    result = write_font(font_path, "A", tmp_path / "f", 60, check=True)
    report = json.loads((tmp_path / "f" / "report.json").read_text(encoding="utf8"))
    assert report["review"] == result.review and set(result.review) <= {"A"}


def test_markup_characters_are_escaped_in_layer_names(tmp_path):
    from fontTools.ttLib import TTFont

    from .test_outline import _build_font
    path = tmp_path / "amp.ttf"
    _build_font(path, 1000)
    font = TTFont(path)
    for table in font["cmap"].tables:
        table.cmap[ord("&")] = "A"
    font.save(path)
    result = write_font(path, "&", tmp_path / "f", 30)
    import xml.dom.minidom
    assert result.built == ["&"]
    xml.dom.minidom.parse(str(tmp_path / "f" / "ltr.svg"))
