from __future__ import annotations

from script_boundary.core.ir import AnalysisResult, BoundaryAnalysis


def render_analysis(result: AnalysisResult) -> str:
    lines = [
        f"File: {result.program.path}",
        f"Language: {result.program.language}",
        f"Regions: {len(result.program.regions)}",
    ]
    if result.program.diagnostics:
        lines.append("Diagnostics: " + "; ".join(result.program.diagnostics))
    for region in result.program.regions:
        boundaries = [item for item in result.boundaries if item.region_id == region.id]
        lines.extend(["", f"Region {region.id} ({len(region.statements)} statements)"])
        if not boundaries:
            lines.append("  No legal boundaries")
            continue
        lines.append("  #     Lines  Score   Prom Peak Rec")
        for item in boundaries:
            lines.append(
                f"  {item.boundary:<3} {item.after_line:>4}|{item.before_line:<4} "
                f"{item.score:>6.3f} {item.prominence:>6.3f} "
                f"{'YES' if item.local_peak_candidate else '':>4} "
                f"{'YES' if item.recommended else ''}"
            )
    recommended = [item for item in result.boundaries if item.recommended]
    lines.extend(["", "Recommended boundaries:"])
    if not recommended:
        lines.append("  none")
    else:
        for item in recommended:
            lines.extend(_explanation_lines(item, indent="  "))
    return "\n".join(lines)


def render_explanation(item: BoundaryAnalysis) -> str:
    return "\n".join(_explanation_lines(item, indent=""))


def _explanation_lines(item: BoundaryAnalysis, indent: str) -> list[str]:
    features = ", ".join(f"{name}={value:.3f}" for name, value in item.features.items())
    raw = ", ".join(f"{name}={value:g}" for name, value in item.raw_features.items())
    edges = ", ".join(
        f"{edge.source_statement + 1}->{edge.target_statement + 1}:{edge.symbol}"
        for edge in item.cross_edges
    )
    return [
        f"{indent}{item.region_id} after line {item.after_line}, score={item.score:.3f}",
        f"{indent}  local peak: {item.local_peak_candidate}, prominence={item.prominence:.3f}",
        f"{indent}  rejected by: {', '.join(item.rejection_reasons) or '-'}",
        f"{indent}  features: {features}",
        f"{indent}  raw ({item.normalization_version}): {raw}",
        f"{indent}  dead: {', '.join(item.dead_symbols) or '-'}",
        f"{indent}  born: {', '.join(item.born_symbols) or '-'}",
        f"{indent}  cross: {', '.join(item.cross_symbols) or '-'}",
        f"{indent}  cross edges: {edges or '-'}",
        f"{indent}  constraints: {', '.join(item.constraints) or '-'}",
        f"{indent}  risks: {', '.join(item.risks) or '-'}",
        f"{indent}  completion roles: {', '.join(item.completion_roles) or '-'}",
        f"{indent}  completion symbols: {', '.join(item.completion_symbols) or '-'}",
        f"{indent}  left module quality: {_quality(item.left_module_quality)}",
        f"{indent}  right module quality: {_quality(item.right_module_quality)}",
    ]


def _quality(quality) -> str:
    if quality is None:
        return "-"
    return (
        f"{quality.score:.3f} lines {quality.start_line}-{quality.end_line} "
        f"inputs={len(quality.inputs)} outputs={len(quality.outputs)}"
    )
