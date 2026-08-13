from __future__ import annotations

import hashlib
import json
import math
import statistics
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from enum import StrEnum

from codeseam.core.ir import Effect, OperationRole, Risk
from codeseam.core.raw_facts import BoundaryRawFacts


class FingerprintKind(StrEnum):
    COUNT = "count"
    CONTINUOUS = "continuous"
    PROBABILITY = "probability"
    BINARY = "binary"
    CATEGORICAL = "categorical"
    HISTOGRAM = "histogram"
    SET_STATS = "set_stats"


@dataclass(frozen=True, slots=True)
class FingerprintFieldSpec:
    name: str
    family: str
    kind: FingerprintKind
    source: str
    transform: str = "identity"
    categories: tuple[str, ...] = ()
    weight: float = 1.0


@dataclass(frozen=True, slots=True)
class FingerprintSchema:
    version: str
    fields: tuple[FingerprintFieldSpec, ...]
    metric_version: str = "mixed-distance-v1"
    fitted_stats: tuple[tuple[str, float, float, bool], ...] = ()
    clip: float = 8.0
    fit_split: str = "train"

    @property
    def schema_id(self) -> str:
        payload = json.dumps(asdict(self), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(payload.encode()).hexdigest()


@dataclass(frozen=True, slots=True)
class NormalizedFingerprint:
    schema_version: str
    schema_id: str
    names: tuple[str, ...]
    values: tuple[float, ...]
    observed_mask: tuple[bool, ...]
    blocks: tuple[tuple[str, int, int, str, float], ...]
    exact_id: str
    raw_observation_id: str


@dataclass(frozen=True, slots=True)
class DistanceResult:
    distance: float
    block_distances: tuple[tuple[str, float], ...]
    missingness_distance: float


def _default_fields() -> tuple[FingerprintFieldSpec, ...]:
    count = FingerprintKind.COUNT
    scalar = [
        ("dead_count", "symbol", count, "dead_symbol_count"),
        ("born_count", "symbol", count, "born_symbol_count"),
        ("cross_count", "symbol", count, "cross_symbol_count"),
        ("left_symbols", "symbol", count, "left_symbol_count"),
        ("right_symbols", "symbol", count, "right_symbol_count"),
        ("input_interface", "interface", count, "input_interface_count"),
        ("output_interface", "interface", count, "output_interface_count"),
        ("cross_dependencies", "dependency", count, "cross_dependency_count"),
        ("local_cross_dependencies", "dependency", count, "local_cross_dependency_count"),
        ("nearby_dependencies", "dependency", count, "nearby_dependency_count"),
        ("left_internal_edges", "dependency", count, "left_internal_data_edge_count"),
        ("right_internal_edges", "dependency", count, "right_internal_data_edge_count"),
        ("dependency_span_mean", "dependency", FingerprintKind.CONTINUOUS, "dependency_span_mean"),
        ("dependency_span_max", "dependency", count, "dependency_span_max"),
        ("dependency_targets", "dependency", count, "dependency_target_count"),
        ("dependency_mass", "dependency", count, "dependency_reuse_mass"),
        ("left_calls", "call", count, "left_call_count"),
        ("right_calls", "call", count, "right_call_count"),
        ("call_intersection", "call", count, "call_intersection"),
        ("call_union", "call", count, "call_union"),
        ("call_jaccard", "call", FingerprintKind.PROBABILITY, "call_jaccard"),
        ("control_followup", "control", count, "control_followup_edge_count"),
        ("unfinished_mass", "completion", FingerprintKind.CONTINUOUS, "unfinished_work_mass"),
        ("completion_length", "completion", count, "completion_chain_length"),
        ("left_module_size", "module_size", count, "left_context_size"),
        ("right_module_size", "module_size", count, "right_context_size"),
    ]
    fields = [
        FingerprintFieldSpec(name, family, kind, source, "log1p" if kind is count else "identity")
        for name, family, kind, source in scalar
    ]
    for name in ("parse", "call_resolution", "dependency", "role", "effect"):
        fields.append(
            FingerprintFieldSpec(
                f"reliability.{name}",
                "reliability",
                FingerprintKind.PROBABILITY,
                f"reliability.{name}",
            )
        )
    fields.extend(
        (
            FingerprintFieldSpec(
                "compound_end", "control", FingerprintKind.BINARY, "compound_ends_here"
            ),
            FingerprintFieldSpec(
                "dynamic_workspace",
                "risk",
                FingerprintKind.BINARY,
                "reliability.dynamic_workspace_risk",
            ),
            FingerprintFieldSpec(
                "alias_uncertainty", "risk", FingerprintKind.BINARY, "reliability.alias_uncertainty"
            ),
            FingerprintFieldSpec(
                "roles.left",
                "role",
                FingerprintKind.HISTOGRAM,
                "left_role_histogram",
                categories=tuple(item.value for item in OperationRole),
            ),
            FingerprintFieldSpec(
                "roles.right",
                "role",
                FingerprintKind.HISTOGRAM,
                "right_role_histogram",
                categories=tuple(item.value for item in OperationRole),
            ),
            FingerprintFieldSpec(
                "effects.left",
                "effect",
                FingerprintKind.HISTOGRAM,
                "left_effect_histogram",
                categories=tuple(item.value for item in Effect),
            ),
            FingerprintFieldSpec(
                "effects.right",
                "effect",
                FingerprintKind.HISTOGRAM,
                "right_effect_histogram",
                categories=tuple(item.value for item in Effect),
            ),
            FingerprintFieldSpec(
                "risks",
                "risk",
                FingerprintKind.CATEGORICAL,
                "risks",
                categories=tuple(item.value for item in Risk) + ("OTHER", "UNKNOWN"),
            ),
            FingerprintFieldSpec(
                "constraints",
                "constraint",
                FingerprintKind.CATEGORICAL,
                "constraints",
                categories=("compound_continuation", "adjacent_parse_error", "OTHER", "UNKNOWN"),
            ),
        )
    )
    return tuple(fields)


def raw_fingerprint(facts: BoundaryRawFacts) -> dict[str, object]:
    """Identifier- and source-position-independent typed observation."""
    result: dict[str, object] = {}
    for spec in _default_fields():
        result[spec.name] = _source_value(facts, spec.source)
    return result


def fingerprint_id(facts: BoundaryRawFacts) -> str:
    payload = json.dumps(raw_fingerprint(facts), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode()).hexdigest()


def numeric_fingerprint(facts: BoundaryRawFacts) -> tuple[float, ...]:
    """Legacy vector retained for API compatibility; new audits use normalize_fingerprint."""
    r = facts.reliability
    return tuple(
        float(value)
        for value in (
            facts.dead_symbol_count,
            facts.born_symbol_count,
            facts.cross_symbol_count,
            facts.input_interface_count,
            facts.output_interface_count,
            facts.cross_dependency_count,
            facts.dependency_span_mean,
            facts.dependency_span_max,
            facts.dependency_reuse_mass,
            facts.unfinished_work_mass,
            facts.completion_chain_length,
            facts.left_context_size,
            facts.right_context_size,
            r.parse,
            r.call_resolution,
            r.dependency,
            r.role,
            r.dynamic_workspace_risk,
            r.alias_uncertainty,
        )
    )


def fit_fingerprint_schema(
    train_facts_only: Iterable[BoundaryRawFacts], *, split: str = "train"
) -> FingerprintSchema:
    if split != "train":
        raise ValueError("fingerprint normalization may only be fitted on train")
    facts = list(train_facts_only)
    if not facts:
        raise ValueError("cannot fit fingerprint schema on an empty training set")
    fields = _default_fields()
    stats = []
    for spec in fields:
        if spec.kind not in {FingerprintKind.COUNT, FingerprintKind.CONTINUOUS}:
            continue
        values = [float(_source_value(item, spec.source)) for item in facts]
        if spec.transform == "log1p":
            values = [math.log1p(max(0.0, value)) for value in values]
        median = statistics.median(values)
        ordered = sorted(values)
        q1 = _quantile(ordered, 0.25)
        q3 = _quantile(ordered, 0.75)
        iqr = q3 - q1
        stats.append((spec.name, median, iqr, iqr == 0.0))
    return FingerprintSchema("typed-fingerprint-v2", fields, fitted_stats=tuple(stats))


def normalize_fingerprint(
    facts: BoundaryRawFacts, schema: FingerprintSchema
) -> NormalizedFingerprint:
    stats = {name: (median, iqr, constant) for name, median, iqr, constant in schema.fitted_stats}
    names: list[str] = []
    values: list[float] = []
    mask: list[bool] = []
    blocks: list[tuple[str, int, int, str, float]] = []
    raw = raw_fingerprint(facts)
    for spec in schema.fields:
        start = len(values)
        observation = raw.get(spec.name)
        observed = observation is not None
        if spec.kind in {FingerprintKind.COUNT, FingerprintKind.CONTINUOUS}:
            value = float(observation) if observed else 0.0
            if spec.transform == "log1p":
                value = math.log1p(max(0.0, value))
            median, iqr, constant = stats[spec.name]
            value = (
                0.0
                if constant
                else max(-schema.clip, min(schema.clip, (value - median) / iqr)) / schema.clip
            )
            names.append(spec.name)
            values.append(value)
            mask.append(observed)
        elif spec.kind in {FingerprintKind.PROBABILITY, FingerprintKind.BINARY}:
            names.append(spec.name)
            values.append(float(observation) if observed else 0.0)
            mask.append(observed)
        elif spec.kind is FingerprintKind.HISTOGRAM:
            histogram = dict(observation or ())
            total = sum(max(0.0, float(value)) for value in histogram.values())
            for category in spec.categories:
                names.append(f"{spec.name}.{category}")
                values.append(
                    max(0.0, float(histogram.get(category, 0.0))) / total if total else 0.0
                )
                mask.append(observed)
            names.append(f"{spec.name}.__empty__")
            values.append(float(total == 0))
            mask.append(observed)
        else:
            selected = set(observation or ())
            known = set(spec.categories) - {"OTHER", "UNKNOWN"}
            if not observed:
                selected = {"UNKNOWN"}
            elif any(item not in known for item in selected):
                selected.add("OTHER")
            for category in spec.categories:
                names.append(f"{spec.name}.{category}")
                values.append(float(category in selected))
                mask.append(observed or category == "UNKNOWN")
        blocks.append((spec.family, start, len(values), spec.kind.value, spec.weight))
    canonical = {
        "schema_id": schema.schema_id,
        "names": names,
        "values": [round(item, 12) for item in values],
        "observed_mask": mask,
    }
    exact_id = hashlib.sha256(
        json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    raw_id = hashlib.sha256(
        json.dumps(raw, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return NormalizedFingerprint(
        schema.version,
        schema.schema_id,
        tuple(names),
        tuple(values),
        tuple(mask),
        tuple(blocks),
        exact_id,
        raw_id,
    )


def mixed_distance(left: NormalizedFingerprint, right: NormalizedFingerprint) -> DistanceResult:
    if left.schema_id != right.schema_id or left.names != right.names:
        raise ValueError("fingerprint schema mismatch")
    weighted = 0.0
    weights = 0.0
    details = []
    for family, start, end, kind, weight in left.blocks:
        both = [
            index
            for index in range(start, end)
            if left.observed_mask[index] and right.observed_mask[index]
        ]
        if not both:
            continue
        if kind == FingerprintKind.HISTOGRAM.value:
            distance = math.sqrt(
                sum(
                    (math.sqrt(max(0.0, left.values[i])) - math.sqrt(max(0.0, right.values[i])))
                    ** 2
                    for i in both
                )
            ) / math.sqrt(2.0)
        elif kind in {FingerprintKind.BINARY.value, FingerprintKind.CATEGORICAL.value}:
            distance = sum(left.values[i] != right.values[i] for i in both) / len(both)
        else:
            distance = sum(abs(left.values[i] - right.values[i]) for i in both) / len(both)
        distance = max(0.0, min(1.0, distance))
        details.append((family, distance))
        weighted += weight * distance
        weights += weight
    missing = sum(
        a != b for a, b in zip(left.observed_mask, right.observed_mask, strict=True)
    ) / max(1, len(left.observed_mask))
    return DistanceResult(weighted / weights if weights else 0.0, tuple(details), missing)


def _source_value(facts: BoundaryRawFacts, source: str):
    if source == "call_intersection":
        return len(set(facts.left_calls) & set(facts.right_calls))
    if source == "call_union":
        return len(set(facts.left_calls) | set(facts.right_calls))
    if source == "call_jaccard":
        union = set(facts.left_calls) | set(facts.right_calls)
        return len(set(facts.left_calls) & set(facts.right_calls)) / len(union) if union else 1.0
    value: object = facts
    for part in source.split("."):
        value = getattr(value, part)
    return value


def _quantile(ordered: list[float], fraction: float) -> float:
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * fraction
    lower = math.floor(position)
    upper = math.ceil(position)
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)
