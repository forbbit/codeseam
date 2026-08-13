from __future__ import annotations

from collections.abc import Mapping

TRAINABLE_SOURCE_KINDS = frozenset({"curated_real_gold"})
FORBIDDEN_SOURCE_KINDS = frozenset(
    {"real_project", "github_real", "external_unlabeled", "detection_only"}
)


def require_trainable_record(record: Mapping[str, object]) -> None:
    """Reject real/untrusted source records before source parsing or feature extraction."""

    provenance = record.get("provenance")
    details = provenance if isinstance(provenance, Mapping) else {}
    source_kind = details.get("source_kind")
    if source_kind is None:
        raise ValueError("training record has no trusted source_kind provenance")
    if source_kind in FORBIDDEN_SOURCE_KINDS:
        raise ValueError(f"source_kind {source_kind!r} is forbidden for training")
    if source_kind == "curated_real_gold":
        if details.get("annotation_status") not in {"expert_accepted", "user_adjudicated"}:
            raise ValueError("curated real source has not passed final review")
        if details.get("annotation_status") == "expert_accepted" and details.get(
            "annotation_confidence"
        ) != "high":
            raise ValueError("expert-accepted real source is not high confidence")
        if not details.get("source_sha256") or not details.get("revision"):
            raise ValueError("curated real source lacks immutable provenance")
    if source_kind not in TRAINABLE_SOURCE_KINDS:
        raise ValueError(f"source_kind {source_kind!r} is not approved for training")
