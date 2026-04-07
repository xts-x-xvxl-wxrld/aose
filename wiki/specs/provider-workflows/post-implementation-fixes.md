# Phase 3 Post-Implementation Fixes

## Purpose And Scope

- Record the concrete mismatches found after implementing the Phase 3 provider-backed vertical slice.
- Replace abstract ambiguity-tracking with a correction list grounded in current runtime behavior.
- Make the remaining work explicit before declaring the Phase 3 path fully complete in practice.

## Status

- The Phase 3 provider-backed runtime, workflow wiring, reasoning layer, chat integration, migrations, and test coverage now exist in code.
- The implementation exists, but Phase 3 is not fully complete yet.
- The repository is in strong shape from a contract and test perspective:
  - provider-backed adapters exist
  - workflow/runtime/chat tests are green
  - `pytest -q` passes
- The local container story is materially better than it was when this doc was first written:
  - `docker-compose.yml` now loads `.env` into the API services
  - containerized database URLs now target the `postgres` service rather than `localhost`
  - the `api` service now runs `alembic upgrade head` before starting `uvicorn`
  - a production-like `api` path and a fake-auth live-dev `api-test` path now exist side by side
- The original fix pass largely landed in code:
  - degraded account-search terminal outcomes now exist
  - account-search fallback wiring to Google Local Places now exists
  - degraded assistant-summary selection now exists
  - noisy reasoning-validation emission during provider failure has been tightened
  - a developer-facing run debug endpoint now exists
- Follow-up repo review on `April 5, 2026` confirms that several earlier runtime fixes now exist in code:
  - account-search fallback now explicitly treats `provider_bad_response` as fallback-eligible
  - Firecrawl account-search now retries through compatibility request profiles
  - the OpenAI structured normalizer now retries through a compatibility response-format profile
  - the contact-search `_normalize_domain` crash path now has regression coverage
  - contact-search now returns a clearer internal-failure summary than the earlier generic unexpected-error text
- The remaining issues are now concentrated in live verification, diagnosing any newly observed provider-contract drift, and one narrower resilience gap in contact-search fallback trigger coverage if `provider_bad_response` reappears there.
- This file is now the Phase 3 closure and correction document for the implemented slice set.

## Decision Lock

- This fix pass is for Phase 3 closure, not a new provider-strategy rewrite.
- Firecrawl remains the primary account-search and account-research provider.
- Google Local Places remains an approved account-search source and should be usable as a backup path when appropriate.
- Findymail remains the default primary contact-search provider and Tomba remains fallback-only for contact search in Phase 3.
- Chat remains the only user-facing workflow trigger.
- The product should distinguish:
  - true no-results
  - degraded execution due to provider failure
  - fallback success
  - fallback exhausted

## Implemented Areas That Are In Good Shape

- Central provider config and runtime wiring exist.
- Workflow execution no longer depends on null toolsets in the main Phase 3 path.
- Additive run-event taxonomy exists for reasoning, candidate decisions, and routing.
- The account search, account research, and contact search workflows execute through the current chat/run foundation.
- The repo has strong deterministic coverage for provider adapters, workflow behavior, migrations, and chat APIs.
- The live-dev path now proves:
  - fake-auth tenant access works through the real app
  - seller and ICP setup work through the real API
  - durable thread, message, run, debug, snapshot, and artifact state all persist correctly in the containerized environment

## Post-Implementation Findings

### 1. The Original Degraded No-Results Misclassification Is Fixed In Code

- The original account-search issue that motivated this doc is no longer current.
- In the live smoke run on `April 4, 2026`, account search did not collapse into ordinary `no_results`.
- The terminal run outcome was `provider_failure`.
- The final assistant message said:
  - `Hmm, looks like one of our sources is down, and I couldn't continue with a reliable search path from the available data.`
- That means the user-visible degraded-state path is now behaving more truthfully than it did when this document was first written.

### 2. Account Search Fallback Wiring Exists, But The Live Trigger Coverage Is Still Incomplete

