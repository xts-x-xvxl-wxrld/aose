# Code-Backed Semantic Work

## Purpose And Scope

- Describe the workflow decisions that are still implemented as code-heavy heuristics even though they depend on semantic understanding and context-sensitive judgment.
- Separate these items from Phase 4 resilience bugs.
- Provide a clean follow-on backlog for constrained LLM-backed services.
- Some smoke pain points are caused not by fallback correctness but by semantic decisions still being code-backed, especially account-search final selection and contact-search targeting.

## Principle

- Code should continue to own:
  - validation
  - retries
  - fallback safety rules
  - persistence
  - provenance
  - deterministic guardrails
- LLM-backed services should own semantic tasks such as:
  - planning
  - query strategy
  - persona interpretation
  - nuanced relevance scoring
  - context-sensitive synthesis

## Current Semantic Work Still Hardcoded

### 1. Account Search Final Selection

- Account-search query planning is now LLM-backed, which fixed the biggest deterministic bottleneck.
- But final candidate acceptance still relies on deterministic scoring and selection logic.
- Current code-backed semantic areas include:
  - `_score_candidate(...)`
  - deterministic `select_candidates(...)`
  - deterministic fallback query narrowing
- Why this is semantic:
  - good account acceptance often depends on nuanced fit interpretation, not simple text overlap
  - a company can be relevant even when ICP language does not appear verbatim
  - a company can also look superficially similar while still being a weak fit
- Recommended direction:
  - add a structured account-selection service that accepts normalized candidates plus seller and ICP context and returns ranked acceptance decisions with reasons

### 2. Account Research Planning And Deterministic Fallback Synthesis

- Account research still builds its research plan deterministically.
- It also still has a large deterministic fallback synthesis path.
- Current code-backed semantic areas include:
  - `_build_research_plan(...)`
  - `_select_primary_query(...)`
  - `_build_fallback_research_record(...)`
  - `_build_fit_to_icp_summary(...)`
  - `_build_buying_signals(...)`
  - `_build_risks(...)`
  - `_build_uncertainty_notes(...)`
- Why this is semantic:
  - research planning should decide which public evidence is most valuable to gather
  - seller fit, ICP fit, risk, and uncertainty are judgment-heavy synthesis tasks
  - deterministic string overlap is a weak substitute for actual contextual reasoning
- Recommended direction:
  - add an LLM-backed research planner
  - keep durable evidence gathering in code
  - keep a constrained fallback summarizer only for failure-containment, not as the primary synthesis strategy

### 3. Contact Search Targeting And Persona Framing

- Contact search already uses structured reasoning for final ranking, but the upstream targeting logic is still heavily heuristic.
- Current code-backed semantic areas include:
  - `_build_search_queries(...)`
  - `_build_target_personas(...)`
  - `_build_selection_criteria(...)`
  - `_normalize_role_hints(...)`
- Why this is semantic:
  - buyer roles are rarely captured by simple keyword extraction
  - persona intent depends on seller context, research snapshot context, and account context together
  - role hints such as "operations leader" or "champion" are often too blunt when derived from static rules
- Recommended direction:
  - add a structured contact-targeting planner that produces:
    - target personas
    - title hints
    - search queries
    - selection criteria
    - routing hints for providers

### 4. Contact Provider Routing

- Contact-search provider routing is still rule-based and default-first.
- Current code-backed semantic areas include:
  - default primary/fallback routing policy
  - explicit fallback triggers
- Why this is semantic:
  - the best provider can depend on geography, company type, contact seniority, and the kind of buyer being targeted
- Recommended direction:
  - keep hard safety guardrails in code
  - add an LLM-backed routing advisor that proposes the best provider strategy inside those guardrails

### 5. Chat Intent Routing

- The chat orchestrator is still regex-based.
- Current code-backed semantic areas include:
  - workflow intent classification
  - active-thread follow-up interpretation
  - ambiguity handling for natural user requests
- Why this is semantic:
  - users do not always ask in explicit verbs like "find accounts" or "research this account"
  - mixed-intent follow-ups and subtle workflow switches are better handled through structured intent reasoning than regex matches
- Recommended direction:
  - replace regex-first routing with a constrained LLM router that emits:
    - requested workflow
    - confidence
    - missing inputs
    - whether the message is a status check, follow-up, or new run request

## Prioritization

### Highest Priority

- Account research planning and fallback synthesis
- Contact-search targeting and persona framing

### Medium Priority

- Account-search final selection and scoring
- Chat intent routing

### Lower Priority

- Contact-provider routing refinement

## Recommendation

- Do not treat this backlog as "remove code and let the model do everything."
- The right move is to introduce constrained LLM-backed services with typed outputs while preserving workflow-owned guardrails and durability.
