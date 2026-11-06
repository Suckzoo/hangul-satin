# 한글 폰트 자동 satin 경로 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** TTF/OTF 한글 폰트에서 전문가 요구 5건을 만족하는 InkStitch lettering 폰트 폴더를 자동으로 만들고, 실패 글자를 표시한다.

**Architecture:** 외곽선에서 직선 변을 분석해서 기둥을 먼저 찾고, 기둥과 남은 영역은 축에 수직으로 잘라서 평행 stitch로 만든다. 기둥이 없는 요소는 Voronoi centerline으로 처리한다. 결과는 기존 `SatinColumn`이 읽는 path로 쓰므로 stitch 엔진은 수정하지 않는다.

**Tech Stack:** Python 3.13, shapely 2, scipy(Voronoi, 신규 dependency), networkx, fontTools, pytest.

**Spec:** `docs/superpowers/specs/2026-11-06-hangul-auto-satin-design.md`

**Prototype(이식 원본):** `docs/superpowers/prototypes/hangul-satin/`. 이 코드는 동작을 확인한 임시 코드다. 그대로 복사하지 말고 아래 interface에 맞추어 옮긴다. 마지막 task에서 삭제한다.

**비교 페이지:** https://claude.ai/artifact/5QEkY6KDpi8ekfvUG91BD7

## Global Constraints

- CookieRun 폰트와 그 파생물을 저장소에 커밋하지 않는다. 커밋하는 테스트는 합성 polygon만 쓴다.
- 실제 폰트 테스트는 환경 변수 `INKSTITCH_TEST_FONT_DIR`이 있을 때만 실행하고, 없으면 skip한다.
- 길이 상수는 em 1000 기준 값이다. 코드에서 `unitsPerEm / 1000`으로 환산한다.
- InkStitch 코드는 수정하지 않는다. 별도 checkout을 `INKSTITCH_PATH`(기본값 `~/tmp/InkStitch`)로 읽는다.
- 각 commit 전에 `flake8 --max-complexity=10 --max-line-length=150`을 통과한다.
- 합격 기준: 최대 빈틈 지름 0.5mm 이하, 기둥 stitch 기울기 p95 ≤ atan(0.4 ÷ 폭 mm) + 1.5°, 최장 stitch 7mm 이하 또는 분할.
- 개발 환경: `uv venv --python 3.13`, `uv pip install --no-deps "inkex @ git+https://gitlab.com/CapellanCitizen/extensions.git@a887f9d4c8adacd62786e4f46c8ef1467bedc1df"`, 이후 InkStitch `requirements.txt`의 나머지와 scipy, pytest, flake8을 설치한다. inkex의 `pygobject` 의존성은 이 macOS 환경에서 빌드에 실패한다. 2026-11-06에 이 환경에서 `pytest tests/lettering`은 4건 모두 통과했다.

## Review Focus

- `unitsPerEm`이 2048인 TTF: em 1000 폰트와 같은 비율의 결과가 나와야 한다. (Task 2 테스트)
- 폰트에 없는 글자 또는 빈 글리프: 오류로 중단하지 않고 해당 글자를 실패 목록에 넣는다. (Task 7 테스트)
- 곁획 길이보다 높이가 큰 짧은 곁획: InkStitch가 rung을 rail로 읽지 않아야 한다. (Task 1 테스트)
- 15° 넘게 기운 이탤릭체: 잘못된 기둥을 만들지 않고 centerline 경로로 간다. (Task 2 테스트)
- 굵어서 구멍이 거의 없는 글자: 기둥을 찾지 못해도 빈틈 기준을 위반하면 실패로 표시한다. (Task 5 테스트)

## File Structure

```
hangul_satin/
  __init__.py
  types.py        SatinStroke 자료형
  outline.py      글리프 → shapely polygon, unitsPerEm 환산
  scan_satin.py   영역 + 축 → SatinStroke
  pillars.py      직선 변 분석과 기둥 판정
  medial.py       Voronoi centerline, 고리, miter 모서리
  compose.py      요소 하나의 획 조립, 빈틈 처리, 수놓는 순서
  metrics.py      품질 지표와 판정
  font_writer.py  font.json과 ltr.svg 출력
hangul-satin   CLI
tests/
  shapes.py       합성 polygon (T형, 왼쪽 H형, 고리, ㅁ형, ㄱ형)
  test_*.py
```

---

### Task 1: SatinStroke와 scan satin

**Files:**
- Create: `hangul_satin/__init__.py`, `types.py`, `scan_satin.py`
- Create: `tests/__init__.py`, `shapes.py`, `test_scan_satin.py`
- Modify: `pyproject.toml`

