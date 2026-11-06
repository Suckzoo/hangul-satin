"""Build a KS X 1001 font and time one render. Usage: load_time.py FONT OUT_DIR"""
import sys
import time

from hangul_satin.cli import ks_x_1001_syllables
from hangul_satin.font_writer import write_font
from hangul_satin.inkstitch_bridge import use_inkstitch


def main():
    font, out = sys.argv[1], sys.argv[2]
    started = time.time()
    result = write_font(font, ks_x_1001_syllables(), out, 30)
    print("build seconds", round(time.time() - started, 1), "built", len(result.built), "failed", len(result.failed), flush=True)
    use_inkstitch()
    import inkex
    from lib.lettering import Font
    started = time.time()
    Font(out, show_font_path_warning=False).render_text("가", inkex.Group(), "ltr")
    print("render seconds", round(time.time() - started, 1), flush=True)


if __name__ == "__main__":
    main()
