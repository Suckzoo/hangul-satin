"""Pillar-first decomposition prototype. A pillar is a straight stroke with a branch: one of its long sides
is interrupted by a gap and continues collinearly. Pillars are sewn straight; what remains is sewn into them."""
import math
import numpy as np
from shapely.geometry import Polygon, MultiPolygon, LineString, Point
from shapely.ops import unary_union
import strokes as ST

MIN_EDGE = 18.0; ANGLE_DEG = 15.0; COLLINEAR = 8.0
SCAN_STEP = 5.0; RUNG_STEP = 35.0; OVERLAP = 12.0; OPEN = 4.0; MIN_RESIDUAL = 300.0


def boundary_edges(poly):
    out = []; s = math.sin(math.radians(ANGLE_DEG))
    for ring in [poly.exterior]+list(poly.interiors):
        c = list(ring.simplify(1.5).coords)
        for p, q in zip(c, c[1:]):
            p, q = np.array(p), np.array(q); v = q-p; L = float(np.linalg.norm(v))
            if L < MIN_EDGE: continue
            if abs(v[0])/L <= s: o = 'V'; al, cr = 1, 0
            elif abs(v[1])/L <= s: o = 'H'; al, cr = 0, 1
            else: continue
            n = np.array([-v[1], v[0]])/L; mid = (p+q)/2
            inward = n if poly.contains(Point(*(mid+n*2))) else -n
            side = 'lo' if inward[cr] > 0 else 'hi'
            a, b = (p, q) if p[al] < q[al] else (q, p)
            out.append(dict(o=o, side=side, a0=a[al], a1=b[al], c0=a[cr], c1=b[cr], L=L))
    return out


def group_collinear(edges):
    groups = []
    for e in sorted(edges, key=lambda e: -e['L']):
        m = (e['c1']-e['c0'])/(e['a1']-e['a0']+1e-9); placed = False
        for g in groups:
            if g['o'] != e['o'] or g['side'] != e['side']: continue
            mid = (e['a0']+e['a1'])/2; pred = g['b']+g['m']*mid; own = (e['c0']+e['c1'])/2
            overlap = any(min(e['a1'], x['a1'])-max(e['a0'], x['a0']) > 5 for x in g['edges'])
            if abs(pred-own) <= COLLINEAR and not overlap:
                g['edges'].append(e); placed = True; break
        if not placed:
            groups.append(dict(o=e['o'], side=e['side'], m=m, b=e['c0']-m*e['a0'], edges=[e]))
    for g in groups:
        A = [x for e in g['edges'] for x in (e['a0'], e['a1'])]; C = [x for e in g['edges'] for x in (e['c0'], e['c1'])]
        if len(g['edges']) > 1:
            g['m'], g['b'] = np.polyfit(A, C, 1)
        g['a0'], g['a1'] = min(A), max(A); g['pieces'] = len(g['edges'])
    return groups


def strip(lo, hi, a0, a1, o, grow=0.0):
    at = lambda g, a: g['b']+g['m']*a
    pts = [(a0, at(lo, a0)-grow), (a1, at(lo, a1)-grow), (a1, at(hi, a1)+grow), (a0, at(hi, a0)+grow)]
    if o == 'V': pts = [(c, a) for a, c in pts]
    return Polygon(pts).buffer(0)


def find_pillars(poly):
    groups = group_collinear(boundary_edges(poly)); out = []
    for o in ('V', 'H'):
        los = [g for g in groups if g['o'] == o and g['side'] == 'lo']
        his = [g for g in groups if g['o'] == o and g['side'] == 'hi']
        cands = []
        for lo in los:
            for hi in his:
                if lo['pieces'] < 2 and hi['pieces'] < 2: continue
                a0, a1 = max(lo['a0'], hi['a0']), min(lo['a1'], hi['a1'])
                if a1-a0 < 30: continue
                mid = (a0+a1)/2; w = (hi['b']+hi['m']*mid)-(lo['b']+lo['m']*mid)
                if w <= 15: continue
                span0, span1 = min(lo['a0'], hi['a0']), max(lo['a1'], hi['a1'])
                if (span1-span0)/w < 1.3: continue
                span = span1-span0
                share = sorted(sum(e['a1']-e['a0'] for e in g['edges'])/span for g in (lo, hi))
                if share[1] < 0.7 or share[0] < 0.2: continue
                # a true pillar has one long straight side; a curved ring only has short near-straight runs
                longest = max(e['a1']-e['a0'] for g in (lo, hi) for e in g['edges'])
                if longest < 0.6*span: continue
                # the interruption must be a real branch, not a kink in one straight side
                def max_gap(g):
                    es = sorted(g['edges'], key=lambda e: e['a0'])
                    return max([b['a0']-a['a1'] for a, b in zip(es, es[1:])] or [0])
                if max(max_gap(lo), max_gap(hi)) < 0.4*w: continue
                st = strip(lo, hi, a0, a1, o)
                if st.is_empty or st.intersection(poly).area/st.area < 0.92: continue
                cands.append((w, lo, hi))
        used = set()
        for w, lo, hi in sorted(cands, key=lambda c: c[0]):
            if id(lo) in used or id(hi) in used: continue
            used.add(id(lo)); used.add(id(hi))
            out.append(dict(o=o, lo=lo, hi=hi, width=w))
    # a horizontal pillar never cuts through a vertical one
    v = [p for p in out if p['o'] == 'V']
    res = list(v)
    for p in [p for p in out if p['o'] == 'H']:
        if not v: res.append(p)
    return res


