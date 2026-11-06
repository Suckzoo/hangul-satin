# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

Environment setup is in `README.md`. `inkex` must be installed with `--no-deps`: its `pygobject` dependency does not build on macOS.

```bash
source .venv/bin/activate
python -m pytest                                  # font tests skip
python -m pytest tests/test_pillars.py -k kink    # one test
INKSTITCH_TEST_FONT_DIR=~/Downloads/CookieRunFont_OTF python -m pytest   # adds real-font regression tests
flake8 --max-complexity=10 --max-line-length=150 hangul_satin tests scripts   # must pass before a commit

hangul-satin FONT.otf --chars "가나다" --size 30 --out out/f --check
python scripts/survey.py out/s.json 300 30 FONT...             # pass rate of random syllables
python scripts/build_page.py out/page.html SURVEY.json FONT_DIR out/fonts [LABEL=PATH=CHARS ...]   # viewer page
```

`INKSTITCH_PATH` points to an InkStitch checkout (default `~/tmp/InkStitch`). Tests, `--check` and the viewer page need it. Tests that need it skip when it is missing. Never edit InkStitch from this repository.

## Architecture

`compose.compose_glyph(GlyphOutline)` is the core. It runs once per connected part of a glyph:

1. `pillars.find_pillars` looks for straight strokes with a branch. It uses straight outline edges, not the medial axis. A pillar has one side cut by a real branch that continues on the same line, so `ㅏ` and `ㅒ` have pillars and `ㅇ`, `ㅁ`, `ㄱ` do not.
2. `scan_satin.scan_satin` slices a region across an axis, so all stitches run parallel. Pillars and bar-shaped remainders use it. A remainder tucks under its pillar by `OVERLAP`.
3. `medial.medial_strokes` handles parts with no pillar and curved remainders. Voronoi ridges give chords that become rungs. Rings stay radial. Sharp inner corners become miters. `compose._straighten` then rescans straight pieces with `scan_satin`.
4. `compose._fill_gaps` merges an uncovered area into a neighbor, or makes a patch. `compose._order` sews strokes that end at a junction before the stroke that crosses there, using `SatinStroke.under` and `over`.

The output is `SatinStroke` (`types.py`), which writes SVG path data. The stitch engine is InkStitch's `SatinColumn`; this project only feeds it rails and rungs.

- `inkstitch_bridge.py` is the only way to reach InkStitch at quality-check time. It stitches strokes and sets per-stroke parameters such as underlay and stitch split.
- `metrics.evaluate` gives the pass or fail numbers: largest gap, pillar tilt, long stitches.
- `font_writer.py` writes the font folder. `report.py` and `viewer.html` render real text through InkStitch's `Font` and build the review page.

Design and rationale: `docs/superpowers/specs/2026-11-06-hangul-auto-satin-design.md`.

## Units

Geometry is in em-1000 units with y up, after `outline.glyph_outline` normalizes `unitsPerEm`. All length constants assume this. `metrics` works in mm with y down; `inkstitch_bridge.to_mm` converts.

## InkStitch behaviors that shape this code

- `SatinColumn.rail_indices` finds rails by counting crossings. With fewer than three rungs it falls back to the longest paths, and in a short wide piece those are rungs. Every stroke therefore has at least three rungs, placed inside the rail span.
- `SatinColumn.flattened_sections` drops a section when a rail section has zero length. Two rungs must not share a contact point.
- Rail points pair by proportion between rungs. A stretch with changing width and no rung slants its stitches, so `scan_satin` adds rungs where the width changes.
- `max_stitch_length_mm` lets a stitch reach the set length, and it does not split underlay. Hence the 6.5 mm split, and the 7.2 mm limit that `metrics` applies to top stitches only.
- `Glyph` moves each glyph to x = 0 before layout. `report._placed_outlines` must undo this to place outlines.

## Constraints

- Do not commit font files or data derived from them. This repository is public. `out/` and font extensions are ignored; committed tests use the synthetic shapes in `tests/shapes.py`. The only exception is a README image of stitched text, with the source credit its font license asks for. The README image uses CookieRun; its license forbids redistributing a modified font, so converted font folders stay out of this repository.
- Numeric pass does not mean a good path. An embroidery expert judges results from before/after pages, so show visual comparisons for path changes.
- Regular and thin weights come first. Black is too thick for most embroidery, so defer Black-only fixes.
