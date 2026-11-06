"""Build InkStitch lettering font folders from OTF, render via lib.lettering.Font, export stitches as JSON."""
import sys, os, json, math, time, traceback
import importlib.abc, importlib.machinery, types
class _Dummy:
    def __init__(self, *a, **k): pass
    def __getattr__(self, n): return _Dummy()
    def __call__(self, *a, **k): return _Dummy()
class _WxMod(types.ModuleType):
    __path__ = []
    def __getattr__(self, n):
        if n.startswith('__'): raise AttributeError(n)
        return type(n, (_Dummy,), {})
class _WxFinder(importlib.abc.MetaPathFinder, importlib.abc.Loader):
    def find_spec(self, name, path=None, target=None):
        if name == 'wx' or name.startswith('wx.'):
            return importlib.machinery.ModuleSpec(name, self, is_package=True)
    def create_module(self, spec): return _WxMod(spec.name)
    def exec_module(self, m): pass
sys.meta_path.insert(0, _WxFinder())
REPO = '/Users/suckzoo/tmp/InkStitch'
sys.path.insert(0, REPO); sys.path.insert(0, os.path.dirname(__file__))
sys.dont_write_bytecode = True
import numpy as np
import shapely
import inkex
from shapely.geometry import LineString, MultiPolygon
from shapely.ops import unary_union
import strokes as ST
import pillar as PL
from strokes import TTFont, glyph_strokes
from lib.lettering import Font
from lib.elements.utils.nodes import nodes_to_elements
from lib.elements import SatinColumn
from lib.svg.tags import EMBROIDERABLE_TAGS
from lib.stitch_plan import stitch_groups_to_stitch_plan

PX_MM = 96/25.4
FD = os.path.expanduser('~/Downloads/CookieRunFont_OTF')
OUT = os.path.join(os.path.dirname(__file__), 'out'); os.makedirs(OUT, exist_ok=True)
CHARS = '가감꺪앙'; WEIGHTS = ['Regular', 'Bold', 'Black']; SIZES = [30, 15]
AUTO_SATIN = '--auto-satin' in sys.argv


def flip(s):
    s['left'], s['right'] = s['left'][::-1], s['right'][::-1]
    s['rungs'] = s['rungs'][::-1]


def order_strokes(strokes):
    """Terminating strokes first, the stroke that passes through the junction on top."""
    n = len(strokes); before = {i: set() for i in range(n)}
    for i, s in enumerate(strokes):
        for j in s['ends']:
            if j is None: continue
            for k, o in enumerate(strokes):
                if k != i and j in o['passes']: before[k].add(i)
    done, out = set(), []; pos = None
    while len(out) < n:
        ready = [i for i in range(n) if i not in done and before[i] <= done] or [i for i in range(n) if i not in done]
        def d(i):
            p = strokes[i]['left'][0] if strokes[i]['left'] else (0, 0)
            return 0 if pos is None else math.dist(pos, p)
        def d2(i):
            s = strokes[i]
            if pos is None or not s['left']: return 0
            return min(math.dist(pos, s['left'][0]), math.dist(pos, s['left'][-1]))
        i = min(ready, key=d2); done.add(i); out.append(i)
        s = strokes[i]
        if pos is not None and s['left'] and not s['closed'] and math.dist(pos, s['left'][-1]) < math.dist(pos, s['left'][0]):
            flip(s)
        pos = s['left'][-1] if s['left'] else pos
    return out


def to_d(line, k):
    return 'M ' + ' L '.join(f'{x*k:.3f},{(1000-y)*k:.3f}' for x, y in line)


def extend(u, v, f=0.04):
    u, v = np.array(u), np.array(v); e = (v-u)*f
    return (u-e).tolist(), (v+e).tolist()


def clean_line(line):
    ls = LineString(line).simplify(0.25)
    return list(ls.coords)


def stroke_path(s, k):
    parts = [to_d(clean_line(s['left']), k), to_d(clean_line(s['right']), k)]
    parts += [to_d(extend(u, v), k) for u, v in s['rungs']]
    return ' '.join(parts)


def underlay_attrs(width_mm):
    a = {'contour_underlay': 'True'} if width_mm >= 1.5 else {'center_walk_underlay': 'True'}
    if width_mm >= 4: a['zigzag_underlay'] = 'True'
    a['pull_compensation_mm'] = '0.2'
    return a


