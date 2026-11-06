"""Strokes from the medial axis, for parts with no pillar: rings stay radial, sharp corners become mitres.

Voronoi ridges between boundary samples give the medial axis. Each ridge knows its two boundary samples,
and that pair is a chord across the stroke. Chords of a medial axis do not cross, so they make good rungs.
"""
import math
from collections import defaultdict
from dataclasses import dataclass

import networkx as nx
import numpy as np
import shapely
from scipy.spatial import Voronoi
from shapely.geometry import LineString, MultiPolygon, Polygon

from .types import SatinStroke

SAMPLE_STEP = 3.0
SPUR_RATIO = 1.7
SPUR_PRUNE_PER_RADIUS = 0.5
CLUSTER_PER_RADIUS = 0.9
TANGENT_PER_RADIUS = 1.3
STRAIGHT_DEG = 40.0
RUNG_STEP = 30.0
WALK_RATIO = 1.6
JUNCTION_ZONE = 1.6
MAX_FLARE = 1.12
MAX_SKEW = 0.15
TANGENT_WINDOW = 0.4
END_OVERLAP = 0.2
CORNER_PIN = 0.12
CORNER_DEG = 50.0
CORNER_GROW_DEG = 4.0
CORNER_GROW_WINDOW = 4
STRAIGHT_LIMIT = 0.2
SEAM_WINDOW = 4
MIN_RUNGS = 3


def medial_strokes(poly: Polygon) -> list[SatinStroke]:
    boundary = _Boundary(poly)
    graph = _prune(_medial_graph(poly, boundary))
    branches = _find_branches(graph)
    clusters = _Clusters(graph, branches)
    branches = [b for b in branches if not b.dropped]
    links = _link_ends(graph, branches, clusters)
    strokes = []
    for chain in _chains(branches, links):
        strokes.extend(_chain_strokes(graph, boundary, branches, chain, clusters))
    return strokes


class _Boundary:
    """Evenly spaced samples along every ring, with the distance along the ring between them."""

    def __init__(self, poly):
        pts, rings, arcs = [], [], []
        self.lengths, self.offsets, self.counts = [], [], []
        for r, ring in enumerate([poly.exterior, *poly.interiors]):
            length = ring.length
            n = max(8, int(length / SAMPLE_STEP))
            self.lengths.append(length)
            self.offsets.append(len(pts))
            self.counts.append(n)
            for i in range(n):
                p = ring.interpolate(i * length / n)
                pts.append((p.x, p.y))
                rings.append(r)
                arcs.append(i * length / n)
        self.pts, self.rings, self.arcs = np.array(pts), np.array(rings), np.array(arcs)

    def along(self, a, b):
        if self.rings[a] != self.rings[b]:
            return math.inf
        d = abs(self.arcs[a] - self.arcs[b])
        return min(d, self.lengths[self.rings[a]] - d)

    def walk(self, a, b):
        """Sample ids strictly between a and b, the short way round."""
        r = self.rings[a]
        offset, n = self.offsets[r], self.counts[r]
        ia, ib = a - offset, b - offset
        forward, back = (ib - ia) % n, (ia - ib) % n
        if forward <= back:
            return [offset + (ia + k) % n for k in range(1, forward)]
        return [offset + (ia - k) % n for k in range(1, back)]

    def point(self, i):
        return (float(self.pts[i][0]), float(self.pts[i][1]))


def _medial_graph(poly, boundary):
    vor = Voronoi(boundary.pts)
    vertices = vor.vertices
    inside = shapely.contains_xy(poly, vertices[:, 0], vertices[:, 1])
    graph = nx.Graph()
    for (a, b), (u, v) in zip(vor.ridge_points, vor.ridge_vertices):
        if u < 0 or v < 0 or not inside[u] or not inside[v]:
            continue
        # samples close along the boundary only trace a corner or a cap: they are spurs, not a stroke
        if boundary.along(a, b) <= SPUR_RATIO * np.linalg.norm(boundary.pts[a] - boundary.pts[b]):
            continue
        if poly.contains(LineString([vertices[u], vertices[v]])):
            graph.add_edge(u, v, sites=(int(a), int(b)))
    for node in graph.nodes:
        graph.nodes[node]["pos"] = vertices[node]
        graph.nodes[node]["r"] = float(np.linalg.norm(boundary.pts - vertices[node], axis=1).min())
    return graph