def pillar_region(poly, p):
    (x0, y0, x1, y1) = poly.bounds
    a0, a1 = (y0-50, y1+50) if p['o'] == 'V' else (x0-50, x1+50)
    st = strip(p['lo'], p['hi'], a0, a1, p['o'], grow=0.5)
    r = st.intersection(poly)
    if isinstance(r, MultiPolygon): r = max(r.geoms, key=lambda g: g.area)
    return r


def axis_of(p):
    m = (p['lo']['m']+p['hi']['m'])/2
    u = np.array([m, 1.0]) if p['o'] == 'V' else np.array([1.0, m])
    return u/np.linalg.norm(u)


def scan_satin(region, u):
    """Rails and rungs from slicing the region across axis u: every stitch is perpendicular to u."""
    n = np.array([-u[1], u[0]])
    co = [np.array(c) for c in region.exterior.coords]
    ts = [float(np.dot(c, u)) for c in co]; ns = [float(np.dot(c, n)) for c in co]
    t0, t1 = min(ts), max(ts); s0, s1 = min(ns)-5, max(ns)+5
    left, right, rungs, widths = [], [], [], []; last_rung = -1e9
    for t in np.arange(t0+0.3, t1, SCAN_STEP):
        cut = LineString([u*t+n*s0, u*t+n*s1]).intersection(region)
        if cut.is_empty: continue
        seg = max(cut.geoms, key=lambda g: g.length) if hasattr(cut, 'geoms') else cut
        if seg.geom_type != 'LineString' or seg.length < 0.5: continue
        a, b = np.array(seg.coords[0]), np.array(seg.coords[-1])
        if np.dot(a, n) > np.dot(b, n): a, b = b, a
        left.append(a.tolist()); right.append(b.tolist()); widths.append(seg.length)
        if t-last_rung >= RUNG_STEP:
            rungs.append((a.tolist(), b.tolist())); last_rung = t
    if len(left) < 2: return None
    # rungs sit inside the rail span and number at least 3: a rung on a rail end can miss the rail after
    # rounding, and then rail_indices (satin_column.py) takes the longest paths, which here may be rungs
    n_r = len(left)
    want = max(3, len(rungs))
    idx = [int(round(x)) for x in np.linspace(0.1*(n_r-1), 0.9*(n_r-1), min(want, n_r))]
    rungs = [(left[i], right[i]) for i in sorted(set(idx))]
    return dict(left=left, right=right, rungs=rungs, closed=False, width=float(np.median(widths)), passes=[], ends=[None, None], center=[])


def region_of(s):
    try:
        r = Polygon(s['left']+s['right'][::-1]).buffer(0)
    except Exception:
        return None
    if isinstance(r, MultiPolygon): r = max(r.geoms, key=lambda g: g.area)
    return r if not r.is_empty else None


def straighten(strokes):
    '''Replace chord-based pieces with parallel stitches when the piece is straight. Curved pieces stay radial.'''
    out = []
    for s in strokes:
        c = np.array(s.get('center') or [])
        if s['closed'] or len(c) < 4:
            out.append(s); continue
        d = c[-1]-c[0]; L = np.linalg.norm(d)
        if L < 1: out.append(s); continue
        u = d/L; n = np.array([-u[1], u[0]])
        if np.abs((c-c[0])@n).max() > 0.2*s['width']:
            out.append(s); continue
        reg = region_of(s); ns = scan_satin(reg, u) if reg is not None else None
        if ns and scan_width(ns) <= 1.35*s['width']:
            ns['passes'], ns['ends'] = s['passes'], s['ends']; ns['axis'] = u.tolist(); ns['region'] = reg
            out.append(ns)
        else:
            out.append(s)
    return out


