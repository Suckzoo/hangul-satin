"""Command line: hangul-satin FONT --chars TEXT --size 30 --out DIR"""
import argparse
import sys
from pathlib import Path

from .font_writer import write_font


def ks_x_1001_syllables() -> str:
    """The 2,350 common Hangul syllables of KS X 1001, rows 0xB0 to 0xC8 of EUC-KR."""
    return "".join(bytes([lead, trail]).decode("euc_kr") for lead in range(0xB0, 0xC9) for trail in range(0xA1, 0xFF))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="hangul-satin", description="Convert a TTF/OTF font to an InkStitch lettering font folder.")
    parser.add_argument("font", type=Path)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--chars", help="characters to build")
    source.add_argument("--charset", choices=["ks-x-1001"], help="a named character set")
    parser.add_argument("--size", type=float, default=30.0, help="em size in mm")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--check", action="store_true", help="stitch each glyph with InkStitch and list the ones that miss the quality limits")
    args = parser.parse_args(argv)

    chars = args.chars if args.chars else ks_x_1001_syllables()
    try:
        result = write_font(args.font, chars, args.out, args.size, check=args.check)
    except RuntimeError as error:
        print(error, file=sys.stderr)
        return 2
    print(f"built {len(result.built)}, failed {len(result.failed)}, need review {len(result.review)}")
    for char, reasons in {**result.failed, **result.review}.items():
        print(f"  {char}: {', '.join(reasons)}")
    print(f"report: {args.out / 'report.json'}")
    return 0
