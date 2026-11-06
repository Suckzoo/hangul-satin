"""Render real text through InkStitch's Font, survey a font's failure rate, and write a viewer page."""
import base64
import io
import json
import random
import time
from pathlib import Path

import numpy as np
from fontTools.ttLib import TTFont
from shapely.geometry import MultiPolygon

from .compose import compose_glyph
from .inkstitch_bridge import EMPTY_SVG, PX_PER_MM, _collect_stitches, glyph_report, use_inkstitch
from .outline import glyph_outline

GRID = 100.0
SYLLABLE_FIRST, SYLLABLE_LAST = 0xAC00, 0xD7A3
COLLAPSE_MM, MIN_STITCH_MM = 3.0, 0.1
VIEWER = Path(__file__).with_name("viewer.html")


def encode_points(points) -> str:
    """Little-endian int32 pairs in 0.01 mm, as deltas in int16 would overflow on long jumps."""
    array = np.round(np.asarray(points, dtype=float) * GRID).astype("<i4")
    return base64.b64encode(array.tobytes()).decode("ascii")


def decode_points(data: str) -> list[tuple[float, float]]:
    array = np.frombuffer(base64.b64decode(data), dtype="<i4").reshape(-1, 2) / GRID
    return [(float(x), float(y)) for x, y in array]


def random_syllables(count: int, seed: int) -> list[str]:
    return [chr(c) for c in random.Random(seed).sample(range(SYLLABLE_FIRST, SYLLABLE_LAST + 1), count)]


def render_text(font_dir, font_path, text: str, size_mm: float) -> dict:
    """Lay out text with InkStitch's Font, so spacing and glyph loading are the real ones."""
    use_inkstitch()
    import inkex
    from lib.elements.utils.nodes import nodes_to_elements
    from lib.lettering import Font
    from lib.stitch_plan import stitch_groups_to_stitch_plan
    from lib.svg.tags import EMBROIDERABLE_TAGS

    root = inkex.load_svg(io.BytesIO(EMPTY_SVG)).getroot()
    layer = inkex.Layer()
    root.append(layer)
    group = inkex.Group()
    layer.append(group)
    Font(str(font_dir), show_font_path_warning=False).render_text(text, group, "ltr", back_and_forth=False)

    elements = nodes_to_elements(group.iterdescendants(EMBROIDERABLE_TAGS))
    plan_groups = []
    stitches = _collect_stitches(elements, plan_groups)
    plan = stitch_groups_to_stitch_plan(plan_groups, collapse_len=COLLAPSE_MM * PX_PER_MM, min_stitch_len=MIN_STITCH_MM * PX_PER_MM)
    return dict(groups=stitches, outlines=_placed_outlines(group, TTFont(font_path), size_mm), stitches=int(plan.num_stitches),
                jumps=int(plan.num_jumps), trims=int(plan.num_trims))


def _placed_outlines(group, font, size_mm):
    """Each rendered glyph node carries its translate. Glyph moved its own left edge to zero before that."""
    k = size_mm / 1000
    out = []
    for node in group.iterdescendants():
        if node.get("inkstitch:letter-group") != "glyph" or not node.label:
            continue
        outline = glyph_outline(font, node.label.strip())
        if outline is None:
            continue
        left = _stroke_left_em(outline)
        tx, ty = node.transform.apply_to_point((0, 0))
        for poly in _polygons(outline.shape):
            rings = []
            for ring in [poly.exterior, *poly.interiors]:
                rings.append([(round((x - left) * k + tx / PX_PER_MM, 2), round((1000 - y) * k + ty / PX_PER_MM, 2)) for x, y in ring.coords])
            out.append(rings)
    return out


def _stroke_left_em(outline):
    """Left edge of what the glyph file holds: rails plus the small rung overshoot, as Glyph measures it."""
    from .types import _extended
    xs = []
    for stroke in compose_glyph(outline):
        xs += [p[0] for p in stroke.left + stroke.right]
        xs += [p[0] for a, b in stroke.rungs for p in _extended(a, b)]
    return min(xs)


def _polygons(shape):
    return list(shape.geoms) if isinstance(shape, MultiPolygon) else [shape]


def survey_font(font_path, chars, size_mm: float) -> dict:
    """Count how many characters pass, and why the others do not."""
    font = TTFont(font_path)
    started = time.time()
    review, missing, errors, passed = {}, 0, {}, 0
    for char in chars:
        outline = glyph_outline(font, char)
        if outline is None:
            missing += 1
            continue
        try:
            reasons = glyph_report(outline, size_mm).reasons
        except Exception as error:  # a survey must report a crash, and go on
            errors[char] = str(error)
            continue
        if reasons:
            review[char] = reasons
        else:
            passed += 1
    return dict(font=Path(font_path).stem, total=len(chars), passed=passed, missing=missing, errors=len(errors), error_samples=errors,
                review=review, seconds=round(time.time() - started, 1))


def failure_items(font_path, font_label: str, chars: str, size_mm: float, work_dir) -> list[dict]:
    """One item per glyph, with the numbers that decide pass or fail. A glyph the font lacks is left out."""
    from .font_writer import write_font
    result = write_font(font_path, chars, work_dir, size_mm, check=True)
    font = TTFont(font_path)
    items = []
    for char in result.built:
        report = glyph_report(glyph_outline(font, char), size_mm)
        numbers = dict(gap_mm=round(report.gap_mm, 2), stem_tilt_p95=report.stem_tilt_p95,
                       max_stitch_mm=round(report.max_stitch_mm, 1), long_stitches=report.long_stitches)
        rendered = render_text(work_dir, font_path, char, size_mm)
        items.append(dict(key=f"{font_label}-{char}", label=char, font=font_label, size=size_mm, chars=char, numbers=numbers,
                          review={char: report.reasons} if report.reasons else {}, **rendered))
    return items


def write_page(path, items: list[dict], surveys: list[dict], title: str, failures: list[dict] | None = None) -> None:
    packed = [_pack(item) for item in items]
    page = VIEWER.read_text(encoding="utf8")
    page = page.replace("__TITLE__", title)
    page = page.replace("__ITEMS__", json.dumps(packed, ensure_ascii=False, separators=(",", ":")))
    page = page.replace("__SURVEYS__", json.dumps(surveys, ensure_ascii=False, separators=(",", ":")))
    page = page.replace("__FAILS__", json.dumps([_pack(f) for f in failures or []], ensure_ascii=False, separators=(",", ":")))
    Path(path).write_text(page, encoding="utf8")


def _pack(item):
    packed = {k: v for k, v in item.items() if k not in ("groups", "outlines")}
    packed["groups"] = [dict(el=g["el"], u=int(g["underlay"]), p=encode_points(g["pts"])) for g in item["groups"] if len(g["pts"]) > 1]
    packed["outlines"] = [[encode_points(ring) for ring in poly] for poly in item["outlines"]]
    return packed
