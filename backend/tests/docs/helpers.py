from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re


REPO_ROOT = Path(__file__).resolve().parents[2]
IMPLEMENTATION_DOCS_DIR = REPO_ROOT / "docs" / "implementation"
EXPECTED_DOC_IDS = [f"{index:02d}" for index in range(12)]
CHILD_REQUIRED_SECTIONS = [
    "Purpose And Scope",
    "Dependencies On Earlier Docs",
    "Decision Summary",
    "Canonical Models / Types / Interfaces Introduced Or Consumed",
    "Data Flow / State Transitions",
    "Failure Modes And Edge-Case Rules",
    "Validation, Ownership, And Permission Rules",
    "Persistence Impact",
    "API / Events / Artifact Impact",
    "Implementation Acceptance Criteria",
    "Verification",
    "Deferred Items",
]


@dataclass(frozen=True)
class ImplementationDoc:
    doc_id: str
    path: Path
    text: str

    @property
    def level_two_headings(self) -> list[str]:
        return [
            match.group("heading").strip()
            for match in re.finditer(r"^## (?P<heading>.+)$", self.text, re.MULTILINE)
        ]


def load_implementation_docs() -> list[ImplementationDoc]:
    docs: list[ImplementationDoc] = []

    for path in sorted(IMPLEMENTATION_DOCS_DIR.glob("*.md")):
        match = re.match(r"(?P<doc_id>\d{2})-", path.name)
        assert match, f"Implementation doc filename must start with a numeric id: {path.name}"
        docs.append(ImplementationDoc(doc_id=match.group("doc_id"), path=path, text=path.read_text()))

    return docs


def get_doc(doc_id: str) -> ImplementationDoc:
    for doc in load_implementation_docs():
        if doc.doc_id == doc_id:
            return doc
    raise AssertionError(f"Missing implementation doc {doc_id}")


def get_section_body(doc: ImplementationDoc, heading: str, *, level: int = 2) -> str:
    target = f"{'#' * level} {heading}"
    lines = doc.text.splitlines()
    capture = False
    body: list[str] = []

    for line in lines:
        if line == target:
            capture = True
            continue

        if capture and line.startswith("#"):
            marker, _space, _rest = line.partition(" ")
            if marker and set(marker) == {"#"} and len(marker) <= level:
                break

        if capture:
            body.append(line)

    if not capture:
        raise AssertionError(f"Missing section {target} in {doc.path.name}")

    return "\n".join(body).strip()


def get_section_bullets(doc: ImplementationDoc, heading: str, *, level: int = 2) -> list[str]:
    body = get_section_body(doc, heading, level=level)
    return [_strip_wrapping_backticks(line[2:].strip()) for line in body.splitlines() if line.startswith("- ")]


def extract_dependency_ids(doc: ImplementationDoc) -> list[str]:
    body = get_section_body(doc, "Dependencies On Earlier Docs")
    return re.findall(r"\[(\d{2})-[^\]]+\.md\]", body)


def extract_list_after_label(body: str, label: str) -> list[str]:
    lines = body.splitlines()
    capture = False
    items: list[str] = []

    for line in lines:
        if line.strip() == label:
            capture = True
            continue

        if not capture:
            continue

        if line.startswith("- "):
            items.append(_strip_wrapping_backticks(line[2:].strip()))
            continue

        if items and line.strip():
            break

    return items


def extract_route_groups(doc: ImplementationDoc) -> list[tuple[str, str]]:
    body = get_section_body(doc, "Route Groups", level=3)
    routes: list[tuple[str, str]] = []

    for line in body.splitlines():
        if not line.startswith("- "):
            continue

        route_literal = _strip_wrapping_backticks(line[2:].strip())
        match = re.match(r"(?P<method>GET|POST|PATCH|PUT|DELETE) (?P<path>/\S+)$", route_literal)
        if match:
            routes.append((match.group("method"), match.group("path")))

    return routes


def extract_persistence_models(doc: ImplementationDoc) -> set[str]:
    body = get_section_body(doc, "Canonical Persistence Models", level=3)
    return set(re.findall(r"^#### ([A-Za-z][A-Za-z0-9]+)$", body, re.MULTILINE))


def extract_backticked_model_names(doc: ImplementationDoc) -> set[str]:
    return set(re.findall(r"`([A-Z][A-Za-z0-9]+)`", doc.text))


def _strip_wrapping_backticks(value: str) -> str:
    if value.startswith("`") and value.endswith("`"):
        return value[1:-1]
    return value