- The earlier statement that account search had no Google Local Places fallback is now outdated.
- The current implementation does wire Google Local Places as an account-search fallback path.
- However, the live smoke run exposed a narrower problem:
  - the primary Firecrawl account-search calls failed with `provider_bad_response`
  - fallback was not attempted
  - the current fallback trigger set only covers:
    - `provider_unavailable`
    - `provider_rate_limit`
    - `provider_quota_exceeded`
- This means the resilience design exists, but the live trigger rules do not yet cover all provider-failure shapes that can block discovery in practice.

### 3. Reasoning-Validation Noise During Provider Failure Is Improved

- The earlier finding that provider failure still emitted misleading `reasoning.failed_validation` noise is no longer the active issue.
- In the live `account_search` and `account_research` smoke runs:
  - provider attempts recorded `provider_bad_response`
  - the debug bundles did not show spurious reasoning-validation events
- This fix appears to be holding in practice.

### 4. User-Facing Degraded Messaging Is Implemented For Account Search

- The earlier finding that degraded assistant messaging did not exist is now outdated.
- The account-search live smoke run surfaced the dedicated degraded terminal summary instead of ordinary no-results language.
- The current remaining issue is not summary absence.
- The remaining issue is whether the correct degraded summary family is selected for all live provider-failure shapes and fallback paths.

### 5. The Developer-Facing Debug Surface Exists And Was Useful In Live Smoke

- The earlier statement that there was no developer-facing debug surface is no longer true.
- The run-debug endpoint now exposes:
  - provider attempts
  - fallback decisions
  - reasoning-validation state
  - terminal outcome family
  - summary-selection context
- We used that endpoint successfully during live smoke to confirm:
  - account search ended in `provider_failure`
  - fallback was allowed but not attempted
  - account research completed with persisted outputs despite upstream `provider_bad_response` events
  - contact search failed after provider search due to an internal code error rather than an external auth/setup problem

### 6. Docker Compose Provider Wiring Was A Real Gap, But Is Now Addressed

- The earlier gap was real:
  - `.env` had been excluded from the Docker build context
  - `docker-compose.yml` did not make the Phase 3 provider settings reliably visible in the running API container
- The current repo now addresses that setup problem:
  - `.env` is no longer excluded by `.dockerignore`
  - `docker-compose.yml` uses `env_file` for `api` and `api-test`
  - the containerized env path now includes Phase 3 provider settings in the running API service
- The remaining work here is verification rather than missing config wiring:
  - prove the live provider-backed chat path through the current containerized API
  - keep the container env model aligned with the production-like auth/runtime path

### 7. The Local Container Startup Path Is Now More Migration-Ready, But Still Needs Verification

- The original issue was that the dev database could be missing conversation tables until `alembic upgrade head` was run manually.
- The current container path is now materially better:
  - `api` runs `alembic upgrade head` before starting the server
  - `api-test` does the same before starting the live-reload dev server
  - Alembic now follows the settings-driven database URL instead of depending on a stale localhost default in `alembic.ini`
- This is no longer primarily a setup-gap finding.
- The remaining concern is operational proof:
  - confirm the migrated startup path behaves cleanly on rebuild/recreate
  - confirm the same path works with the current auth split and provider configuration

### 8. Live Smoke Verification Is Now Partially Complete And Reveals Two New Runtime Problems

- We now have stronger live verification than when this doc was first written.
- The local verification setup is now stronger than it was when this doc was first written:
  - the production-like `api` service can run with the current auth configuration
  - the `api-test` service now provides a fake-auth live-dev path for containerized verification
  - containerized provider credentials and migration startup are now in place
- A full chat-thread smoke path was exercised on `April 4, 2026` through the live-dev container path using the persisted `dev-user` identity.
- What succeeded live:
  - fake-auth identity resolution
  - tenant creation
  - seller-profile creation
  - ICP-profile creation
  - chat-triggered account search run creation and durable event/debug persistence
  - chat-triggered account research completion with:
    - durable thread/run state
    - persisted research snapshot
    - persisted research brief artifact
