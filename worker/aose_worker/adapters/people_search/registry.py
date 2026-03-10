"""
Static adapter registry for people search.

Keys must match stable provider enum values.
No reflection-based discovery or fuzzy matching.
"""

from __future__ import annotations

from .base import PeopleSearchAdapter
from .dummy_predictable import DummyPredictablePeopleAdapter

_REGISTRY: dict[str, PeopleSearchAdapter] = {
    "dummy_predictable_people": DummyPredictablePeopleAdapter(),
}

_DEFAULT_ADAPTER = "dummy_predictable_people"


def get_adapter(name: str | None) -> PeopleSearchAdapter:
    """
    Return the registered PeopleSearchAdapter for the given name.

    Defaults to dummy_predictable_people (PH-EPIC-G-001) when name is None.

    Raises:
        ValueError: If name is provided but not registered.
    """
    if not name:
        return _REGISTRY[_DEFAULT_ADAPTER]
    adapter = _REGISTRY.get(name)
    if adapter is None:
        raise ValueError(
            f"Unknown people search adapter: {name!r}."
            f" Registered: {sorted(_REGISTRY)}"
        )
    return adapter


def registered_adapter_names() -> list[str]:
    """Return sorted list of registered adapter names."""
    return sorted(_REGISTRY)