@dataclass
class _Branch:
    a: int | None
    b: int | None
    nodes: list[int]
    cycle: bool = False
    dropped: bool = False


def _find_branches(graph):
    specials = {n for n in graph if graph.degree(n) != 2}
    out, seen = [], set()
    for start in specials:
        for neighbor in graph[start]:
            if (start, neighbor) not in seen:
                path = _trace(graph, start, neighbor, specials)
                seen.update(((start, neighbor), (path[-1], path[-2])))
                out.append(_Branch(path[0], path[-1], path))
    used = {n for b in out for n in b.nodes}
    for component in nx.connected_components(graph):
        if not component & used:
            out.append(_Branch(None, None, _trace_cycle(graph, next(iter(component))), cycle=True))
    return out


def _trace(graph, start, neighbor, specials):
    path = [start, neighbor]
    while path[-1] not in specials:
        following = [x for x in graph[path[-1]] if x != path[-2]]
        if not following:
            break
        path.append(following[0])
    return path


def _trace_cycle(graph, start):
    path, previous, current = [start], None, start
    while True:
        following = [x for x in graph[current] if x != previous]
        if not following:
            return path
        if following[0] == start and len(path) > 2:
            return [*path, start]
        previous, current = current, following[0]
        path.append(current)


def _path_length(graph, nodes):
    return sum(np.linalg.norm(graph.nodes[a]["pos"] - graph.nodes[b]["pos"]) for a, b in zip(nodes, nodes[1:]))


def _prune(graph):
    """Remove short dead ends that remain after the spur filter."""
    changed = True
    while changed:
        changed = False
        for branch in _find_branches(graph):
            if not branch.cycle and _is_short_dead_end(graph, branch):
                inner = branch.nodes[1:] if graph.degree(branch.b) == 1 else branch.nodes[:-1]
                graph.remove_nodes_from(inner)
                changed = True
        graph.remove_nodes_from([n for n in list(graph) if graph.degree(n) == 0])
    return graph


def _is_short_dead_end(graph, branch):
    a_leaf, b_leaf = graph.degree(branch.a) == 1, graph.degree(branch.b) == 1
    if a_leaf == b_leaf:
        return False
    junction = branch.a if b_leaf else branch.b
    return _path_length(graph, branch.nodes) < SPUR_PRUNE_PER_RADIUS * graph.nodes[junction]["r"]


class _Clusters:
    """Junctions joined by a very short branch act as one junction."""

    def __init__(self, graph, branches):
        self.parent = {}
        for branch in branches:
            if not branch.cycle and self._should_merge(graph, branch):
                self.parent[self.find(branch.a)] = self.find(branch.b)
                branch.dropped = True
        members = defaultdict(list)
        for node in graph:
            if graph.degree(node) >= 3:
                members[self.find(node)].append(node)
        self.info = {}
        for root, nodes in members.items():
            positions = np.array([graph.nodes[n]["pos"] for n in nodes])
            self.info[root] = dict(pos=positions.mean(0), r=max(graph.nodes[n]["r"] for n in nodes), has_pass=False)

    @staticmethod
    def _should_merge(graph, branch):
        a, b = branch.a, branch.b
        if a == b or graph.degree(a) < 3 or graph.degree(b) < 3:
            return False
        return _path_length(graph, branch.nodes) < CLUSTER_PER_RADIUS * max(graph.nodes[a]["r"], graph.nodes[b]["r"])

    def find(self, node):
        self.parent.setdefault(node, node)
        while self.parent[node] != node:
            self.parent[node] = self.parent[self.parent[node]]
            node = self.parent[node]
        return node


def _tangent_from(graph, nodes, distance):
    start = graph.nodes[nodes[0]]["pos"]
    travelled, previous = 0.0, start
    for node in nodes[1:]:
        p = graph.nodes[node]["pos"]
        travelled += np.linalg.norm(p - previous)
        previous = p
        if travelled >= distance:
            break
    v = previous - start
    return v / (np.linalg.norm(v) + 1e-9)


