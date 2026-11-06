"""Spike: glyph outline -> strokes (medial axis + chords) -> satin rails/rungs. Units: font units, y-up."""
import math
from collections import defaultdict
import numpy as np
import networkx as nx
import shapely
from shapely.geometry import Polygon, MultiPolygon, LineString, Point
from shapely.ops import unary_union
from scipy.spatial import Voronoi
from fontTools.ttLib import TTFont
from fontTools.pens.recordingPen import DecomposingRecordingPen

DS = 3.0            # boundary sample spacing, font units
RATIO = 1.7         # chord kept if along-boundary/euclid > RATIO
RUNG_STEP = 30.0
STRAIGHT_DEG = 40.0
JUNCTION_CLEAR = 1.15
CORNER_STYLE = 'fan'
END_OVERLAP = 0.2   # terminating stroke ends at this * junction radius from junction centre


def glyph_shape(font, ch):
    gs = font.getGlyphSet(); name = font.getBestCmap()[ord(ch)]
    pen = DecomposingRecordingPen(gs); gs[name].draw(pen)
    contours, cur = [], []
    for op, a in pen.value:
        if op == 'moveTo': cur = [a[0]]
        elif op == 'lineTo': cur.append(a[0])
        elif op == 'curveTo':
            p0 = np.array(cur[-1]); p1, p2, p3 = map(np.array, a)
            for t in np.linspace(0, 1, 17)[1:]:
                cur.append(tuple((1-t)**3*p0+3*(1-t)**2*t*p1+3*(1-t)*t*t*p2+t**3*p3))
        elif op in ('closePath', 'endPath'):
            if len(cur) > 2: contours.append(cur)
            cur = []
    polys = [Polygon(c).buffer(0) for c in contours]
    signed = [0.5*sum(x0*y1-x1*y0 for (x0,y0),(x1,y1) in zip(c,c[1:]+c[:1])) for c in contours]
    sign = np.sign(signed[int(np.argmax(np.abs(signed)))])
    outer = unary_union([p for p, s in zip(polys, signed) if np.sign(s) == sign])
    holes = [p for p, s in zip(polys, signed) if np.sign(s) != sign]
    return outer.difference(unary_union(holes)) if holes else outer, gs[name].width


class Sampler:
    def __init__(self, poly):
        self.rings = [poly.exterior] + list(poly.interiors)
        pts, rid, arc = [], [], []
        self.lengths = []; self.offset = []; self.count = []
        for r, ring in enumerate(self.rings):
            L = ring.length; n = max(8, int(L/DS))
            self.lengths.append(L); self.offset.append(len(pts)); self.count.append(n)
            for i in range(n):
                s = i*L/n
                p = ring.interpolate(s)
                pts.append((p.x, p.y)); rid.append(r); arc.append(s)
        self.pts = np.array(pts); self.rid = np.array(rid); self.arc = np.array(arc)

    def along(self, a, b):
        if self.rid[a] != self.rid[b]: return math.inf
        d = abs(self.arc[a]-self.arc[b]); return min(d, self.lengths[self.rid[a]]-d)

    def walk(self, a, b):
        """Sample ids strictly between a and b taking the short way round."""
        r = self.rid[a]; o = self.offset[r]; n = self.count[r]
        ia, ib = a-o, b-o
        fwd = (ib-ia) % n; back = (ia-ib) % n
        if fwd <= back: return [o+(ia+k) % n for k in range(1, fwd)]
        return [o+(ia-k) % n for k in range(1, back)]


def medial_graph(poly, S):
    vor = Voronoi(S.pts)
    V = vor.vertices
    inside = shapely.contains_xy(poly, V[:, 0], V[:, 1])
    G = nx.Graph()
    for (a, b), (u, v) in zip(vor.ridge_points, vor.ridge_vertices):
        if u < 0 or v < 0 or not inside[u] or not inside[v]: continue
        eu = np.linalg.norm(S.pts[a]-S.pts[b])
        al = S.along(a, b)
        if al <= RATIO*eu: continue
        if not poly.contains(LineString([V[u], V[v]])): continue
        G.add_edge(u, v, sites=(a, b), length=float(np.linalg.norm(V[u]-V[v])))
    for n in G.nodes:
        G.nodes[n]['pos'] = V[n]
        G.nodes[n]['r'] = float(np.min(np.linalg.norm(S.pts-V[n], axis=1)))
    return G