**Interfaces:**
- Produces: `SatinStroke` dataclass: `left: list[Point]`, `right: list[Point]`, `rungs: list[tuple[Point, Point]]`, `closed: bool`, `width: float`, `axis: tuple[float, float] | None`, `region: Polygon | None`, `under: set[int]`, `over: set[int]` (`Point = tuple[float, float]`, 단위는 em 1000 좌표)
- Produces: `scan_satin(region: Polygon, axis: tuple[float, float], step: float = 5.0, rung_step: float = 35.0) -> SatinStroke | None`

- [ ] **Step 1: Write the failing tests**

```python
def test_rectangle_rungs_are_perpendicular_to_axis():
    s = scan_satin(box(0, 0, 100, 400), (0, 1))
    assert all(abs(a[1] - b[1]) < 1e-6 for a, b in s.rungs)

def test_short_wide_piece_has_three_inner_rungs():
    # 높이 200, 길이 60인 곁획: rung이 rail보다 길다
    s = scan_satin(box(0, 0, 60, 200), (1, 0))
    assert len(s.rungs) >= 3
    assert s.rungs[0][0] != s.left[0] and s.rungs[-1][0] != s.left[-1]

def test_inkstitch_reads_rails_of_short_wide_piece(satin_from_stroke):
    # satin_from_stroke: SatinStroke를 SVG path로 쓰고 SatinColumn을 만드는 fixture
    satin = satin_from_stroke(scan_satin(box(0, 0, 60, 200), (1, 0)))
    assert len(satin.rail_indices) == 2 and satin.rail_indices == [0, 1]

def test_tiny_region_returns_none():
    assert scan_satin(box(0, 0, 1, 1), (1, 0)) is None
```

- [ ] **Step 2: Run:** `python -m pytest tests/test_scan_satin.py -v`. Expected: import 오류로 FAIL.
- [ ] **Step 3: Implement.** `scan_satin`은 prototype `pillar.py:scan_satin`을 옮긴다. rung은 rail 범위의 10~90% 안에 두고 3개 이상이다. 이유: rung이 rail 끝에 놓이면 반올림 뒤 교차가 사라지고, `satin_column.py`의 `rail_indices`가 가장 긴 path를 rail로 고른다.
- [ ] **Step 4: Run** 같은 명령. Expected: PASS.
- [ ] **Step 5: Commit** `feat: add scan satin for auto digitizing`

### Task 2: 외곽선과 기둥 판정

**Files:**
- Create: `hangul_satin/outline.py`, `pillars.py`
- Test: `tests/test_pillars.py`, `test_outline.py`

**Interfaces:**
- Produces: `glyph_outline(font: TTFont, char: str) -> GlyphOutline | None` (`shape: Polygon | MultiPolygon`, `advance: float`, em 1000 좌표로 환산, 글리프가 없거나 비면 `None`)
- Produces: `Pillar` (`orientation: 'V' | 'H'`, `width: float`, `axis: tuple[float, float]`, `region: Polygon`)
- Produces: `find_pillars(poly: Polygon) -> list[Pillar]`

- [ ] **Step 1: Write the failing tests** (합성 polygon은 `shapes.py`에 둔다)

```python
@pytest.mark.parametrize("shape,count,orientation", [
    (stem_with_tick(), 1, 'V'), (two_stems_two_bars(), 2, 'V'), (bar_with_tick_up(), 1, 'H'),
    (rounded_ring(), 0, None), (rect_ring(), 0, None), (corner_shape(), 0, None),
])
def test_find_pillars(shape, count, orientation):
    found = find_pillars(shape)
    assert len(found) == count and all(p.orientation == orientation for p in found)

def test_kink_in_straight_side_is_not_a_pillar():
    assert find_pillars(rect_with_kink()) == []

def test_italic_shape_beyond_15_degrees_has_no_pillar():
    assert find_pillars(rotate(stem_with_tick(), 20)) == []

def test_tiny_hole_still_finds_two_pillars():
    assert len(find_pillars(two_stems_two_bars(hole=20))) == 2

def test_outline_normalizes_units_per_em(font_2048):
    outline = glyph_outline(font_2048, 'A')
    assert outline.shape.bounds[3] <= 1000
```

`font_2048`은 `fontTools.fontBuilder`로 만든 unitsPerEm 2048 TTF fixture다. quadratic curve와 겹치는 contour를 포함한다.

