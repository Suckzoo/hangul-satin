"""Talk to a local InkStitch checkout: turn strokes into real stitches with its satin engine."""
import io
import os
import sys
from pathlib import Path

from shapely.affinity import affine_transform
from shapely.geometry import MultiPolygon

from .compose import compose_glyph
from .metrics import GlyphReport, evaluate
from .pillars import Pillar, find_pillars
from .types import SatinStroke

PX_PER_MM = 96 / 25.4
PULL_COMPENSATION_MM = 0.2
CONTOUR_MIN_WIDTH_MM = 1.5
ZIGZAG_MIN_WIDTH_MM = 4.0
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
    return attrs


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