def _link_ends(graph, branches, clusters):
    """At each junction, join the branch ends that continue each other in a straight line."""
    ends = defaultdict(list)
    for i, branch in enumerate(branches):
        if not branch.cycle:
            for end, node in (("a", branch.a), ("b", branch.b)):
                if graph.degree(node) >= 3:
                    ends[clusters.find(node)].append((i, end))
    links = {}
    for root, items in ends.items():
        _link_at_junction(graph, branches, clusters.info[root], items, links)
    return links


def _link_at_junction(graph, branches, info, items, links):
    def direction(item):
        i, end = item
        nodes = branches[i].nodes if end == "a" else branches[i].nodes[::-1]
        return _tangent_from(graph, nodes, TANGENT_PER_RADIUS * info["r"])

    dirs = {item: direction(item) for item in items}
    candidates = []
    for x, p in enumerate(items):
        for q in items[x + 1:]:
            angle = math.degrees(math.acos(float(np.clip(dirs[p] @ -dirs[q], -1, 1))))
            if angle < STRAIGHT_DEG and p[0] != q[0]:
                candidates.append((angle, p, q))
    for _, p, q in sorted(candidates, key=lambda c: c[0]):
        if p not in links and q not in links:
            links[p], links[q] = q, p
            info["has_pass"] = True


def _other(end):
    return "b" if end == "a" else "a"


def _chains(branches, links):
    chains, used = [], set()
    for i, branch in enumerate(branches):
        if i in used:
            continue
        if branch.cycle:
            used.add(i)
            chains.append(dict(seq=[(i, "a")], closed=True))
            continue
        start, wrapped = _chain_start(i, links)
        seq = _walk_chain(start, links)
        used.update(item[0] for item in seq)
        chains.append(dict(seq=seq, closed=wrapped))
    return chains


def _chain_start(i, links):
    current, visited = (i, "a"), {i}
    while current in links:
        j, end = links[current]
        if j in visited:
            return (i, "a"), True
        visited.add(j)
        current = (j, _other(end))
    return current, False


def _walk_chain(start, links):
    seq, visited, current = [], set(), start
    while True:
        seq.append(current)
        visited.add(current[0])
        outgoing = (current[0], _other(current[1]))
        if outgoing not in links or links[outgoing][0] in visited:
            return seq
        current = links[outgoing]


@dataclass
class _Chord:
    mid: np.ndarray
    left: int
    right: int
    s: float
    tangent: np.ndarray


def _chain_nodes(graph, branches, chain, clusters):
    nodes, passes = [], []
    for i, end in chain["seq"]:
        ordered = branches[i].nodes if end == "a" else branches[i].nodes[::-1]
        if nodes:
            passes.append(clusters.find(nodes[-1]))
            nodes.append(None)
        nodes.extend(ordered)
    known = [n for n in nodes if n is not None]
    start_j = clusters.find(known[0]) if graph.degree(known[0]) >= 3 else None
    end_j = clusters.find(known[-1]) if graph.degree(known[-1]) >= 3 else None
    if chain["closed"] and start_j is not None and start_j == end_j:
        passes.append(start_j)
    return nodes, passes, start_j, end_j


def _make_chords(graph, boundary, nodes):
    chords, travelled = [], 0.0
    for u, v in zip(nodes, nodes[1:]):
        if u is None or v is None:
            continue
        a, b = graph[u][v]["sites"]
        pu, pv = graph.nodes[u]["pos"], graph.nodes[v]["pos"]
        tangent, mid = pv - pu, (pu + pv) / 2
        offset = boundary.pts[a] - mid
        left, right = (a, b) if tangent[0] * offset[1] - tangent[1] * offset[0] > 0 else (b, a)
        chords.append(_Chord(mid, left, right, travelled, tangent))
        travelled += np.linalg.norm(tangent)
    return chords


def _smooth_tangents(chords, width):
    """A single Voronoi edge is noisy, so measure the direction over about half a stroke width."""
    mids = np.array([c.mid for c in chords])
    arc = np.array([c.s for c in chords])
    last = len(chords) - 1
    for chord in chords:
        lo = min(int(np.searchsorted(arc, chord.s - TANGENT_WINDOW * width)), last)
        hi = min(int(np.searchsorted(arc, chord.s + TANGENT_WINDOW * width)), last)
        chord.tangent = mids[hi] - mids[lo]