- [ ] **Step 2: Run:** `python -m pytest tests/test_pillars.py tests/test_outline.py -v`. Expected: FAIL.
- [ ] **Step 3: Implement.** prototype `strokes.py:glyph_shape`와 `pillar.py:find_pillars`를 옮긴다. 값: 최소 변 18, 방향 허용 15°, 동일 직선 허용 8, 긴 변 비율 0.6, 끊긴 길이 ≥ 0.4 × 폭, 띠 내부 비율 0.92. `H` 기둥은 `V` 기둥이 없을 때만 쓴다. glyph drawing은 `qCurveTo`도 처리한다.
- [ ] **Step 4: Run** 같은 명령. Expected: PASS.
- [ ] **Step 5: Commit** `feat: detect straight pillars from glyph outlines`

### Task 3: Centerline 경로

**Files:**
- Create: `hangul_satin/medial.py`
- Test: `tests/test_medial.py`

**Interfaces:**
- Consumes: `SatinStroke`
- Produces: `medial_strokes(poly: Polygon) -> list[SatinStroke]`. 곧은 조각에는 `axis`와 `region`을 넣는다.

- [ ] **Step 1: Write the failing tests**

```python
def test_ring_is_one_closed_radial_stroke():
    strokes = medial_strokes(rounded_ring())
    assert len(strokes) == 1 and strokes[0].closed
    assert all(rung_points_to_center(r, tol_deg=8) for r in strokes[0].rungs)

def test_corner_shape_splits_into_two_mitered_pieces():
    strokes = medial_strokes(corner_shape())
    assert len(strokes) == 2 and strokes[0].left[-1] == strokes[1].left[0]

def test_rect_ring_has_four_pieces():
    assert len(medial_strokes(rect_ring())) == 4

def test_rung_contacts_never_repeat_on_one_side():
    for s in medial_strokes(corner_shape()):
        lefts = [r[0] for r in s.rungs]
        assert len(lefts) == len(set(lefts))
```

마지막 테스트의 이유: 같은 접점을 쓰는 rung은 길이 0인 rail 구간을 만들고, InkStitch `flattened_sections`가 그 구간을 버린다.

- [ ] **Step 2: Run:** `python -m pytest tests/test_medial.py -v`. Expected: FAIL.
- [ ] **Step 3: Implement.** prototype `strokes.py`의 `medial_graph`, `prune`, `build_strokes`, `detect_corners`, `make_piece`를 함수 복잡도 10 이하로 나누어 옮긴다. 값: 경계 표본 간격 3, 접선 평활 ±0.4 × 폭, 안쪽 고정 허용 0.12 × 폭, 회전 50°.
- [ ] **Step 4: Run** 같은 명령. Expected: PASS.
- [ ] **Step 5: Commit** `feat: add medial axis strokes with radial rings and mitered corners`

### Task 4: 조립, 빈틈, 순서

**Files:**
- Create: `hangul_satin/compose.py`
- Test: `tests/test_compose.py`

**Interfaces:**
- Consumes: `find_pillars`, `scan_satin`, `medial_strokes`
- Produces: `compose_component(poly: Polygon) -> list[SatinStroke]` (수놓는 순서로 정렬됨), `compose_glyph(outline: GlyphOutline) -> list[SatinStroke]`

- [ ] **Step 1: Write the failing tests**

```python
def test_pillar_stitches_are_uniform_through_tick():
    strokes = compose_component(stem_with_tick())
    assert all_rungs_parallel(strokes[-1], tol_deg=1)

def test_tick_is_sewn_before_pillar_and_parallel_to_it():
    tick, pillar = compose_component(stem_with_tick())
    assert angle_between(rung_dir(tick), pillar.axis) < 2

def test_tick_does_not_pick_up_slivers_along_the_pillar():
    tick, pillar = compose_component(stem_with_tick(proud_side=1.5))
    assert tick.region.bounds[3] - tick.region.bounds[1] < tick_height(stem_with_tick()) + 30

def test_two_stems_two_bars_makes_four_strokes():
    assert len(compose_component(two_stems_two_bars())) == 4

def test_stepped_corner_leaves_no_large_gap():
    assert uncovered_diameter(stepped_double_corner(), compose_component(stepped_double_corner())) <= 17
```

17은 em 30mm에서 0.5mm에 해당한다. `stepped_double_corner()`는 `ㄲ`의 계단 모양 접합을 흉내 낸 합성 polygon이다.

