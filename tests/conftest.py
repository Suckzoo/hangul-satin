import io
import os
import sys
from pathlib import Path

import pytest

EMPTY_SVG = (b'<svg xmlns="http://www.w3.org/2000/svg" xmlns:inkstitch="http://inkstitch.org/namespace" '
             b'width="400" height="400" viewBox="0 0 400 400"/>')
INKSTITCH = Path(os.environ.get("INKSTITCH_PATH", "~/tmp/InkStitch")).expanduser()


@pytest.fixture
def inkstitch():
    if not (INKSTITCH / "lib" / "elements").is_dir():
        pytest.skip("InkStitch checkout not found; set INKSTITCH_PATH")
    if str(INKSTITCH) not in sys.path:
        sys.path.insert(0, str(INKSTITCH))
    sys.dont_write_bytecode = True
    return INKSTITCH


@pytest.fixture
def satin_from_stroke(inkstitch):
    """Build a real InkStitch SatinColumn from a SatinStroke."""
    import inkex
    from lib.elements import SatinColumn

    def build(stroke, scale=0.1134):
        root = inkex.load_svg(io.BytesIO(EMPTY_SVG)).getroot()
        node = inkex.PathElement()
        node.set("d", stroke.path_data(scale))
        node.set("style", "fill:none;stroke:#000;stroke-width:1")
        node.set("inkstitch:satin_column", "True")
        root.append(node)
        return SatinColumn(node)
    return build