def fill_residual(strokes, poly):
    '''Uncovered pieces join a neighbouring straight stroke, or become a patch sewn under it.'''
    regs = [s.get('region') if s.get('region') is not None else region_of(s) for s in strokes]
    valid = [r for r in regs if r is not None]
    if not valid: return strokes
    rest = poly.difference(unary_union([r.buffer(0.5) for r in valid])).buffer(-OPEN).buffer(OPEN)
    patches = []
    for part in (list(rest.geoms) if hasattr(rest, 'geoms') else [rest]):
        if part.is_empty or part.geom_type != 'Polygon' or part.area < MIN_RESIDUAL/3: continue
        cand = [i for i, s in enumerate(strokes) if s.get('axis') is not None and regs[i] is not None and regs[i].distance(part) < 2]
        if not cand: continue
        i = max(cand, key=lambda k: regs[k].buffer(1).intersection(part.boundary).length)
        u = np.array(strokes[i]['axis'])
        grown = part.buffer(OVERLAP, join_style=2).intersection(poly)
        if isinstance(grown, MultiPolygon): grown = max(grown.geoms, key=lambda g: g.area)
        merged = unary_union([regs[i], grown])
        ns = scan_satin(merged, u) if merged.geom_type == 'Polygon' and not merged.interiors else None
        if ns and scan_width(ns) <= 1.2*scan_width(strokes[i]):
            ns.update(passes=strokes[i]['passes'], ends=strokes[i]['ends'], axis=strokes[i]['axis'], region=merged)
            strokes[i] = ns; regs[i] = merged
        else:
            ps = scan_satin(grown, u)
            if ps and scan_width(ps) <= 1.2*strokes[i]['width']:
                ps['patch'] = True; ps['axis'] = strokes[i]['axis']; ps['region'] = grown
                patches.append(ps)
    return patches+strokes


def grow_along(part, u, d):
    '''Extend a part only along the sewing axis, so it tucks under the pillar without picking up slivers.'''
    from shapely.affinity import translate
    return unary_union([part, translate(part, *(u*d)), translate(part, *(-u*d))]).convex_hull.intersection(part.buffer(d, join_style=2))


def scan_width(s):
    return max(math.dist(a, b) for a, b in zip(s['left'], s['right']))


def build_component(poly, use_pillars=True):
    pillars = find_pillars(poly) if use_pillars else []
    if not pillars:
        r = ST.build_strokes(poly); r['pillars'] = []
        if use_pillars:
            r['strokes'] = fill_residual(straighten(r['strokes']), poly)
        return r
    regs = [pillar_region(poly, p) for p in pillars]
    strokes = []
    residual = poly.difference(unary_union([g.buffer(0.1) for g in regs])).buffer(-OPEN).buffer(OPEN)
    parts = list(residual.geoms) if hasattr(residual, 'geoms') else [residual]
    for part in parts:
        if part.is_empty or part.area < MIN_RESIDUAL: continue
        near = min(range(len(regs)), key=lambda i: regs[i].distance(part))
        if regs[near].distance(part) > 1: continue
        u_p = axis_of(pillars[near]); u = np.array([-u_p[1], u_p[0]])
        grown = grow_along(part, u, OVERLAP).intersection(poly)
        if isinstance(grown, MultiPolygon): grown = max(grown.geoms, key=lambda g: g.area)
        s = scan_satin(grown, u)
        if s:
            s['ends'] = [-1-near, None]; s['axis'] = u.tolist(); s['region'] = grown; strokes.append(s)
    for i, (p, g) in enumerate(zip(pillars, regs)):
        s = scan_satin(g, axis_of(p))
        if s:
            s['passes'] = [-1-i]; s['axis'] = axis_of(p).tolist(); s['region'] = g; strokes.append(s)
    return dict(strokes=strokes, skeleton=[], junctions=[], pillars=[dict(region=g, axis=axis_of(p).tolist(), o=p['o']) for p, g in zip(pillars, regs)])


def glyph_components(font, ch, use_pillars=True):
    shape, adv = ST.glyph_shape(font, ch)
    polys = list(shape.geoms) if isinstance(shape, MultiPolygon) else [shape]
    out = []
    for comp, poly in enumerate(sorted(polys, key=lambda p: (-p.bounds[3], p.bounds[0]))):
        r = build_component(poly, use_pillars); r['poly'] = poly; r['comp'] = comp; out.append(r)
    return shape, adv, out