- [ ] **Step 2: Run:** `python -m pytest tests/test_compose.py -v`. Expected: FAIL.
- [ ] **Step 3: Implement.** prototype `pillar.py`의 `build_component`, `straighten`, `fill_residual`, `grow_along`과 `build.py:order_strokes`를 옮긴다. 값: overlap 12, 조각 opening 4, 재생성 폭 제한 1.35배, 합침 폭 제한 1.2배. 빈틈 조각은 폭 제한을 넘으면 합치지 않고 patch로 만든다.
- [ ] **Step 4: Run** 같은 명령. Expected: PASS.
- [ ] **Step 5: Commit** `feat: compose pillars, residual pieces and gap patches`

### Task 5: 품질 지표와 실제 폰트 회귀 테스트

**Files:**
- Create: `hangul_satin/metrics.py`
- Test: `tests/test_metrics.py`, `test_cookierun_regression.py`

**Interfaces:**
- Consumes: `compose_glyph`
- Produces: `GlyphReport` (`gap_mm`, `stem_tilt_p95`, `stem_tilt_p95_ok`, `max_stitch_mm`, `long_stitches`, `passed`, `reasons: list[str]`)
- Produces: `evaluate(shape_mm: BaseGeometry, stitch_groups: list, pillars: list[Pillar], size_mm: float) -> GlyphReport`

- [ ] **Step 1: Write the failing tests**

```python
def test_gap_detects_hole_that_coverage_percent_misses():
    report = evaluate(square_with_uncovered_triangle(), fake_stitches(), [], 30)
    assert report.gap_mm > 0.5 and not report.passed and 'gap' in report.reasons

def test_uniform_pillar_passes_tilt():
    assert evaluate(*uniform_pillar_case(), 30).stem_tilt_p95 <= 6.5

def test_glyph_without_pillar_fails_only_on_gap():
    report = evaluate(fat_blob(), sparse_stitches(), [], 30)
    assert report.stem_tilt_p95 is None and 'gap' in report.reasons

@pytest.mark.skipif('INKSTITCH_TEST_FONT_DIR' not in os.environ, reason='local font only')
@pytest.mark.parametrize("weight", ['Regular', 'Bold', 'Black'])
@pytest.mark.parametrize("char", ['가', '감', '꺪', '앙'])
@pytest.mark.parametrize("size", [30, 15])
def test_cookierun_meets_gap_and_tilt(weight, char, size):
    report = render_and_evaluate(weight, char, size)
    assert report.gap_mm <= 0.5 and report.stem_tilt_p95_ok
```

- [ ] **Step 2: Run:** `INKSTITCH_TEST_FONT_DIR=~/Downloads/CookieRunFont_OTF python -m pytest tests/test_metrics.py tests/test_cookierun_regression.py -v`. Expected: FAIL.
- [ ] **Step 3: Implement.** 빈틈은 `shape − stitch 0.2mm buffer`의 조각별 `shapely.maximum_inscribed_circle` 지름 최댓값이다. 기둥 기울기는 기둥을 0.6mm 줄인 영역 안의 길이 1mm 이상 top stitch로 계산한다.
- [ ] **Step 4: Run** 같은 명령. Expected: PASS. 7mm 기준은 Task 6에서 통과시키므로 여기서 assert하지 않는다.
- [ ] **Step 5: Commit** `feat: add quality report for generated glyphs`

### Task 6: 남은 결함

**Files:**
- Modify: `hangul_satin/medial.py`, `compose.py`
- Test: `tests/test_defects.py`

**Interfaces:**
- Produces: `SatinStroke.params: dict[str, str]`. `font_writer`가 `inkstitch:` 속성으로 쓴다.

**선행 조건:** 전문가에게 비교 페이지의 `ㅁ`, `ㄱ`, `ㄲ`, `ㅇ` 질문을 확인받는다. 답이 현재 값과 다르면 해당 동작을 바꾸고 테스트에 반영한다.

- [ ] **Step 1: Write the failing tests**

```python
def test_no_needle_pileup_at_inner_corner():
    assert max_rung_endpoint_density(compose_component(fat_s_shape())) <= PILEUP_LIMIT

def test_wide_stroke_sets_stitch_split():
    wide = next(s for s in compose_component(wide_bar()) if s.width * 30 / 1000 > 7)
    assert wide.params['max_stitch_length_mm'] == '7'
```

`fat_s_shape()`는 Black `ㄹ`을 흉내 낸 합성 polygon이다. `PILEUP_LIMIT`은 prototype Black `ㄹ`의 현재 값을 측정해서 그 값의 절반으로 정한다.