def write_font(weight, size, geoms, style):
    k = size/1000*PX_MM
    name = f'cookierun-{weight.lower()}-{size}-{style}'
    d = os.path.join(OUT, 'fonts', name); os.makedirs(d, exist_ok=True)
    W = 1200*k
    svg = [f'<?xml version="1.0" encoding="UTF-8"?>\n<svg xmlns="http://www.w3.org/2000/svg" xmlns:inkscape="http://www.inkscape.org/namespaces/inkscape" '
           f'xmlns:sodipodi="http://sodipodi.sourceforge.net/DTD/sodipodi-0.dtd" xmlns:inkstitch="http://inkstitch.org/namespace" width="{W}" height="{W*1.3}" viewBox="0 0 {W} {W*1.3}">'
           '<metadata><inkstitch:min_stitch_len_mm>0.1</inkstitch:min_stitch_len_mm><inkstitch:collapse_len_mm>3.0</inkstitch:collapse_len_mm>'
           '<inkstitch:inkstitch_svg_version>3</inkstitch:inkstitch_svg_version></metadata>']
    for ch, g in geoms.items():
        svg.append(f'<g inkscape:groupmode="layer" inkscape:label="GlyphLayer-{ch}" id="glyph{ord(ch):x}">')
        for ci, c in enumerate(g['comps']):
            ss = c['strokes']
            for i in order_strokes(ss):
                st = ss[i]
                if not st['left'] or not st['right']: continue
                attrs = ' '.join(f'inkstitch:{a}="{b}"' for a, b in underlay_attrs(st['width']*size/1000).items())
                svg.append(f'<path id="g{ord(ch):x}c{ci}s{i}" inkscape:label="c{ci}s{i}" style="fill:none;stroke:#1f4e79;stroke-width:1" '
                           f'inkstitch:satin_column="True" {attrs} d="{stroke_path(st, k)}"/>')
        svg.append('</g>')
    svg.append('</svg>')
    import pathlib; pathlib.Path(d, 'ltr.svg').write_text('\n'.join(svg), encoding='utf8')
    adv = {ch: round(g['adv']*k, 2) for ch, g in geoms.items()}
    meta = dict(name=f'CookieRun {weight} {size}mm {style} (spike)', description='Auto-generated spike', font_license='', default_variant='ltr',
                text_direction='ltr', keywords=['satin'], leading=100, auto_satin=AUTO_SATIN, reversible=False, sortable=False,
                combine_at_sort_indices=[], letter_case='', default_glyph='가', size=float(size), min_scale=1.0, max_scale=1.0,
                horiz_adv_x_default=round(1000*k, 2), horiz_adv_x_space=round(300*k, 2), units_per_em=round(1000*k, 2),
                horiz_adv_x=adv, kerning_pairs={}, glyphs=list(geoms))
    pathlib.Path(d, 'font.json').write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding='utf8')
    return d


def render_char(font_dir, ch):
    tpl = os.path.join(OUT, 'empty.svg')
    open(tpl, 'w').write('<svg xmlns="http://www.w3.org/2000/svg" xmlns:inkstitch="http://inkstitch.org/namespace" width="400" height="400" viewBox="0 0 400 400"><metadata><inkstitch:min_stitch_len_mm>0.1</inkstitch:min_stitch_len_mm><inkstitch:collapse_len_mm>3.0</inkstitch:collapse_len_mm><inkstitch:inkstitch_svg_version>3</inkstitch:inkstitch_svg_version></metadata></svg>')
    doc = inkex.load_svg(tpl); root = doc.getroot()
    layer = inkex.Layer(); root.append(layer)
    grp = inkex.Group(); layer.append(grp)
    font = Font(font_dir, show_font_path_warning=False)
    font.render_text(ch, grp, 'ltr', back_and_forth=False)
    elements = nodes_to_elements(grp.iterdescendants(EMBROIDERABLE_TAGS))
    groups_out, all_groups = [], []
    last = None
    for idx, el in enumerate(elements):
        nxt = elements[idx+1] if idx+1 < len(elements) else None
        sgs = el.embroider(last, nxt)
        all_groups.extend(sgs)
        for sg in sgs:
            last = sg
            cur = None
            for st in sg.stitches:
                tags = [str(t) for t in (st.tags or [])]
                is_under = any('underlay' in t for t in tags)
                if cur is None or cur['underlay'] != is_under:
                    if cur is not None:
                        cur['pts'].append((round(st.x/PX_MM, 3), round(st.y/PX_MM, 3)))
                    cur = dict(el=idx, label=el.node.label or el.node.get_id(), kind=type(el).__name__, underlay=is_under, pts=[])
                    groups_out.append(cur)
                cur['pts'].append((round(st.x/PX_MM, 3), round(st.y/PX_MM, 3)))
    plan = stitch_groups_to_stitch_plan(all_groups, collapse_len=3.0*PX_MM, min_stitch_len=0.1*PX_MM)
    return elements, groups_out, plan


