from tests.docs.helpers import get_doc, get_section_bullets


def test_setup_workflow_doc_keeps_stable_prerequisite_contract() -> None:
    doc = get_doc("06")

    assert get_section_bullets(doc, "Implementation Acceptance Criteria") == [
        "downstream workflows can rely on stable seller and ICP records",
        "missing setup context is surfaced explicitly instead of inferred or fabricated",
        "seller and ICP writes are tenant-scoped and actor-scoped",
    ]


def test_account_search_doc_keeps_prerequisite_iteration_and_persistence_contract() -> None:
    doc = get_doc("07")

    assert get_section_bullets(doc, "Implementation Acceptance Criteria") == [
        "account search cannot run without seller and ICP context",
        "the iterative refinement loop is allowed by design",
        "accepted accounts become tenant-scoped canonical records",
        "downstream account research can start from persisted account ids",
    ]


def test_account_research_doc_keeps_snapshot_and_uncertainty_contract() -> None:
    doc = get_doc("08")

    assert get_section_bullets(doc, "Implementation Acceptance Criteria") == [
        "research output is seller-aware and ICP-aware",
        "deeper enrichment belongs to research, not search",
        "snapshots are append-only",
        "uncertainty notes are persisted when evidence is incomplete",
    ]


def test_contact_search_doc_keeps_normalization_and_missing_data_contract() -> None:
    doc = get_doc("09")

    assert get_section_bullets(doc, "Implementation Acceptance Criteria") == [
        "contact search stores normalized contacts rather than only transient ranked text",
        "missing-data flags are supported",
        "contact ranking remains tied to account and seller context",
    ]


def test_evidence_doc_keeps_traceability_and_approval_contract() -> None:
    doc = get_doc("10")

    assert get_section_bullets(doc, "Implementation Acceptance Criteria") == [
        "research outputs can be traced back to evidence",
        "approval decisions are durable and actor-attributed",
        "markdown is clearly treated as an artifact layer over canonical data",
    ]