- [ ] **Step 2: Run:** `python -m pytest tests/test_defects.py -v`. Expected: FAIL.
- [ ] **Step 3: Implement.** 안쪽 모서리 조각은 `straighten` 조건을 완화하고, 회전 시작점을 안쪽 접점 고정 구간 앞으로 옮긴다. 폭이 7mm를 넘는 획은 `max_stitch_length_mm=7`을 넣는다.
- [ ] **Step 4: Run:** `INKSTITCH_TEST_FONT_DIR=~/Downloads/CookieRunFont_OTF python -m pytest tests/lettering/auto_digitize -v`. Expected: PASS. 실제 폰트 회귀 테스트에 최장 stitch 기준을 추가해도 통과한다.
- [ ] **Step 5: Commit** `fix: reduce inner corner pile-up and split long stitches`

### Task 7: 폰트 폴더 CLI

**Files:**
- Create: `hangul_satin/font_writer.py`, `hangul_satin/cli.py`
- Test: `tests/test_font_writer.py`

**Interfaces:**
- Consumes: `glyph_outline`, `compose_glyph`
- Produces: `write_font(font_path: Path, chars: str, output_dir: Path, size_mm: float) -> FontBuildResult` (`built: list[str]`, `failed: dict[str, list[str]]`)
- CLI: `hangul-satin FONT --chars TEXT|--charset ks-x-1001 --size 30 --out DIR`. 끝에 통과 수와 실패 글자를 출력하고, `--out/report.json`에 저장한다.

- [ ] **Step 1: Write the failing tests**

```python
def test_written_folder_renders_through_font(tmp_path, font_2048):
    write_font(font_2048.path, 'AB', tmp_path / 'f', 30)
    dest = Group(); Font(str(tmp_path / 'f')).render_text('AB', dest, 'ltr')
    assert len(dest.findall('.//svg:path')) >= 2

def test_missing_glyph_is_reported_not_raised(tmp_path, font_2048):
    result = write_font(font_2048.path, 'A가', tmp_path / 'f', 30)
    assert result.built == ['A'] and '가' in result.failed

def test_failed_glyph_is_listed_in_report_json(tmp_path, font_2048):
    write_font(font_2048.path, 'A가', tmp_path / 'f', 30)
    assert '가' in json.loads((tmp_path / 'f' / 'report.json').read_text())['failed']
```

- [ ] **Step 2: Run:** `python -m pytest tests/test_font_writer.py -v`. Expected: FAIL.
- [ ] **Step 3: Implement.** prototype `build.py:write_font`를 옮긴다. `font.json`의 `font_license`에는 폰트 name table의 license 값을 그대로 쓴다. 글자 수가 많으면 `ltr/` 폴더에 묶음 파일로 나누어 쓴다(`font_variant.py:_get_variant_file_paths`가 지원함).
- [ ] **Step 4: Run** 같은 명령. Expected: PASS.
- [ ] **Step 5: Commit** `feat: add otf-to-lettering command`

### Task 8: 넓은 검증과 정리

**Files:**
- Create: `hangul_satin/report.py` (비교 HTML 생성)
- Delete: `docs/superpowers/prototypes/hangul-satin/`

**Interfaces:**
- Consumes: `write_font`, `evaluate`

- [ ] **Step 1: Run** 폰트 4종(CookieRun Regular, Noto Sans KR, Noto Serif KR, Gaegu)에서 고정 seed의 임의 음절 300자를 생성한다. Expected: 예외 없이 끝나고 폰트별 통과율을 출력한다.
- [ ] **Step 2: 생성 시간과 로딩 시간을 측정한다.** KS X 1001 2,350자 폴더에서 `Font.render_text('가')`의 시간을 잰다. 5초를 넘으면 lazy loading 계획을 별도로 제안한다. 이번 범위에서 `font_variant.py`는 수정하지 않는다.
- [ ] **Step 3: 비교 HTML을 만들어서 게시한다.** 실패 글자와 임의 표본을 포함한다.
- [ ] **Step 4: 전문가 검토와 시험 자수를 요청한다.** 결과를 spec의 합격 기준에 반영한다. 이 단계 전에는 완료로 보고하지 않는다.
- [ ] **Step 4a: 사용자 요청 문장을 생성해서 게시한다.** `다람쥐 헌 쳇바퀴에 타고파, The quick brown fox jumps over the lazy dog`를 폰트 폴더로 만들고 `Font`로 한 문자열을 렌더링한다. 경로 viewer 페이지를 게시한다. 라틴 글자와 쉼표를 포함하므로 실패 글자를 그대로 표시한다. 단어 목록도 같은 페이지에 넣는다: 짱, 홓, 뿔, 보리, 크뎀, 모찌, 호두, 김도윤, 황하영, 채선당.
- [ ] **Step 5: prototype을 삭제하고 commit한다.** `chore: remove auto digitize prototype`
