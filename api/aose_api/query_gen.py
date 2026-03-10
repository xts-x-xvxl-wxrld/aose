"""
Deterministic query object generation from a stored SellerProfile.

Rules:
- No external calls, no LLM, no network, no mutable runtime state.
- Same SellerProfile input always produces the same QueryObject list in the same order.
- Generates between 3 and 10 QueryObjects for any valid profile (simple_heuristic_v0).

query_object_id format: qo:<sha256(seller_id|buyer_context)>
This is a local heuristic implementation detail, not a globally frozen canonical ID formula.

Tier ordering (all priorities assigned in strictly descending order):
  Tier 1: one QO per persona in offer.who (up to 3)      — priority 1.0, 0.9, 0.8
  Tier 2: language variants for first persona              — priority 0.65, 0.60, ...
  Tier 3: channel variants for first persona               — priority 0.50, 0.45, ...
  Fallback: generic positional variants until count >= 3   — priority 0.30, 0.25, ...
"""

from __future__ import annotations

import hashlib

from aose_api.models import SellerProfile

# Static conservative exclusions appended after seller avoid_claims.
_STATIC_EXCLUSIONS = ["spam", "cold-call", "unsolicited bulk"]


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _dedup_ordered(items: list[str]) -> list[str]:
    """Remove duplicates while preserving insertion order."""
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        if item not in seen:
            seen.add(item)
            result.append(item)
    return result


def generate_query_objects(profile: SellerProfile) -> list[dict]:
    """
    Deterministically generate 3-10 query object dicts from a stored SellerProfile.

    Returns a list of dicts ready to be inserted as QueryObject rows.
    Each dict contains all required QueryObject fields.
    Output count is always in [3, 10]. Output order is stable.
    """
    personas: list[str] = list(profile.offer_who or [])[:3]
    if not personas:
        personas = ["general buyer"]

    where_str = ", ".join(profile.offer_where or []) or "any market"

    # Keywords: first 5 tokens from offer_what + first 2 tokens of each positioning item
    what_tokens = (profile.offer_what or "").split()[:5]
    positioning_tokens: list[str] = []
    for p in profile.offer_positioning or []:
        positioning_tokens.extend(p.split()[:2])
    base_keywords = _dedup_ordered(what_tokens + positioning_tokens)

    # Exclusions: seller avoid_claims first, then static list
    base_exclusions = _dedup_ordered(
        list(profile.constraints_avoid_claims or []) + _STATIC_EXCLUSIONS
    )

    seen_contexts: set[str] = set()
    results: list[dict] = []

    def _make_and_add(
        buyer_context: str, priority: float, extra_kw: list[str] = ()
    ) -> None:
        if buyer_context in seen_contexts or len(results) >= 10:
            return
        seen_contexts.add(buyer_context)
        kws = _dedup_ordered(list(base_keywords) + list(extra_kw))
        rationale = (
            f"Targeting '{buyer_context}' based on seller offer: "
            f"{(profile.offer_what or '')[:60].rstrip()}."
        )
        results.append(
            {
                "query_object_id": f"qo:{_sha256(f'{profile.seller_id}|{buyer_context}')}",
                "seller_id": profile.seller_id,
                "buyer_context": buyer_context,
                "priority": round(priority, 2),
                "keywords": kws,
                "exclusions": list(base_exclusions),
                "rationale": rationale,
                "v": 1,
            }
        )

    # Tier 1: one QO per persona (up to 3)
    tier1_priorities = [1.0, 0.9, 0.8]
    for idx, persona in enumerate(personas):
        _make_and_add(f"{persona} in {where_str}", tier1_priorities[idx])

    # Tier 2: language variants using first persona
    languages: list[str] = list(profile.constraints_languages or [])
    first_persona = personas[0]
    for lang_idx, lang in enumerate(languages):
        _make_and_add(
            f"{first_persona} ({lang}) in {where_str}",
            round(0.65 - lang_idx * 0.05, 2),
            [lang],
        )

    # Tier 3: channel variants using first persona
    channels: list[str] = list(profile.constraints_allowed_channels or [])
    for ch_idx, ch in enumerate(channels):
        _make_and_add(
            f"{first_persona} via {ch} in {where_str}",
            round(0.50 - ch_idx * 0.05, 2),
            [ch],
        )

    # Fallback: pad to minimum 3 with generic positional variants
    fallback_idx = 0
    while len(results) < 3:
        _make_and_add(
            f"prospect type {fallback_idx + 1} in {where_str}",
            round(0.30 - fallback_idx * 0.05, 2),
        )
        fallback_idx += 1
        if fallback_idx > 10:
            break  # Safety guard — should not be reachable

    return results
