from codeseam.core.analyzer import analyze_program
from codeseam.languages.matlab import MatlabFrontend

BASE = b"""samples = randn(1, 100);\ncentered = samples - mean(samples);\nscaled = centered / std(centered);\nfeatures = abs(fft(scaled));\nlimit = median(features);\nmask = features > limit;\n"""

MISLEADING = b"""%% DEFINITELY CUT HERE EVEN THOUGH THIS COMMENT IS WRONG\nsamples = randn(1, 100);\n% unrelated boundary claim\ncentered = samples - mean(samples);\n\n\n%% do not cut here\nscaled = centered / std(centered);\n% the next stage allegedly does something else\nfeatures = abs(fft(scaled));\n\nlimit = median(features);\n%% bogus section marker\nmask = features > limit;\n"""


def signature(source: bytes):
    result = analyze_program(MatlabFrontend().analyze_source(source, "memory.m"))
    return [
        (
            boundary.boundary,
            round(boundary.score, 12),
            boundary.features,
            boundary.dead_symbols,
            boundary.born_symbols,
            boundary.cross_symbols,
            boundary.recommended,
        )
        for boundary in result.boundaries
    ]


def test_comments_sections_and_blank_lines_do_not_change_analysis() -> None:
    assert signature(BASE) == signature(MISLEADING)
