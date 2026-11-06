"""Draw the README example. Usage: readme_image.py FONT OUT.png WORK_DIR  (needs matplotlib)"""
import sys

import matplotlib
import matplotlib.pyplot as plt

from hangul_satin.font_writer import write_font
from hangul_satin.report import render_text

matplotlib.use("Agg")
TEXT = "다람쥐 헌 쳇바퀴에 타고파,\nThe quick brown fox"
CLOSE_UP = "앙꺪"
COLORS = ["#0b7285", "#c2410c", "#5c7f1a", "#7c3aed", "#b5179e", "#a67c00", "#1d4ed8", "#d9480f", "#2b8a3e", "#9c3b5a"]
FABRIC = "#eef1f1"


def draw(ax, rendered, line_width):
    for polygon in rendered["outlines"]:
        for ring in polygon:
            xs, ys = zip(*ring)
            ax.plot(xs, ys, color="#8b9a9e", lw=0.4)
    for group in rendered["groups"]:
        if not group["underlay"] and len(group["pts"]) > 1:
            xs, ys = zip(*group["pts"])
            ax.plot(xs, ys, color=COLORS[group["el"] % len(COLORS)], lw=line_width)
    ax.set_aspect("equal")
    ax.invert_yaxis()
    ax.axis("off")


def main():
    font, out, work = sys.argv[1], sys.argv[2], sys.argv[3]
    write_font(font, TEXT + CLOSE_UP, work, 30)
    fig = plt.figure(figsize=(11, 7.4), facecolor=FABRIC)
    grid = fig.add_gridspec(2, 1, height_ratios=[1.0, 1.15], hspace=0.02, left=0.01, right=0.99, top=0.99, bottom=0.01)
    draw(fig.add_subplot(grid[0]), render_text(work, font, TEXT, 30), 0.45)
    draw(fig.add_subplot(grid[1]), render_text(work, font, CLOSE_UP, 30), 0.7)
    fig.savefig(out, dpi=150, facecolor=FABRIC)


if __name__ == "__main__":
    main()
