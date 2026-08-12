from script_boundary.languages.matlab import MatlabFrontend
from script_boundary.languages.matlab.project import apply_project_context, scan_matlab_project


def test_project_scan_resolves_local_matlab_provider(tmp_path) -> None:
    (tmp_path / "main.m").write_text("x = helper(1);\ndisp(x);\n")
    (tmp_path / "helper.m").write_text("function y = helper(x)\ny = x + 1;\nend\n")
    index = scan_matlab_project(tmp_path)
    main = next(item for item in index.files if item.path == "main.m")
    assert "helper" in main.resolved_project_calls
    assert index.providers["helper"] == ["helper.m"]
    program = MatlabFrontend().analyze_source((tmp_path / "main.m").read_bytes(), str(tmp_path / "main.m"))
    apply_project_context(program, index)
    assert "helper" in program.regions[0].statements[0].resolved_calls
    assert program.regions[0].statements[0].call_resolution_available
    assert "ambiguous_call_or_index" not in {
        risk.value for risk in program.regions[0].statements[0].risks
    }