- Newly discovered live-runtime problems:
  - account search:
    - Firecrawl search returned `provider_bad_response`
    - the OpenAI content normalizer also returned `provider_bad_response`
    - fallback did not trigger because `provider_bad_response` is outside the current fallback trigger set
  - contact search:
    - Findymail provider search did return candidates
    - the workflow then crashed with a `NameError` on `_normalize_domain` during fallback candidate conversion
    - no contacts were persisted
- Phase 3 is therefore implemented, strongly tested, and meaningfully smoke-verified, but not yet closed from a live-runtime completion perspective.

### 9. April 5, 2026 Live Rerun Shows The Original Provider-Bad-Response Failures No Longer Reproducing On The Same Paths

- A new live smoke rerun was executed on `April 5, 2026` through the `api-test` fake-auth container path.
- A fresh account-search run using the current Phase 3 live-dev path completed with:
  - terminal outcome `no_results`
  - no fallback attempt
  - Firecrawl web-search attempts completing without `provider_bad_response`
  - OpenAI reasoning validation succeeding without `provider_bad_response`
- The original `April 4, 2026` account-search prompt was also rerun against the previously used live thread context.
- That rerun no longer reproduced the earlier failure shape:
  - the terminal outcome was `no_results`, not `provider_failure`
  - Firecrawl completed without `provider_bad_response`
  - OpenAI completed without `provider_bad_response`
  - the degraded provider-failure assistant summary did not appear because the system did not observe an upstream provider outage on that rerun
- The original `April 4, 2026` account-research path was rerun against the same selected account context.
- That rerun completed successfully and no longer showed the earlier OpenAI `provider_bad_response` contract-compatibility issue.
- One live-provider issue did still surface in the rerun:
  - the OpenAI normalizer recorded `provider_rate_limit`
  - the workflow still completed successfully despite that rate-limit outcome
- The original `April 4, 2026` contact-search path was rerun against the same selected account context.
- That rerun completed successfully with persisted contacts instead of failing with an internal runtime exception.
- The earlier `_normalize_domain` crash therefore appears fixed in live use on the same path that failed on `April 4, 2026`.
- The current evidence now supports these narrower conclusions:
  - the original Firecrawl and OpenAI `provider_bad_response` failures from `April 4, 2026` no longer reproduce on the same live prompts we reran on `April 5, 2026`
  - the contact-search internal crash no longer reproduces on the same live contact-search path
  - account search can still legitimately end in true `no_results`, so a clean rerun does not guarantee accepted accounts for downstream smoke continuation
  - live fallback behavior for a real `provider_bad_response` event was not re-exercised on `April 5, 2026` because the upstream bad-response failure shape did not recur during the rerun

### 10. Repo Review On April 5, 2026 Confirms Several Fixes Are Landed In Code

- A focused repo review after the `April 5, 2026` rerun confirms that several items still listed below as future-looking fixes have already landed in implementation.
- Account-search fallback trigger coverage has been widened in code:
  - `provider_bad_response` is now included in the account-search fallback trigger set
  - regression coverage now proves Google Local Places fallback is used when the primary provider returns `provider_bad_response`
- Firecrawl account-search compatibility hardening now exists in the adapter:
  - the adapter first tries the preferred `/v2/search` request body
  - if Firecrawl rejects the stricter request shape, the adapter retries with narrower compatibility profiles instead of resending the same payload unchanged
  - fixture-backed adapter coverage now exists for this compatibility retry path
- OpenAI structured normalizer compatibility hardening now exists in the adapter:
  - the normalizer first tries `json_schema`
  - if that request shape is rejected, it retries with `json_object`
  - fixture-backed adapter coverage now exists for this compatibility retry path
- The contact-search `_normalize_domain` execution bug now appears fixed in code as well as in live rerun:
  - the workflow defines local domain normalization for provider-candidate conversion
  - regression coverage now proves provider-backed candidates can be converted and persisted without the earlier `NameError`
- The clearer contact-search internal-failure summary is also now implemented:
  - the workflow returns a dedicated `contact_search_internal_error` outcome
  - the assistant summary now explains that contact processing failed internally rather than surfacing only a generic unexpected-error message
