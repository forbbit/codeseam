from __future__ import annotations

import pytest

from codeseam.training.data_policy import require_trainable_record


def test_training_data_policy_accepts_high_confidence_expert_gold() -> None:
    pending = {
        "provenance": {
            "source_kind": "curated_real_gold",
            "annotation_status": "pending_user_review",
            "source_sha256": "abc",
            "revision": "def",
        }
    }
    with pytest.raises(ValueError, match="final review"):
        require_trainable_record(pending)

    pending["provenance"]["annotation_status"] = "expert_accepted"
    pending["provenance"]["annotation_confidence"] = "high"
    require_trainable_record(pending)


def test_training_data_policy_rejects_uncertain_expert_gold() -> None:
    record = {
        "provenance": {
            "source_kind": "curated_real_gold",
            "annotation_status": "expert_accepted",
            "annotation_confidence": "medium",
            "source_sha256": "abc",
            "revision": "def",
        }
    }
    with pytest.raises(ValueError, match="not high confidence"):
        require_trainable_record(record)


def test_training_data_policy_requires_real_gold_provenance() -> None:
    with pytest.raises(ValueError, match="immutable provenance"):
        require_trainable_record({
            "provenance": {
                "source_kind": "curated_real_gold",
                "annotation_status": "user_adjudicated",
            }
        })