def branches_of(G):
    """list of dict(a,b,nodes=[...]); a==b for loops; cycles without junction return a=b=None"""
    specials = {n for n in G if G.degree(n) != 2}
    out, seen = [], set()
    for s in specials:
        for nb in G[s]:
            if (s, nb) in seen: continue
            path = [s, nb]; seen.add((s, nb))
            while path[-1] not in specials:
                nxt = [x for x in G[path[-1]] if x != path[-2]]
                if not nxt: break
                path.append(nxt[0])
            seen.add((path[-1], path[-2]))
            out.append(dict(a=path[0], b=path[-1], nodes=path))
    # pure cycles
    used = set(n for br in out for n in br['nodes'])
    for comp in nx.connected_components(G):
        if comp & used or comp & specials: continue
        start = next(iter(comp)); path = [start]; prev = None; cur = start
        while True:
            nxt = [x for x in G[cur] if x != prev]
            if not nxt: break
            if nxt[0] == start and len(path) > 2:
                path.append(start); break
            prev, cur = cur, nxt[0]; path.append(cur)
        out.append(dict(a=None, b=None, nodes=path, cycle=True))
    return out


def path_len(G, nodes):
    return sum(np.linalg.norm(G.nodes[a]['pos']-G.nodes[b]['pos']) for a, b in zip(nodes, nodes[1:]))


def prune(G):
    while True:
        changed = False
        for br in branches_of(G):
            if br.get('cycle'): continue
            a, b = br['a'], br['b']
            da, db = G.degree(a), G.degree(b)
            if (da == 1) == (db == 1):
                continue
            j = a if db == 1 else b
            L = path_len(G, br['nodes'])
            if L < 0.5*G.nodes[j]['r']:
                inner = br['nodes'][1:] if j == a else br['nodes'][:-1]
                G.remove_nodes_from(inner); changed = True
        G.remove_nodes_from([n for n in list(G) if G.degree(n) == 0])
        if not changed: return G


def tangent_at(G, nodes, dist):
    p0 = G.nodes[nodes[0]]['pos']; acc = 0; prev = p0
    for n in nodes[1:]:
        p = G.nodes[n]['pos']; acc += np.linalg.norm(p-prev); prev = p
        if acc >= dist: break
    v = prev-p0; return v/(np.linalg.norm(v)+1e-9)


def build_strokes(poly):
    S = Sampler(poly)
    G = prune(medial_graph(poly, S))
    brs = branches_of(G)
    # cluster junctions joined by short branches
    uf = {}
    def find(x):
        uf.setdefault(x, x)
        while uf[x] != x:
            uf[x] = uf[uf[x]]; x = uf[x]
        return x
    for br in brs:
        if br.get('cycle'): continue
        a, b = br['a'], br['b']
        if G.degree(a) >= 3 and G.degree(b) >= 3 and a != b:
            if path_len(G, br['nodes']) < 0.9*max(G.nodes[a]['r'], G.nodes[b]['r']):
                uf[find(a)] = find(b); br['drop'] = True
    brs = [b for b in brs if not b.get('drop')]
    junc = defaultdict(list)   # cluster -> list[(branch idx, end)]
    for i, br in enumerate(brs):
        if br.get('cycle'): continue
        for end, n in (('a', br['a']), ('b', br['b'])):
            if G.degree(n) >= 3: junc[find(n)].append((i, end))
    jinfo = {}
    members = defaultdict(list)
    for n in G:
        if G.degree(n) >= 3: members[find(n)].append(n)
    for c, ms in members.items():
        P = np.array([G.nodes[m]['pos'] for m in ms]); rr = [G.nodes[m]['r'] for m in ms]
        jinfo[c] = dict(pos=P.mean(0), r=max(rr))
    # pair ends
    link = {}  # (branch,end) -> (branch,end)
    for c, ends in junc.items():
        r = jinfo[c]['r']
        cand = []
        dirs = {}
        for (i, e) in ends:
            nodes = brs[i]['nodes'] if e == 'a' else brs[i]['nodes'][::-1]
            dirs[(i, e)] = tangent_at(G, nodes, 1.3*r)
        for x in range(len(ends)):
            for y in range(x+1, len(ends)):
                d = np.clip(np.dot(dirs[ends[x]], -dirs[ends[y]]), -1, 1)
                ang = math.degrees(math.acos(d))
                if ang < STRAIGHT_DEG: cand.append((ang, ends[x], ends[y]))
        for ang, p, q in sorted(cand, key=lambda t: t[0]):
            if p in link or q in link: continue
            if p[0] == q[0]: continue  # loop back onto itself handled as termination
            link[p] = q; link[q] = p
    for c, ends in junc.items():
        jinfo[c]['has_pass'] = any(e in link for e in ends)
    # chain
    strokes = []; used = set()
    def other(e): return 'b' if e == 'a' else 'a'
    for i, br in enumerate(brs):
        if i in used: continue
        if br.get('cycle'):
            used.add(i); strokes.append(dict(seq=[(i, 'a')], cycle=True, ends=(None, None))); continue
        # walk to chain start
        cur = (i, 'a'); visited = {i}; closed = False
        while cur in link:
            j, e = link[cur]; ne = (j, other(e))
            if j in visited: closed = True; break
            visited.add(j); cur = ne
        start = cur if not closed else (i, 'a')
        seq = []; c = start; vis = set()
        while True:
            seq.append(c); vis.add(c[0]); used.add(c[0])
            out_end = (c[0], other(c[1]))
            if out_end in link:
                j, e = link[out_end]
                if j in vis: break
                c = (j, e)
            else: break
        strokes.append(dict(seq=seq, cycle=closed, ends=(start, (seq[-1][0], other(seq[-1][1])))))
    res = []
    for st in strokes:
        res.extend(stroke_geometry(G, S, brs, st, find, jinfo) or [])
    return dict(strokes=res, skeleton=[[G.nodes[n]['pos'].tolist() for n in b['nodes']] for b in brs],
                junctions=[dict(pos=j['pos'].tolist(), r=j['r']) for j in jinfo.values()], S=S)