- The remaining value of the fix list below is therefore to preserve these landed behaviors, verify them in live runtime, and capture the next layer of resilience work if provider-contract drift appears again.

### 11. April 6, 2026 Live Smoke Confirmed A Separate Account-Search Runtime Crash And Verified The Repair

- A fresh live smoke run on `April 6, 2026` reproduced a new account-search failure shape that was different from the earlier provider-bad-response issue:
  - Firecrawl completed both web-search attempts with evidence-bearing results
  - OpenAI reasoning validation completed and reported `1 accepted` and `9 rejected` account candidates
  - the workflow still failed with a generic unexpected-error terminal summary
- Container logs confirmed the real crash site:
  - the exception was raised in `_account_candidate_from_reasoning(...)`
  - the accepted reasoning candidate carried `evidence` entries using keys like `url` and `snippet`
  - `CandidateEvidenceRecord` rejected those keys because the internal account-search evidence schema expects `source_url` and `snippet_text` and forbids unknown fields
- This means the failure was not "Firecrawl found nothing."
- The real problem was a schema-conversion bug between:
  - the reasoning-layer account candidate evidence payload
  - the internal account-search evidence record model used before persistence
- The fix is now landed and confirmed:
  - account-search reasoning evidence is normalized before `CandidateEvidenceRecord` validation
  - legacy keys such as `url` and `snippet` are now mapped into the internal schema
  - regression coverage now proves this live failure shape no longer crashes conversion
- A fresh post-fix live smoke rerun on `April 6, 2026` against the `api-test` container path confirmed the repair:
  - the prior account-search runtime exception no longer reproduced
  - Firecrawl again returned evidence-bearing search results
  - OpenAI reasoning validation completed normally
  - the workflow ended cleanly in terminal outcome `no_results` instead of failing at runtime
- The current evidence therefore supports these narrower conclusions:
  - the April 6 account-search crash was a workflow-internal evidence-schema mismatch, not a Firecrawl search outage
  - the crash is now fixed in code and covered by regression tests
  - account search can still legitimately finish in true `no_results` after the crash fix if the ranked candidates do not satisfy the current acceptance rules

## Required Fixes

### Runtime And Workflow Fixes

- Preserve the now-correct distinction between true no-results and provider-degraded outcomes in terminal workflow results.
- Preserve the widened account-search fallback trigger handling so live provider failures like `provider_bad_response` continue to route into fallback when safe.
- Preserve the Firecrawl account-search compatibility retry behavior and extend its diagnostics if a new `provider_bad_response` shape appears in live runtime.
- Preserve the OpenAI normalizer compatibility retry behavior and extend its diagnostics if a new structured-output incompatibility appears in live runtime.
- Preserve the contact-search provider-candidate conversion path and its regression coverage so the earlier `_normalize_domain` runtime crash does not regress.
- Preserve the account-search reasoning-evidence normalization so legacy evidence keys like `url` and `snippet` do not crash candidate conversion after successful reasoning validation.
- Expand contact-search fallback trigger handling so `provider_bad_response` can be treated as fallback-eligible there too when safe and when no trustworthy primary contacts were produced.
- Preserve degraded provenance when a fallback source produces accepted account candidates.

### Chat And User-Visible Fixes

- Preserve the current degraded assistant-summary behavior for provider failure and fallback behavior.
- Ensure the final assistant summary continues to say, when true:
  - primary provider failed
  - backup source was attempted
  - backup succeeded or backup was exhausted
- Preserve the rule that ordinary no-results phrasing must not be used when the system knows the primary provider path failed.
- Preserve the clearer contact-search internal-failure summary path that replaced the earlier generic unexpected-error wording.
- If a future live contact-search failure is provider-specific rather than internal, add the same kind of explicit degraded summary family there instead of collapsing back to generic failure text.

### Developer Experience Fixes

- Preserve the current developer-facing run debug surface.
- Keep it possible to explain a run without manual ad hoc SQL inspection.
- Continue exposing provider attempts, fallback decisions, reasoning-validation state, and final summary selection in that debug view.
- Add enough failure detail to quickly distinguish:
  - upstream provider incompatibility
  - internal workflow code errors
  - fallback-not-triggered policy outcomes