def _skew(boundary, chord):
    across = boundary.pts[chord.left] - boundary.pts[chord.right]
    tangent = chord.tangent / (np.linalg.norm(chord.tangent) + 1e-9)
    return abs(float(across / (np.linalg.norm(across) + 1e-9) @ tangent))


def _clean_chords(boundary, chords, width, junctions, clusters):
    """Drop chords distorted by a junction, which are flared or rotated. Keep something for a short tick."""
    def width_of(chord):
        return np.linalg.norm(boundary.pts[chord.left] - boundary.pts[chord.right])

    def clean(chord):
        for j in junctions:
            info = clusters.info[j]
            near = np.linalg.norm(chord.mid - info["pos"]) < JUNCTION_ZONE * info["r"]
            if near and (width_of(chord) > MAX_FLARE * width or _skew(boundary, chord) > MAX_SKEW):
                return False
        return True

    kept = [c for c in chords if clean(c)]
    if len(kept) >= 2:
        return kept
    best = sorted(chords, key=lambda c: _skew(boundary, c))[:max(2, len(chords) // 3)]
    return sorted(best, key=lambda c: c.s)


def _chain_strokes(graph, boundary, branches, chain, clusters):
    nodes, passes, start_j, end_j = _chain_nodes(graph, branches, chain, clusters)
    chords = _make_chords(graph, boundary, nodes)
    if not chords:
        return []
    width = float(np.median([np.linalg.norm(boundary.pts[c.left] - boundary.pts[c.right]) for c in chords]))
    _smooth_tangents(chords, width)
    junctions = {j for j in (start_j, end_j, *passes) if j is not None}
    kept = _clean_chords(boundary, chords, width, junctions, clusters)
    builder = _PieceBuilder(boundary, clusters, set(passes))
    ring = chain["closed"] and start_j is None and end_j is None
    if ring:
        kept = _rotate_to_straight(boundary, kept)
    corners = _detect_corners(boundary, kept, width)
    pieces = _split_at_corners(boundary, kept, corners, ring, _cap_of(start_j), _cap_of(end_j))
    strokes = [builder.stroke(*piece, ring and not corners) for piece in pieces if piece[0]]
    for stroke in strokes:
        stroke.under = {j for j in (start_j, end_j) if j is not None}
    return [s for s in strokes if len(s.left) > 1 and len(s.right) > 1]


def _cap_of(junction):
    return dict(kind="free") if junction is None else dict(kind="junction", j=junction)


def _chord_rotation(boundary, chords, a, b):
    u = boundary.pts[chords[a].right] - boundary.pts[chords[a].left]
    v = boundary.pts[chords[b].right] - boundary.pts[chords[b].left]
    return abs(math.degrees(math.atan2(u[0] * v[1] - u[1] * v[0], float(u @ v))))


def _rotate_to_straight(boundary, chords):
    """Start a ring where it is straightest, and among equals at the top, so the seam never hides a corner."""
    n = len(chords)
    if n <= 2 * SEAM_WINDOW:
        return chords
    turn = [_chord_rotation(boundary, chords, (i - SEAM_WINDOW) % n, (i + SEAM_WINDOW) % n) for i in range(n)]
    calm = min(turn) + 2.0
    start = max((i for i in range(n) if turn[i] <= calm), key=lambda i: chords[i].mid[1])
    return _renumbered(chords[start:] + chords[:start])


def _renumbered(chords):
    """Arc positions must grow along the new order: rung spacing depends on them."""
    travelled = 0.0
    for previous, chord in zip([None, *chords], chords):
        if previous is not None:
            travelled += float(np.linalg.norm(chord.mid - previous.mid))
        chord.s = travelled
    return chords


def _detect_corners(boundary, chords, width):
    """A corner: one contact point stays pinned while the chord rotates by more than CORNER_DEG."""
    tolerance, corners, i, n = CORNER_PIN * width, [], 0, len(chords)
    while i < n - 1:
        found = _pinned_span(boundary, chords, i, tolerance)
        if not found:
            i += 1
            continue
        low = corners[-1]["k"] + 1 if corners else 0
        a, b = _grow_corner(boundary, chords, i, found[1], low)
        corners.append(dict(i=a, k=b, side=found[0]))
        i = b + 1
    return corners


def _pinned_span(boundary, chords, i, tolerance):
    found = None
    for side in ("left", "right"):
        k, reached = i, None
        while k + 1 < len(chords) and boundary.along(getattr(chords[i], side), getattr(chords[k + 1], side)) <= tolerance:
            k += 1
            if _chord_rotation(boundary, chords, i, k) >= CORNER_DEG:
                reached = k
        if reached is not None and (found is None or k > found[1]):
            found = (side, k)
    return found


def _grow_corner(boundary, chords, a, b, low):
    """Widen the span to where the rotation starts and stops."""
    last = len(chords) - 1
    while a - 1 >= low and _chord_rotation(boundary, chords, max(a - CORNER_GROW_WINDOW, low), a) > CORNER_GROW_DEG:
        a -= 1
    while b + 1 <= last and _chord_rotation(boundary, chords, b, min(b + CORNER_GROW_WINDOW, last)) > CORNER_GROW_DEG:
        b += 1
    return a, b


def _corner_geometry(boundary, chords, corner):
    inner = corner["side"]
    outer = "right" if inner == "left" else "left"
    pivot = boundary.pts[getattr(chords[(corner["i"] + corner["k"]) // 2], inner)]
    o0, o1 = getattr(chords[corner["i"]], outer), getattr(chords[corner["k"]], outer)
    seq = [o0, *boundary.walk(o0, o1), o1]
    apex = max(seq, key=lambda w: np.linalg.norm(boundary.pts[w] - pivot))
    at = seq.index(apex)
    return dict(inner=inner, P=(float(pivot[0]), float(pivot[1])), Q=boundary.point(apex),
                before=[boundary.point(w) for w in seq[1:at]], after=[boundary.point(w) for w in seq[at + 1:-1]])


def _split_at_corners(boundary, chords, corners, ring, cap0, cap1):
    if not corners:
        seam = dict(kind="seam")
        return [(chords, seam, seam)] if ring else [(chords, cap0, cap1)]
    geometries = [_corner_geometry(boundary, chords, c) for c in corners]
    tail = len(chords)
    if ring:
        # the seam moves into the first corner, so a ring of four corners makes four pieces
        n, shift = len(chords), corners[0]["k"]
        chords = _renumbered(chords[shift:] + chords[:shift])
        tail = (corners[0]["i"] - shift) % n + 1
        cap0, cap1 = dict(kind="miter_start", **geometries[0]), dict(kind="miter_end", **geometries[0])
        corners = [dict(c, i=c["i"] - shift, k=c["k"] - shift) for c in corners[1:]]
        geometries = geometries[1:]
    pieces, start, cap = [], 0, cap0
    for corner, geometry in zip(corners, geometries):
        pieces.append((chords[start:corner["i"] + 1], cap, dict(kind="miter_end", **geometry)))
        cap, start = dict(kind="miter_start", **geometry), corner["k"]
    pieces.append((chords[start:tail], cap, cap1))
    return pieces


def _interpolated_rungs(left, right):
    """InkStitch needs three rungs to tell rails from rungs when a piece is shorter than it is wide."""
    a, b = LineString(left), LineString(right)
    rungs = []
    for f in (0.25, 0.5, 0.75):
        p, q = a.interpolate(f, normalized=True), b.interpolate(f, normalized=True)
        rungs.append(((p.x, p.y), (q.x, q.y)))
    return rungs


class _PieceBuilder:
    def __init__(self, boundary, clusters, passes):
        self.boundary, self.clusters, self.passes = boundary, clusters, passes

    def stroke(self, chords, cap0, cap1, closed):
        left, right = self._rail(chords, "left"), self._rail(chords, "right")
        if closed:
            left.append(self.boundary.point(chords[0].left))
            right.append(self.boundary.point(chords[0].right))
        else:
            left, right = self._start_cap(chords[0], cap0, left, right)
            left, right = self._end_cap(chords[-1], cap1, left, right)
        widths = [np.linalg.norm(self.boundary.pts[c.left] - self.boundary.pts[c.right]) for c in chords]
        rungs = self._rungs(chords, closed)
        if len(rungs) < MIN_RUNGS:
            rungs = _interpolated_rungs(left, right)
        stroke = SatinStroke(left=left, right=right, rungs=rungs, closed=closed, width=float(np.median(widths)), over=set(self.passes))
        if not closed:
            self._mark_straight(stroke, chords)
        return stroke

    def _rail(self, chords, side):
        points, last = [], None
        for chord in chords:
            site = getattr(chord, side)
            if site == last:
                continue
            if last is not None:
                gap = np.linalg.norm(self.boundary.pts[site] - self.boundary.pts[last])
                if self.boundary.along(last, site) <= max(WALK_RATIO * gap, 4 * SAMPLE_STEP):
                    points.extend(self.boundary.point(w) for w in self.boundary.walk(last, site))
            points.append(self.boundary.point(site))
            last = site
        return points

    def _start_cap(self, chord, cap, left, right):
        if cap["kind"] == "miter_start":
            inner, outer = [cap["Q"], cap["P"]], [cap["Q"], *cap["after"]]
            return (inner + left, outer + right) if cap["inner"] == "left" else (outer + left, inner + right)
        a, b = self._cap_points(chord, cap)
        return a[::-1] + left, b[::-1] + right

    def _end_cap(self, chord, cap, left, right):
        if cap["kind"] == "miter_end":
            inner, outer = [cap["P"], cap["Q"]], [*cap["before"], cap["Q"]]
            return (left + inner, right + outer) if cap["inner"] == "left" else (left + outer, right + inner)
        a, b = self._cap_points(chord, cap)
        return left + a, right + b

    def _cap_points(self, chord, cap):
        if cap["kind"] == "junction":
            return self._junction_cap(chord, cap["j"])
        if cap["kind"] == "free" and self.boundary.along(chord.left, chord.right) != math.inf:
            arc = self.boundary.walk(chord.left, chord.right)
            if arc:
                middle = len(arc) // 2
                return [self.boundary.point(w) for w in arc[:middle + 1]], [self.boundary.point(w) for w in arc[middle:][::-1]]
        return [], []

    def _junction_cap(self, chord, junction):
        """Extend past the last clean chord, under the stroke that crosses here."""
        info = self.clusters.info[junction]
        to_node = info["pos"] - chord.mid
        distance = np.linalg.norm(to_node)
        target = info["r"] * END_OVERLAP if info["has_pass"] else 0.0
        move = to_node / (distance + 1e-9) * max(distance - target, 0.0)
        left, right = self.boundary.pts[chord.left] + move, self.boundary.pts[chord.right] + move
        return [(float(left[0]), float(left[1]))], [(float(right[0]), float(right[1]))]

    def _rungs(self, chords, closed):
        """Both contacts must advance. A shared contact makes a zero-length rail section, which InkStitch drops."""
        rungs, next_s, previous = [], -math.inf, (None, None)
        for index, chord in enumerate(chords):
            due = chord.s >= next_s or index == len(chords) - 1
            if due and chord.left != previous[0] and chord.right != previous[1]:
                rungs.append((self.boundary.point(chord.left), self.boundary.point(chord.right)))
                previous = (chord.left, chord.right)
                next_s = chord.s + RUNG_STEP
        return rungs[1:] if closed and len(rungs) > 2 else rungs

    @staticmethod
    def _mark_straight(stroke, chords):
        mids = np.array([c.mid for c in chords])
        span = mids[-1] - mids[0]
        length = np.linalg.norm(span)
        if len(chords) < 4 or length < 1:
            return
        u = span / length
        n = np.array([-u[1], u[0]])
        if np.abs((mids - mids[0]) @ n).max() > STRAIGHT_LIMIT * stroke.width:
            return
        region = Polygon(stroke.left + stroke.right[::-1]).buffer(0)
        if isinstance(region, MultiPolygon):
            region = max(region.geoms, key=lambda g: g.area)
        if not region.is_empty:
            stroke.axis, stroke.region = (float(u[0]), float(u[1])), region
