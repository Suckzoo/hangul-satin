"""Talk to a local InkStitch checkout: turn strokes into real stitches with its satin engine."""
import io
import math
import os
import sys
from pathlib import Path

from shapely.affinity import affine_transform
from shapely.geometry import LineString, MultiPolygon, Point

from .compose import compose_glyph
from .metrics import GlyphReport, evaluate
from .pillars import Pillar, find_pillars
from .types import SatinStroke

PX_PER_MM = 96 / 25.4
PULL_COMPENSATION_MM = 0.2
CONTOUR_MIN_WIDTH_MM = 1.5
ZIGZAG_MIN_WIDTH_MM = 4.0
# below the 7 mm limit: InkStitch lets a stitch reach the set length, and a zigzag runs slightly longer than its rung
SPLIT_LENGTH_MM = 6.5
CROSS_SAMPLES = 8
EMPTY_SVG = (b'<svg xmlns="http://www.w3.org/2000/svg" xmlns:inkstitch="http://inkstitch.org/namespace" '
             b'width="4000" height="4000" viewBox="0 0 4000 4000"><metadata>'
             b'<inkstitch:min_stitch_len_mm>0.1</inkstitch:min_stitch_len_mm>'
             b'<inkstitch:collapse_len_mm>3.0</inkstitch:collapse_len_mm>'
             b'<inkstitch:inkstitch_svg_version>3</inkstitch:inkstitch_svg_version></metadata></svg>')


def inkstitch_path() -> Path:
    return Path(os.environ.get("INKSTITCH_PATH", "~/tmp/InkStitch")).expanduser()


def use_inkstitch() -> None:
    """Make InkStitch's lib package importable. Raises when the checkout is missing."""
    path = inkstitch_path()
    if not (path / "lib" / "elements").is_dir():
        raise RuntimeError(f"InkStitch checkout not found at {path}. Set INKSTITCH_PATH.")
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))
    sys.dont_write_bytecode = True


def satin_attributes(stroke: SatinStroke, size_mm: float) -> dict[str, str]:
    """InkStitch parameters without the namespace prefix."""
    width_mm = stroke.width * size_mm / 1000
    attrs = {"satin_column": "True", "pull_compensation_mm": str(PULL_COMPENSATION_MM)}
    attrs["contour_underlay" if width_mm >= CONTOUR_MIN_WIDTH_MM else "center_walk_underlay"] = "True"
    if width_mm >= ZIGZAG_MIN_WIDTH_MM:
        attrs["zigzag_underlay"] = "True"
    if _widest_cross_mm(stroke, size_mm) + 2 * PULL_COMPENSATION_MM > SPLIT_LENGTH_MM:
        attrs["max_stitch_length_mm"] = str(SPLIT_LENGTH_MM)
    return attrs


def _widest_cross_mm(stroke, size_mm):
    """Rungs can miss the widest place. InkStitch pairs rail points by proportion between rungs, so sample the same way."""
    left, right = LineString(stroke.left), LineString(stroke.right)
    left_cuts = _rail_cuts(left, [a for a, _ in stroke.rungs])
    right_cuts = _rail_cuts(right, [b for _, b in stroke.rungs])
    widest = 0.0
    for (l0, l1), (r0, r1) in zip(zip(left_cuts, left_cuts[1:]), zip(right_cuts, right_cuts[1:])):
        for i in range(CROSS_SAMPLES + 1):
            f = i / CROSS_SAMPLES
            widest = max(widest, left.interpolate(l0 + (l1 - l0) * f).distance(right.interpolate(r0 + (r1 - r0) * f)))
    return widest * size_mm / 1000


def _rail_cuts(rail, contacts):
    return sorted({0.0, rail.length, *(rail.project(Point(p)) for p in contacts)})


def stitch_strokes(strokes: list[SatinStroke], size_mm: float) -> list[dict]:
    """Stitch groups in mm with y down, one group per run of underlay or top stitches of one stroke."""
    use_inkstitch()
    import inkex
    from lib.elements import SatinColumn

    root = inkex.load_svg(io.BytesIO(EMPTY_SVG)).getroot()
    scale = size_mm / 1000 * PX_PER_MM
    elements = []
    for stroke in strokes:
        node = inkex.PathElement()
        node.set("d", stroke.path_data(scale))
        node.set("style", "fill:none;stroke:#000;stroke-width:1")
        for name, value in satin_attributes(stroke, size_mm).items():
            node.set(f"inkstitch:{name}", value)
        root.append(node)
        elements.append(SatinColumn(node))
    return _collect_stitches(elements)


def _collect_stitches(elements):
    groups, last = [], None
    for index, element in enumerate(elements):
        following = elements[index + 1] if index + 1 < len(elements) else None
        for stitch_group in element.embroider(last, following):
            last = stitch_group
            _append_runs(groups, stitch_group, index)
    return groups


def _append_runs(groups, stitch_group, index):
    current = None
    for stitch in stitch_group.stitches:
        point = (stitch.x / PX_PER_MM, stitch.y / PX_PER_MM)
        underlay = any("underlay" in str(tag) for tag in (stitch.tags or []))
        if current is None or current["underlay"] != underlay:
            if current is not None:
                current["pts"].append(point)
            current = dict(el=index, underlay=underlay, pts=[])
            groups.append(current)
        current["pts"].append(point)


def to_mm(geometry, size_mm: float):
    """Em-1000, y up to mm, y down, the same placement as SatinStroke.path_data."""
    k = size_mm / 1000
    return affine_transform(geometry, [k, 0, 0, -k, 0, size_mm])


def pillars_mm(outline, size_mm: float) -> list[Pillar]:
    parts = list(outline.shape.geoms) if isinstance(outline.shape, MultiPolygon) else [outline.shape]
    out = []
    for part in parts:
        for pillar in find_pillars(part):
            axis = (pillar.axis[0], -pillar.axis[1])
            out.append(Pillar(pillar.orientation, pillar.width * size_mm / 1000, axis, to_mm(pillar.region, size_mm)))
    return out


def glyph_report(outline, size_mm: float) -> GlyphReport:
    groups = stitch_strokes(compose_glyph(outline), size_mm)
    return evaluate(to_mm(outline.shape, size_mm), groups, pillars_mm(outline, size_mm), size_mm)