### Environment And Verification Fixes

- Preserve the current container env wiring that passes Phase 3 provider settings into the API services.
- Preserve the startup migration path that migrates the database before the containerized API begins serving traffic.
- Validate the production-like `api` path and the fake-auth live-dev `api-test` path with explicit smoke checks.
- Add an explicit live smoke checklist for:
  - account search
  - account research
  - contact search
- Record the live smoke outcomes and newly discovered runtime failures in this document or its owning rollout docs after each major verification pass.

## Proposed Fix Implementation

### 1. Account Search Fallback Trigger Coverage

- Preserve the current account-search fallback trigger policy that already treats `provider_bad_response` as a fallback-eligible degraded outcome when:
  - the failing provider is the primary Firecrawl search path
  - no trustworthy primary results were produced
  - the fallback provider is configured
- Keep the fallback decision explicit in durable run events so debug output still shows:
  - primary provider failed
  - why fallback was allowed
  - whether fallback produced usable candidates
- Preserve the rule that ordinary no-results language must not be used when this degraded path is taken.

### 2. Firecrawl Account-Search Compatibility Repair

- Preserve the Firecrawl compatibility-retry adapter behavior now in code and extend it so `provider_bad_response` is easier to diagnose in live runs:
  - include enough structured failure detail to distinguish HTTP `4xx`, invalid JSON, and unexpected payload shape
  - preserve provider response metadata in debug-friendly form without requiring ad hoc SQL inspection
- Keep the current `/v2/search` request-profile strategy and harden it further only if live Firecrawl returns a new incompatible payload shape.
- Preserve adapter checks for compatibility retries and add captured live fixtures if a new failure shape is observed.
- Continue preferring narrower request profiles over broad workflow-level retries that resend the same incompatible payload.

### 3. OpenAI Structured Normalizer Compatibility Repair

- Preserve the OpenAI normalizer compatibility strategy as a provider-contract compatibility feature, not just a transient retry candidate.
- Pin or verify a model/configuration that supports the current structured-output request shape used by the normalizer path.
- Preserve the current response parsing tolerance for the response variants currently returned by the provider when structured output succeeds.
- Preserve the current behavior where structured-normalizer `provider_bad_response` can degrade into deterministic parsing when safe instead of silently collapsing the workflow into an empty result set.
- Preserve existing fixture-backed adapter checks and add captured live fixtures for any newly observed incompatible response shape.

### 4. Contact Search Runtime Crash Repair

- Preserve the current `_normalize_domain` fix in the contact-search workflow and keep the provider-candidate conversion path covered by regression tests.
- Consider moving domain normalization to a shared helper later if that reduces duplication across workflow and adapter modules, but do not destabilize the now-working path during this fix pass.
- Preserve the distinction between:
  - upstream provider failure
  - fallback-policy choice
  - internal workflow code error

### 5. Clearer User-Facing Contact Failure Summaries

- Preserve the current clearer internal contact-search failure summary now that it exists in code.
- At minimum, distinguish:
  - provider-backed search failed upstream
  - fallback was attempted and exhausted
  - workflow crashed due to an internal code error after provider retrieval
- Keep the internal failure details available in the run-debug surface while presenting a concise degraded explanation in chat.

### 6. Proposed Retry Functionality For Specialized Agents And Provider Tools

- A generic "specialized agent retries its own failed provider request" mechanism is not sufficient by itself if the agent cannot modify the provider request body.
- The more practical design is an adapter-owned or workflow-owned retry strategy where the code, not the agent prompt, controls the retry variants.
- Recommended shape:
  - the first attempt uses the preferred provider request contract
  - if the provider returns a retry-eligible failure such as `provider_bad_response` from a known contract-drift case, the adapter or workflow retries with a narrower or compatibility-mode request body
  - the retry attempt records that a compatibility fallback was used
- For example:
  - Firecrawl retry could omit optional fields that the live API rejects
  - OpenAI normalizer retry could switch to a simpler structured-output request shape or a deterministic fallback path
