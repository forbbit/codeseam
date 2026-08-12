from codeseam.corpus.structure import structure_fingerprint
from codeseam.languages.matlab import MatlabFrontend


def test_structure_fingerprint_ignores_identifier_names_and_literals() -> None:
    frontend = MatlabFrontend()
    left = frontend.analyze_source(b"x = rand(1, 10);\ny = mean(x);\n", "left.m")
    right = frontend.analyze_source(b"samples = rand(1, 20);\nresult = mean(samples);\n", "right.m")
    assert structure_fingerprint(left) == structure_fingerprint(right)
