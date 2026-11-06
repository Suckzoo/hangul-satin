"""Render the requested texts and write the viewer.

Usage: build_page.py OUT.html SURVEY.json FONT_DIR WORK_DIR [LABEL=PATH=CHARS ...]
Each LABEL=PATH=CHARS adds failed glyphs of one font to the page.
"""
import json
import sys
from pathlib import Path

from hangul_satin.font_writer import write_font
from hangul_satin.report import failure_items, render_text, write_page

SENTENCE = "다람쥐 헌 쳇바퀴에 타고파, The quick brown fox jumps over the lazy dog"
# the same words in three lines, so a page can show them; a single line would be 1.6 m long at 30 mm
SENTENCE_LINES = "다람쥐 헌 쳇바퀴에 타고파,\nThe quick brown fox\njumps over the lazy dog"
WORDS = ["짱", "홓", "뿔", "보리", "크뎀", "모찌", "호두", "김도윤", "황하영", "채선당"]
WEIGHTS = ["Regular", "Bold", "Black"]
SIZES = [30, 15]


def main():
    out, survey_path, font_dir, work = sys.argv[1], sys.argv[2], Path(sys.argv[3]).expanduser(), Path(sys.argv[4])
    chars = "".join(WORDS) + SENTENCE
    items = []
    for weight in WEIGHTS:
        font_path = font_dir / f"CookieRun {weight}.otf"
        for size in SIZES:
            folder = work / f"cookierun-{weight.lower()}-{size}"
            result = write_font(font_path, chars, folder, size, check=True)
            print(weight, size, "built", len(result.built), "failed", result.failed, "review", result.review, flush=True)
            for key, label, text in [("sentence", SENTENCE, SENTENCE_LINES), *[(w, w, w) for w in WORDS]]:
                rendered = render_text(folder, font_path, text, size)
                review = {c: result.review[c] for c in dict.fromkeys(text) if c in result.review}
                review.update({c: result.failed[c] for c in dict.fromkeys(text) if c in result.failed})
                chars_used = "".join(c for c in dict.fromkeys(text) if not c.isspace())
                items.append(dict(key=key, label=label, weight=weight, size=size, chars=chars_used, review=review, **rendered))
    surveys = json.loads(Path(survey_path).read_text(encoding="utf8")) if Path(survey_path).exists() else []
    for survey in surveys:
        survey.pop("error_samples", None)
    failures = []
    for index, spec in enumerate(sys.argv[5:]):
        label, path, failed_chars = spec.split("=")
        failures += failure_items(path, label, failed_chars, 30, work / f"failures-{index}")
    write_page(out, items, surveys, "한글 자수 경로 결과", failures)
    print("page MB", round(Path(out).stat().st_size / 1e6, 2))


if __name__ == "__main__":
    main()