def stroke_geometry(G, S, brs, st, find, jinfo):
    # ordered node path
    nodes = []
    pass_j = []
    for k, (i, e) in enumerate(st['seq']):
        ns = brs[i]['nodes'] if e == 'a' else brs[i]['nodes'][::-1]
        if nodes:
            pass_j.append(find(nodes[-1]))
            # jump across junction cluster: no chord for the gap
            nodes.append(None)
        nodes.extend(ns)
    start_j = end_j = None
    if not st.get('cycle') or st['ends'][0] is not None:
        n0 = next(n for n in nodes if n is not None); n1 = next(n for n in reversed(nodes) if n is not None)
        if G.degree(n0) >= 3: start_j = find(n0)
        if G.degree(n1) >= 3: end_j = find(n1)
    if st.get('cycle') and start_j is not None and start_j == end_j:
        pass_j.append(start_j); 
    # chords
    chords = []; L = 0
    for u, v in zip(nodes, nodes[1:]):
        if u is None or v is None: continue
        a, b = G[u][v]['sites']
        pu, pv = G.nodes[u]['pos'], G.nodes[v]['pos']
        t = pv-pu; mid = (pu+pv)/2
        ca = t[0]*(S.pts[a][1]-mid[1])-t[1]*(S.pts[a][0]-mid[0])
        left, right = (a, b) if ca > 0 else (b, a)
        chords.append(dict(mid=mid, left=left, right=right, s=L, t=t))
        L += np.linalg.norm(t)
    if L < 1e-6 or not chords: return None
    # drop only the chords distorted by a junction: flared or rotated ones close to it
    jset = set(pass_j) | {j for j in (start_j, end_j) if j is not None}
    W = lambda c: np.linalg.norm(S.pts[c['left']]-S.pts[c['right']])
    med = float(np.median([W(c) for c in chords]))
    # smooth tangent over about one stroke half-width: single Voronoi edges are noisy
    mids = np.array([c['mid'] for c in chords]); ss = np.array([c['s'] for c in chords])
    for idx, c in enumerate(chords):
        lo = np.searchsorted(ss, c['s']-0.4*med); hi = min(np.searchsorted(ss, c['s']+0.4*med), len(chords)-1)
        c['ts'] = mids[hi]-mids[min(lo, len(chords)-1)]
    def clean(c):
        for j in jset:
            if np.linalg.norm(c['mid']-jinfo[j]['pos']) < 1.6*jinfo[j]['r']:
                chord = S.pts[c['left']]-S.pts[c['right']]
                t = c['ts']/(np.linalg.norm(c['ts'])+1e-9)
                skew = abs(np.dot(chord/(np.linalg.norm(chord)+1e-9), t))
                if W(c) > 1.12*med or skew > 0.15:
                    return False
        return True
    kept = [c for c in chords if clean(c)]
    if len(kept) < 2:
        def score(c):
            ch = S.pts[c['left']]-S.pts[c['right']]; t = c['ts']/(np.linalg.norm(c['ts'])+1e-9)
            return abs(np.dot(ch/(np.linalg.norm(ch)+1e-9), t))
        best = sorted(chords, key=score)[:max(2, len(chords)//3)]
        kept = sorted(best, key=lambda c: c['s'])
    closed = bool(st.get('cycle')) and start_j is None and end_j is None
    corners = detect_corners(S, kept, med) if CORNER_STYLE == 'miter' else []
    if closed and corners:
        # rotate so the first corner is the chain start; the seam becomes a mitre
        i0 = corners[0]['k']
        n = len(kept)
        rotated = kept[i0:]+kept[:i0]
        remap = []
        for c in corners[1:]+[dict(corners[0], i=corners[0]['i']+n, k=corners[0]['k']+n)]:
            remap.append(dict(c, i=c['i']-i0, k=c['k']-i0, geom=corner_geom(S, kept, c if c is not corners[0] else corners[0], med) if c['k'] < n else corner_geom(S, kept, corners[0], med)))
        last = remap[-1]
        pieces = piece_ranges(rotated, remap[:-1], dict(kind='miter_start', **corner_geom(S, kept, corners[0], med)),
                              dict(kind='miter_end', **corner_geom(S, kept, corners[0], med)), last)
    elif corners:
        pieces = piece_ranges(kept, corners, cap_of(start_j), cap_of(end_j), None, S=S, base=kept, med=med)
    else:
        seam = dict(kind='seam') if closed else None
        pieces = [(kept, seam or cap_of(start_j), seam or cap_of(end_j))]
    out = []
    for chs, c0, c1 in pieces:
        if len(chs) == 0: continue
        out.append(make_piece(S, chs, c0, c1, jinfo, closed and not corners, pass_j, start_j, end_j, med))
    return [o for o in out if o and len(o['left']) > 1 and len(o['right']) > 1]


def cap_of(j):
    return dict(kind='free') if j is None else dict(kind='junction', j=j)


def detect_corners(S, kept, med):
    """A corner: one contact point stays pinned while the chord rotates by more than 50 degrees."""
    n = len(kept); tol = 0.12*med; out = []; i = 0
    dirs = [S.pts[c['right']]-S.pts[c['left']] for c in kept]
    def rot(a, b):
        return abs(math.degrees(math.atan2(dirs[a][0]*dirs[b][1]-dirs[a][1]*dirs[b][0], float(np.dot(dirs[a], dirs[b])))))
    while i < n-1:
        found = None
        for side in ('left', 'right'):
            k = i; best = None
            while k+1 < n and S.along(kept[i][side], kept[k+1][side]) <= tol:
                k += 1
                if rot(i, k) >= 50: best = k
            if best is not None and (found is None or best > found[1]):
                found = (side, k)
        if found:
            lo = out[-1]['k']+1 if out else 0
            a = i
            while a-1 >= lo and rot(max(a-4, lo), a) > 4: a -= 1
            b = found[1]
            while b+1 < n and rot(b, min(b+4, n-1)) > 4: b += 1
            out.append(dict(i=a, k=b, side=found[0])); i = b+1
        else:
            i += 1
    return out


def corner_geom(S, kept, c, med):
    inner = c['side']; outer = 'right' if inner == 'left' else 'left'
    P = S.pts[kept[(c['i']+c['k'])//2][inner]]
    o0, o1 = kept[c['i']][outer], kept[c['k']][outer]
    seq = [o0]+list(S.walk(o0, o1))+[o1]
    q = max(seq, key=lambda w: np.linalg.norm(S.pts[w]-P))
    iq = seq.index(q)
    return dict(inner=inner, outer=outer, P=P.tolist(), Q=S.pts[q].tolist(),
                before=[S.pts[w].tolist() for w in seq[1:iq]], after=[S.pts[w].tolist() for w in seq[iq+1:-1]])


def piece_ranges(kept, corners, c0, c1, last, S=None, base=None, med=None):
    """Cut chords at corners. Without S the corner dicts already hold rotated indices (closed stroke)."""
    pieces = []; start = 0; cap = c0
    if S is None:
        S_ = None
    for c in corners:
        g = c['geom'] if 'geom' in c else corner_geom(S, base, c, med)
        pieces.append((kept[start:c['i']+1], cap, dict(kind='miter_end', **g)))
        cap = dict(kind='miter_start', **g); start = c['k']
    tail_end = last['i']+1 if last else len(kept)
    pieces.append((kept[start:tail_end], cap, c1))
    return pieces


def make_piece(S, kept, c0, c1, jinfo, closed, pass_j, start_j, end_j, med):
    def rail(side):
        pts = []; last = None
        for c in kept:
            s = c[side]
            if s == last: continue
            if last is not None:
                eu = np.linalg.norm(S.pts[s]-S.pts[last]); al = S.along(last, s)
                if al <= max(1.6*eu, 4*DS):
                    pts.extend(S.pts[w].tolist() for w in S.walk(last, s))
            pts.append(S.pts[s].tolist()); last = s
        return pts
    Lr, Rr = rail('left'), rail('right')
    first, last = kept[0], kept[-1]
    def cap_points(chord, cap):
        l, r = S.pts[chord['left']], S.pts[chord['right']]
        kind = cap['kind']
        if kind == 'junction':
            node = jinfo[cap['j']]['pos']; d = node-chord['mid']; dist = np.linalg.norm(d)
            target = jinfo[cap['j']]['r']*(END_OVERLAP if jinfo[cap['j']].get('has_pass') else 0.0)
            mv = d/(dist+1e-9)*max(dist-target, 0)
            return [(l+mv).tolist()], [(r+mv).tolist()]
        if kind == 'free':
            if S.along(chord['left'], chord['right']) == math.inf: return [], []
            arc = S.walk(chord['left'], chord['right'])
            if not arc: return [], []
            m = len(arc)//2
            return [S.pts[w].tolist() for w in arc[:m+1]], [S.pts[w].tolist() for w in arc[m:][::-1]]
        if kind == 'seam':
            return [l.tolist()], [r.tolist()]
        return None
    if closed:
        Lr.append(S.pts[first['left']].tolist()); Rr.append(S.pts[first['right']].tolist())
    else:
        # start
        if c0['kind'] == 'miter_start':
            inner = [c0['Q'], c0['P']]; outer = [c0['Q']]+c0['after']
            if c0['inner'] == 'left': Lr, Rr = inner+Lr, outer+Rr
            else: Lr, Rr = outer+Lr, inner+Rr
        else:
            a, b = cap_points(first, c0); Lr, Rr = a[::-1]+Lr, b[::-1]+Rr
        # end
        if c1['kind'] == 'miter_end':
            inner = [c1['P'], c1['Q']]; outer = c1['before']+[c1['Q']]
            if c1['inner'] == 'left': Lr, Rr = Lr+inner, Rr+outer
            else: Lr, Rr = Lr+outer, Rr+inner
        else:
            a, b = cap_points(last, c1); Lr, Rr = Lr+a, Rr+b
    rungs = []; next_s = -1e9; prev = (None, None)
    for idx, c in enumerate(kept):
        # both ends must advance: a shared contact point would make a zero-length
        # rail section, and InkStitch drops that section (see flattened_sections)
        force = idx == len(kept)-1
        if (c['s'] >= next_s or force) and c['left'] != prev[0] and c['right'] != prev[1]:
            rungs.append((S.pts[c['left']].tolist(), S.pts[c['right']].tolist()))
            prev = (c['left'], c['right'])
            next_s = c['s']+RUNG_STEP
    if closed and len(rungs) > 2:
        rungs = rungs[1:]   # no rung on the seam
    width = float(np.median([np.linalg.norm(S.pts[c['left']]-S.pts[c['right']]) for c in kept]))
    return dict(left=Lr, right=Rr, rungs=rungs, closed=closed, width=width,
                passes=[int(j) for j in pass_j],
                ends=[None if start_j is None else int(start_j), None if end_j is None else int(end_j)],
                center=[c['mid'].tolist() for c in kept])


def glyph_strokes(font, ch):
    shape, adv = glyph_shape(font, ch)
    polys = list(shape.geoms) if isinstance(shape, MultiPolygon) else [shape]
    out = []
    for comp, poly in enumerate(sorted(polys, key=lambda p: (-p.bounds[3], p.bounds[0]))):
        r = build_strokes(poly); r['poly'] = poly; r['comp'] = comp; out.append(r)
    return shape, adv, out
