"""Pass rate of random syllables per font. Usage: survey.py OUT.json COUNT SIZE_MM FONT..."""
import json
import sys

from hangul_satin.report import random_syllables, survey_font


def main():
    out, count, size, fonts = sys.argv[1], int(sys.argv[2]), float(sys.argv[3]), sys.argv[4:]
    chars = random_syllables(count, seed=20261106)
    surveys = []
    for path in fonts:
        survey = survey_font(path, chars, size)
        surveys.append(survey)
        print(survey["font"], survey["passed"], "/", survey["total"], "errors", survey["errors"], "secs", survey["seconds"], flush=True)
        with open(out, "w", encoding="utf8") as fh:
            json.dump(surveys, fh, ensure_ascii=False)


if __name__ == "__main__":
    main()
