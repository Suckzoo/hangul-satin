"""Glyph outlines as shapely geometry, normalized to em-1000 units with y up."""
from dataclasses import dataclass

import numpy as np
from fontTools.pens.recordingPen import DecomposingRecordingPen
from fontTools.ttLib import TTFont
from shapely import Polygon, MultiPolygon
from shapely.ops import unary_union

CURVE_STEPS = 16


@dataclass
class GlyphOutline:
    shape: Polygon | MultiPolygon
    advance: float


def glyph_outline(font: TTFont, char: str) -> GlyphOutline | None:
    """Return the outline, or None when the font has no such glyph or the glyph is empty."""
    name = font.getBestCmap().get(ord(char))
    if name is None:
        return None
    glyph_set = font.getGlyphSet()
    pen = DecomposingRecordingPen(glyph_set)
    glyph_set[name].draw(pen)
    scale = 1000.0 / font["head"].unitsPerEm
    contours = [[(x * scale, y * scale) for x, y in c] for c in _contours(pen.value)]
    if not contours:
        return None
    shape = _fill(contours)
    if shape.is_empty:
        return None
    return GlyphOutline(shape=shape, advance=glyph_set[name].width * scale)


def _contours(ops):
    contours, cur = [], []
    for op, args in ops:
        if op == "moveTo":
            cur = [args[0]]
        elif op == "lineTo":
            cur.append(args[0])
        elif op == "curveTo":
            cur.extend(_cubic(cur[-1], *args))
        elif op == "qCurveTo":
            cur.extend(_quadratic_spline(cur[-1], args))
        elif op in ("closePath", "endPath"):
            if len(cur) > 2:
                contours.append(cur)
            cur = []
    return contours


def _cubic(p0, p1, p2, p3):
    p0, p1, p2, p3 = map(np.array, (p0, p1, p2, p3))
    out = []
    for t in np.linspace(0, 1, CURVE_STEPS + 1)[1:]:
        out.append(tuple((1 - t) ** 3 * p0 + 3 * (1 - t) ** 2 * t * p1 + 3 * (1 - t) * t * t * p2 + t ** 3 * p3))
    return out


def _quadratic_spline(p0, args):
    """TrueType spline: consecutive off-curve points imply an on-curve midpoint."""
    off, end = [np.array(a) for a in args[:-1]], np.array(args[-1])
    out, start = [], np.array(p0)
    for i, ctrl in enumerate(off):
        stop = end if i == len(off) - 1 else (ctrl + off[i + 1]) / 2
        for t in np.linspace(0, 1, CURVE_STEPS + 1)[1:]:
            out.append(tuple((1 - t) ** 2 * start + 2 * (1 - t) * t * ctrl + t * t * stop))
        start = stop
    return out or [tuple(end)]


def _signed_area(c):
    return 0.5 * sum(x0 * y1 - x1 * y0 for (x0, y0), (x1, y1) in zip(c, c[1:] + c[:1]))


def _fill(contours):
    """Non-zero winding. An opposite contour inside the fill is a hole; outside the fill it is still filled."""
    areas = [_signed_area(c) for c in contours]
    sign = np.sign(areas[int(np.argmax(np.abs(areas)))])
    outer = unary_union([Polygon(c).buffer(0) for c, a in zip(contours, areas) if np.sign(a) == sign])
    opposite = unary_union([Polygon(c).buffer(0) for c, a in zip(contours, areas) if np.sign(a) != sign])
    return outer.symmetric_difference(opposite)
