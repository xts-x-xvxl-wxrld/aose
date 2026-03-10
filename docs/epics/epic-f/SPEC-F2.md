# spec-f2 — Rule scoring v0

## Goal
Implement the Epic F v0.1 deterministic rule engine that computes account-level `fit` and `intent` scores, plus confidence and evidence-linked reasons, using only the locked rule set and no hidden weights.

## Scope boundary
**In scope:** exact positive and negative rules, category usage constraints, normalization to `0..100`, confidence calculation, source trust handling, and reason construction.

**Out of scope:** promotion, queue orchestration, provider-specific fetch logic, contact-level scoring, draft generation, and any rules not explicitly present in the Epic F contract.

## Contract touchpoints
Fit scoring must use only account-scoped evidence relevant to segment and offer match.

Intent scoring must use only trigger-style evidence relevant to near-term buying or change signals.

`persona_fit` evidence is allowed to exist canonically but is ignored for Epic F account scoring v0.1.

Source trust ordering remains deterministic:

1. `registry_api`
2. `first_party_site`
3. `official_profile`
4. `reputable_directory`
5. `general_web_extract`

## Required scoring rules

### Fit positive rules
- `industry_or_segment_exact_match = +35`
- `industry_or_segment_adjacent_match = +20`
- `offer_use_case_match = +25`
- `geography_match = +15`
- `size_band_match = +10`
- `technographic_match = +15`

### Fit exclusivity
- `industry_or_segment_exact_match` is exclusive with `industry_or_segment_adjacent_match`
- Both may not fire together for the same scorecard

### Fit negative rules
- `missing_website_and_registry = -15`
- `conflicting_firmographics_unresolved = -10`

### Intent positive rules
- `hiring_signal = +35`
- `expansion_signal = +35`
- `tender_or_procurement_signal = +35`
- `new_capability_or_new_line_signal = +20`

### Intent negative rules
- `stale_signal_over_180_days = -15`
- `contradictory_trigger_evidence = -10`

Both score families must normalize to integer scores between `0` and `100`, with floor and ceiling applied after rule aggregation.

No hidden multipliers, latent weights, or model-only adjustments are allowed.

## Evidence usage rules
- Fit may use only `firmographic` and `technographic` evidence categories
- Intent may use only `trigger` evidence
- `persona_fit` is ignored for Epic F account scoring v0.1 and must not affect either fit or intent totals
- Only evidence IDs actually consumed by rules may appear in stored reasons or in the evidence snapshot hash
- Reasons must be evidence-backed and code-based

## Confidence rules

### Fit confidence
- High = `0.85`
  - requires at least 2 distinct sources
  - requires at least 2 distinct categories
- Medium = `0.65`
  - requires at least 1 distinct source
  - requires at least 1 distinct category
- Low = `0.40`

#### Fit penalties
- `conflicting_sources = 0.20`
- `low_trust_only = 0.10`

Clamp final fit confidence to `0.0..1.0`.

### Intent confidence
- High = `0.85`
  - requires at least 2 distinct trigger sources
- Medium = `0.65`
  - requires at least 1 distinct trigger source
- Low = `0.40`

#### Intent penalties
- `conflicting_trigger_sources = 0.20`
- `stale_only_signals = 0.10`

Clamp final intent confidence to `0.0..1.0`.

## Reason construction
Each fired scoring rule must yield a structured reason object with:

- `code`
- deterministic `text`
- supporting `evidence_ids`

The text should be template-based and stable for a given rule code and evidence set so reruns do not produce semantically drifting prose.

Unsupported reasons, empty evidence lists, or free-form summaries without evidence IDs are forbidden.

If intent has no trigger evidence, the engine must not fabricate a negative narrative. It must store:

- `intent.score = 0`
- `intent.confidence` per rule
- `intent.reasons = []`

## Deliverables
- A pure rule engine for fit scoring
- A pure rule engine for intent scoring
- A confidence calculator for fit and intent
- A deterministic reason formatter that emits the locked reason shape
- Unit tests covering:
  - every positive and negative rule
  - exclusivity between exact and adjacent industry match
  - confidence penalties
  - ignored `persona_fit` evidence
  - zero-trigger behavior

## Acceptance checks
- Every stored reason references one or more evidence IDs
- No score is ever below `0` or above `100`
- `persona_fit` evidence does not change fit or intent in Epic F v0.1
- Exact and adjacent industry match cannot both score in the same run
- No trigger evidence yields `intent.score = 0` and `intent.reasons = []`
- The same evidence set always yields the same rule firings, score totals, confidences, and reason codes

## AI build prompt
Implement `spec-f2` for Epic F as a deterministic rule-based scorer.

Do not add any rules or weights beyond the contract.

### Fit rules
- `industry_or_segment_exact_match +35` exclusive with `industry_or_segment_adjacent_match +20`
- `offer_use_case_match +25`
- `geography_match +15`
- `size_band_match +10`
- `technographic_match +15`
- negatives:
  - `missing_website_and_registry -15`
  - `conflicting_firmographics_unresolved -10`

### Intent rules
- `hiring_signal +35`
- `expansion_signal +35`
- `tender_or_procurement_signal +35`
- `new_capability_or_new_line_signal +20`
- negatives:
  - `stale_signal_over_180_days -15`
  - `contradictory_trigger_evidence -10`

Fit may use only firmographic and technographic evidence.

Intent may use only trigger evidence.

Ignore `persona_fit` evidence entirely for Epic F account scoring.

Normalize both scores to integer `0..100`.

Compute confidences exactly per the contract’s high/medium/low rules and penalties.

Emit structured reasons with:

- `code`
- deterministic `text`
- non-empty `evidence_ids`

If no trigger evidence exists, persist `intent.score=0` and `intent.reasons=[]`.

Add tests for:

- every rule
- exclusivity
- confidence penalties
- ignored categories
- deterministic outputs