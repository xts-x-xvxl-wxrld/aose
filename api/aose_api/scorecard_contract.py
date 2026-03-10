from __future__ import annotations

from typing import Any

ALLOWED_EVIDENCE_CATEGORIES = frozenset(
    {"firmographic", "persona_fit", "trigger", "technographic"}
)


def normalize_and_validate_reasons(
    reasons: object,
    *,
    existing_evidence_ids: set[str] | None = None,
) -> list[dict[str, Any]]:
    """
    Validate the canonical scorecard reason shape and apply lossless normalization.

    Allowed normalization is intentionally narrow:
    - trim code/text strings
    - dedupe + sort evidence_ids
    """
    if not isinstance(reasons, list):
        raise ValueError("reasons must be a list")

    normalized: list[dict[str, Any]] = []
    for i, reason in enumerate(reasons):
        if not isinstance(reason, dict):
            raise ValueError(f"reason[{i}] must be an object")

        code = reason.get("code")
        text = reason.get("text")
        evidence_ids = reason.get("evidence_ids")

        if not isinstance(code, str) or not code.strip():
            raise ValueError(f"reason[{i}] missing non-empty code")
        if not isinstance(text, str) or not text.strip():
            raise ValueError(f"reason[{i}] missing non-empty text")
        if not isinstance(evidence_ids, list) or len(evidence_ids) == 0:
            raise ValueError(f"reason[{i}] must include non-empty evidence_ids")

        normalized_ids: list[str] = []
        seen_ids: set[str] = set()
        for eid in evidence_ids:
            if not isinstance(eid, str) or not eid.strip():
                raise ValueError(f"reason[{i}] has invalid evidence_id")
            clean_eid = eid.strip()
            if clean_eid in seen_ids:
                continue
            if (
                existing_evidence_ids is not None
                and clean_eid not in existing_evidence_ids
            ):
                raise ValueError(
                    f"reason[{i}] references unknown evidence_id {clean_eid!r}"
                )
            seen_ids.add(clean_eid)
            normalized_ids.append(clean_eid)

        normalized.append(
            {
                "code": code.strip(),
                "text": text.strip(),
                "evidence_ids": sorted(normalized_ids),
            }
        )

    return normalized