- This means the specialized agent does not need raw authority to rewrite request bodies directly. Instead, it can choose from a small set of pre-approved retry modes exposed by code.
- If agent-directed correction is desired later, it should be introduced as an explicit contract such as:
  - request builder returns a named retry profile
  - workflow allows `strict`, `compatibility`, or `minimal` provider modes
  - adapter chooses the concrete body for each mode
- Do not add an unconstrained self-healing retry loop that simply resends the same bad request or lets the agent invent arbitrary provider payloads. That would make failures harder to debug and could create unpredictable provider behavior.

## Acceptance Criteria For Closure

- A primary-provider outage is no longer presented to the user as an ordinary no-results case.
- Account search attempts Google Local Places fallback when Firecrawl fails and the fallback trigger rules allow it.
- The fallback trigger rules cover the real provider-failure shapes encountered in live use, or those shapes are normalized into covered categories.
- Fallback usage is visible in durable run state and explainable in chat.
- Reasoning-validation events are emitted only when they describe a real validation failure rather than an upstream provider outage.
- A developer can inspect one workflow run and understand why the terminal assistant message was selected.
- The containerized API path can actually use configured Phase 3 providers in local development.
- The containerized API path can start against a migrated database without requiring a separate manual migration step first.
- The container setup supports both:
  - a production-like authenticated API path
  - a fake-auth live-dev path for containerized testing and smoke verification
- Live smoke verification exists for chat-triggered account search, account research, and contact search.
- The live smoke path can complete all three workflows without:
  - provider-contract failures blocking discovery unexpectedly
  - internal workflow runtime exceptions preventing persistence
- The specific April 6 account-search post-validation conversion crash no longer reproduces in the live `api-test` smoke path.

## Verification Additions Required

- Preserve workflow tests proving Firecrawl failure can trigger Google Local Places fallback.
- Preserve workflow tests proving true no-results and provider-degraded no-results are not conflated.
- Preserve chat tests proving degraded assistant summaries are shown when a source is down.
- Preserve event/debug tests proving fallback decisions and summary-selection causes are durably inspectable.
- Preserve regression coverage for the contact-search `_normalize_domain` crash path.
- Preserve regression coverage for account-search reasoning evidence that arrives with legacy keys like `url` and `snippet`.
- Add live or fixture-backed adapter checks for any newly observed runtime shapes beyond the compatibility retries already covered for:
  - Firecrawl account-search request/response compatibility
  - OpenAI structured-normalizer request/response compatibility in the current provider mode
- Add regression coverage if contact-search fallback policy is widened to treat `provider_bad_response` as fallback-eligible.
- Add local live-smoke instructions or automation for the full three-workflow chat path, including:
  - the production-like `api` container path
  - the fake-auth live-dev `api-test` container path

## Owning Follow-Up Docs

- Reconcile the fixes above back into:
  - `docs/phase3/provider-backed-vertical-slice/03-account-search-provider-slice.md`
  - `docs/phase3/provider-backed-vertical-slice/06-chat-and-frontend-completion.md`
  - `docs/phase3/provider-backed-vertical-slice/07-rollout-and-verification.md`
  - the current Phase 4 resilience/debugging doc set where the fix grows into a broader reliability feature

## Closure Rule

- Do not declare the Phase 3 provider-backed path fully complete while the live account-search path still fails on current provider contracts without reaching the intended fallback behavior.
- Do not declare the Phase 3 provider-backed path fully complete while contact search can still fail on an internal runtime exception after successful provider candidate retrieval.
- Do not declare the live verification story complete while the three-workflow chat path still requires manual data seeding to continue past a live discovery failure.
- Once the implementation matches the accepted Phase 3 behavior and the remaining resilience fixes are either completed or intentionally moved into a clearly owned later phase, this file may be reduced to a short closure note.

## Assumptions And Defaults

- Full closure is the implementation target for this pass.
- No major public API redesign is required for the fix pass.
- Additive event-category refinement is allowed if it improves debugging and summary accuracy.
- The fix pass should preserve the current tenant, thread, run, and evidence model rather than introducing a parallel system.
