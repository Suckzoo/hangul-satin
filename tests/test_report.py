import json
import random

import pytest

from hangul_satin.report import decode_points, encode_points, random_syllables, render_text, survey_font

from .test_font_writer import font_path  # noqa: F401


def test_points_survive_encoding():
    points = [(0.0, 0.0), (12.34, 5.67), (12.0, -3.21), (300.25, 400.5)]
    decoded = decode_points(encode_points(points))
    flat = [v for p in points for v in p]
    assert [v for p in decoded for v in p] == pytest.approx(flat, abs=0.011)


def test_random_syllables_are_stable_and_hangul():
    first, second = random_syllables(300, seed=7), random_syllables(300, seed=7)
    assert first == second and len(set(first)) == 300 and all(0xAC00 <= ord(c) <= 0xD7A3 for c in first)
    assert first != random_syllables(300, seed=8)


def test_render_text_keeps_letters_on_one_line_in_order(inkstitch, tmp_path, font_path):  # noqa: F811
    from hangul_satin.font_writer import write_font
    write_font(font_path, "A", tmp_path / "f", 30)
    result = render_text(tmp_path / "f", font_path, "AA", 30)
    xs = [p[0] for g in result["groups"] if not g["underlay"] for p in g["pts"]]
    assert max(xs) > 30 and result["stitches"] > 0 and result["outlines"]


def test_render_text_outline_matches_stitches(inkstitch, tmp_path, font_path):  # noqa: F811
    from hangul_satin.font_writer import write_font
    write_font(font_path, "A", tmp_path / "f", 30)
    result = render_text(tmp_path / "f", font_path, "A", 30)
    outline_xs = [p[0] for poly in result["outlines"] for ring in poly for p in ring]
    stitch_xs = [p[0] for g in result["groups"] if not g["underlay"] for p in g["pts"]]
    assert abs(min(outline_xs) - min(stitch_xs)) < 1.0


def test_two_lines_stack_downward(inkstitch, tmp_path, font_path):  # noqa: F811
    from hangul_satin.font_writer import write_font
    write_font(font_path, "A", tmp_path / "f", 30)
    one = render_text(tmp_path / "f", font_path, "A", 30)
    two = render_text(tmp_path / "f", font_path, "A\nA", 30)
    assert max(p[1] for g in two["groups"] for p in g["pts"]) > max(p[1] for g in one["groups"] for p in g["pts"]) + 20


def test_survey_counts_pass_and_missing(inkstitch, font_path):  # noqa: F811
    survey = survey_font(font_path, "A가", 30)
    assert survey["total"] == 2 and survey["missing"] == 1 and survey["passed"] + len(survey["review"]) == 1


def test_page_embeds_items_without_font_files(tmp_path):
    from hangul_satin.report import write_page
    item = dict(key="A", label="A", weight="Regular", size=30, stitches=3, jumps=0, trims=0, review={},
                groups=[dict(el=0, underlay=False, pts=[(0.0, 0.0), (1.0, 1.0)])], outlines=[[[(0.0, 0.0), (1.0, 0.0), (1.0, 1.0)]]])
    page = tmp_path / "p.html"
    write_page(page, [item], [dict(font="T", total=1, passed=1, missing=0, errors=0, review={}, seconds=0.1)], title="T")
    html = page.read_text(encoding="utf8")
    assert html.startswith("<!DOCTYPE html>") and "<title>T</title>" in html
    assert json.loads(html.split("const ITEMS=")[1].split(";\n")[0])[0]["label"] == "A"
    assert random is not None
