import re

from tests.docs.helpers import (
    CHILD_REQUIRED_SECTIONS,
    EXPECTED_DOC_IDS,
    extract_dependency_ids,
    get_doc,
    get_section_bullets,
    load_implementation_docs,
)


def test_implementation_docs_are_numbered_contiguously() -> None:
    docs = load_implementation_docs()

    assert [doc.doc_id for doc in docs] == EXPECTED_DOC_IDS


def test_root_doc_dependency_graph_lists_the_full_doc_order() -> None:
    root_doc = get_doc("00")
    listed_doc_ids = re.findall(r"^\d+\. \[(\d{2})-[^\]]+\.md\]", root_doc.text, re.MULTILINE)

    assert listed_doc_ids == EXPECTED_DOC_IDS


def test_child_docs_follow_the_shared_section_template() -> None:
    child_docs = [doc for doc in load_implementation_docs() if doc.doc_id != "00"]

    for doc in child_docs:
        headings = doc.level_two_headings
        positions = [headings.index(section) for section in CHILD_REQUIRED_SECTIONS]

        assert positions == sorted(positions), f"{doc.path.name} must keep shared sections in order"
        assert get_section_bullets(doc, "Implementation Acceptance Criteria")
        assert get_section_bullets(doc, "Deferred Items")


def test_child_doc_dependencies_only_point_to_existing_earlier_docs() -> None:
    child_docs = [doc for doc in load_implementation_docs() if doc.doc_id != "00"]

    for doc in child_docs:
        dependency_ids = extract_dependency_ids(doc)

        assert dependency_ids, f"{doc.path.name} must declare earlier dependencies"
        assert all(dep_id in EXPECTED_DOC_IDS for dep_id in dependency_ids)
        assert all(dep_id < doc.doc_id for dep_id in dependency_ids)