def metrics(shape_mm, groups, plan):
    top = [g for g in groups if not g['underlay'] and g['kind'] == 'SatinColumn']
    segs = []
    for g in groups:
        p = np.array(g['pts'])
        if len(p) > 1: segs.append(np.linalg.norm(np.diff(p, axis=0), axis=1))
    L = np.concatenate(segs) if segs else np.array([0.])
    cov_lines = []
    for g in top:
        if len(g['pts']) > 1: cov_lines.append(LineString(g['pts']))
    thread = unary_union([l.buffer(0.2, cap_style='flat') for l in cov_lines]) if cov_lines else None
    pts = np.array([p for g in groups for p in g['pts']])
    cells = {}
    for x, y in pts:
        cells[(int(x//1), int(y//1))] = cells.get((int(x//1), int(y//1)), 0)+1
    dens = max(cells.values()) if cells else 0
    m = dict(density=dens, stitches=int(plan.num_stitches), jumps=int(plan.num_jumps), trims=int(plan.num_trims),
             max_len=float(L.max()), long_over_7=int((L > 7).sum()), long_over_12=int((L > 12).sum()))
    if thread is not None:
        m['coverage'] = float(shape_mm.intersection(thread).area/shape_mm.area)
        un = shape_mm.difference(thread)
        parts = list(un.geoms) if hasattr(un, 'geoms') else [un]
        best = 0.0
        for q in parts:
            if q.geom_type == 'Polygon' and q.area > 0.01:
                best = max(best, 2*shapely.maximum_inscribed_circle(q).length)
        m['gap'] = float(best)
        m['outside'] = float(thread.difference(shape_mm).area/thread.area)
    return m


PILLAR_CACHE = {}


def pillar_regions_mm(w, ch, size, minx):
    from shapely.affinity import affine_transform
    if (w, ch) not in PILLAR_CACHE:
        f = TTFont(f'{FD}/CookieRun {w}.otf')
        _, _, comps = PL.glyph_components(f, ch, True)
        PILLAR_CACHE[(w, ch)] = [p for c in comps for p in c.get('pillars', [])]
    out = []
    for p in PILLAR_CACHE[(w, ch)]:
        reg = affine_transform(p['region'], [size/1000, 0, 0, -size/1000, -minx, size])
        ax = p['axis']
        out.append(dict(region=reg, axis=(ax[0], -ax[1])))
    return out


def stem_deviation(groups, regions):
    '''Stitch angle against the pillar normal, over top stitches whose midpoint is inside the pillar. Degrees.'''
    from shapely.geometry import Point
    devs = []
    for r in regions:
        ax = np.array(r['axis']); core = r['region'].buffer(-0.6)
        for g in groups:
            if g['underlay']: continue
            P = np.array(g['pts'])
            if len(P) < 2: continue
            V = np.diff(P, axis=0); L = np.linalg.norm(V, axis=1); M = (P[:-1]+P[1:])/2
            for v, l, mid in zip(V, L, M):
                if l < 1.0 or not core.contains(Point(mid)): continue
                devs.append(math.degrees(math.asin(min(1, abs(np.dot(v/l, ax))))))
    return dict(p95=round(float(np.percentile(devs, 95)), 1), max=round(float(np.max(devs)), 1)) if devs else None


def main():
    results = []
    for style in ('miter', 'pillar'):
        ST.CORNER_STYLE = 'miter'
        for w in WEIGHTS:
            f = TTFont(f'{FD}/CookieRun {w}.otf')
            geoms = {}
            for ch in CHARS:
                shape, adv, comps = PL.glyph_components(f, ch, style == 'pillar')
                geoms[ch] = dict(shape=shape, adv=adv, comps=comps)
            for size in SIZES:
                d = write_font(w, size, geoms, style)
                for ch in CHARS:
                    g = geoms[ch]; rec = dict(style=style, weight=w, size=size, ch=ch)
                    t0 = time.time()
                    try:
                        els, groups, plan = render_char(d, ch)
                        minx = min(pt[0] for c in g['comps'] for s in c['strokes'] for rail in (s['left'], s['right']) for pt in rail)*size/1000
                        X = lambda x, y: (round(x*size/1000-minx, 2), round((1000-y)*size/1000, 2))
                        from shapely.affinity import affine_transform
                        shp = affine_transform(g['shape'], [size/1000, 0, 0, -size/1000, -minx, size])
                        rec['groups'] = groups
                        rec['metrics'] = metrics(shp, groups, plan)
                        regs = pillar_regions_mm(w, ch, size, minx)
                        rec['stem'] = stem_deviation(groups, regs)
                        rec['pillars'] = len(regs)
                        rec['strokes'] = sum(len(c['strokes']) for c in g['comps'])
                        rec['components'] = len(g['comps'])
                        polys = list(shp.geoms) if shp.geom_type == 'MultiPolygon' else [shp]
                        rec['outline'] = [[[(round(x, 2), round(y, 2)) for x, y in r.coords] for r in [p.exterior]+list(p.interiors)] for p in polys]
                        rec['rails'] = []
                        for c in g['comps']:
                            for s in c['strokes']:
                                T = lambda L: [X(*p) for p in L]
                                rec['rails'].append(dict(left=T(clean_line(s['left'])), right=T(clean_line(s['right'])), rungs=[T(r) for r in s['rungs']], width=round(s['width']*size/1000, 2)))
                    except Exception:
                        rec['error'] = traceback.format_exc()
                    rec['secs'] = round(time.time()-t0, 2)
                    m = rec.get('metrics') or {}
                    print(style, w, size, ch, 'n', rec.get('strokes'), {k: (round(v, 3) if isinstance(v, float) else v) for k, v in m.items()}, rec['secs'], (rec.get('error') or '')[-400:], flush=True)
                    results.append(rec)
    with open(os.path.join(OUT, 'results.json'), 'w') as fh:
        json.dump(results, fh, ensure_ascii=False)


def clean_cast(l):
    return clean_line(l)


if __name__ == '__main__':
    main()
