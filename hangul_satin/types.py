"""Shared data types. All geometry is in em-1000 units with y up."""
from dataclasses import dataclass, field

from shapely.geometry import LineString, Polygon

Point = tuple[float, float]

RAIL_SIMPLIFY = 0.25
RUNG_EXTEND = 0.04


@dataclass
class SatinStroke:
    left: list[Point]
    right: list[Point]
    rungs: list[tuple[Point, Point]]
    closed: bool = False
    width: float = 0.0
    axis: tuple[float, float] | None = None
    region: Polygon | None = None
    under: set[int] = field(default_factory=set)
    over: set[int] = field(default_factory=set)

    def path_data(self, scale: float, baseline: float = 1000.0) -> str:
        """SVG path data: two rails, then the rungs. Rungs reach slightly past the rails so they cross them."""
        def to_d(line):
            return "M " + " L ".join(f"{x * scale:.3f},{(baseline - y) * scale:.3f}" for x, y in line)
        parts = [to_d(_simplified(self.left)), to_d(_simplified(self.right))]
        parts += [to_d(_extended(a, b)) for a, b in self.rungs]
        return " ".join(parts)


def _simplified(line: list[Point]) -> list[Point]:
    return list(LineString(line).simplify(RAIL_SIMPLIFY).coords)


def _extended(a: Point, b: Point) -> list[Point]:
    dx, dy = (b[0] - a[0]) * RUNG_EXTEND, (b[1] - a[1]) * RUNG_EXTEND
    return [(a[0] - dx, a[1] - dy), (b[0] + dx, b[1] + dy)]
