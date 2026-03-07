# worker/AGENT.md — RQ Worker Service

## Purpose

The worker is the organ runtime. It pulls WorkItems off a Redis queue and routes each to the correct organ handler based on `WorkItem.stage`. Each organ reads one WorkItem, writes canonical outputs to Postgres, emits a StructuredEvent, and enqueues the next WorkItem.

## Entry point

| File | Role |
|------|------|
| `worker/aose_worker/run_worker.py` | Worker bootstrap — connects to Redis, starts RQ Worker |

## How it works

```python
# Simplified view of run_worker.py
conn = Redis.from_url(REDIS_URL)
q = Queue(RQ_QUEUE, connection=conn)
worker = Worker([q], connection=conn)
worker.work(burst=burst)  # burst=True exits when queue empties
```

RQ dispatches jobs to Python functions. The job function receives a WorkItem, processes it, and enqueues the next stage.

## Configuration (env vars)

| Variable | Default | Used for |
|----------|---------|---------|
| `REDIS_URL` | `redis://redis:6379/0` | Redis connection |
| `RQ_QUEUE` | `default` | Queue name to listen on (PH-003) |
| `RQ_BURST` | `0` | Set to `1` for one-shot mode (drains queue then exits) |
| `DATABASE_URL` | _(required)_ | Postgres DSN for organ handlers that write canonical records |

## Adding a new organ handler

1. Create `worker/aose_worker/organs/<stage_name>.py` with a `handle(work_item: dict) -> None` function.
2. The handler must:
   - Check `idempotency_key` before writing side effects (replay safety)
   - Decrement `attempt_budget.remaining` before each external call; park with `budget_exhausted` at zero
   - Write a `StructuredEvent` on completion (inputs, outputs, metrics, outcome, error_code)
   - Enqueue the next WorkItem (or park with a reason code) — never call another organ directly
3. Register the handler in the stage router (to be created in Epic B+).
4. Add a test in `worker/tests/`.

## Stage vocabulary

Handlers must use these exact stage strings (from `docs/data-spine/DATA-SPINE-v0.1.md` §5):

```
seller_profile_build | query_objects_generate | account_discovery |
intent_fit_scoring   | people_search          | contact_enrichment |
copy_generate        | approval_request       | sending_dispatch   |
parked:<reason_code>
```

Reason codes for parking: `contract_error | transient_error | budget_exhausted | no_signal | policy_blocked | needs_human`

## WorkItem shape (what the worker receives)

```json
{
  "work_item_id": "wi_...",
  "entity_ref": { "type": "account", "id": "account:SI-1234567" },
  "stage": "account_discovery",
  "payload": { "v": 1, "data": { "query_object_id": "q_87f1" } },
  "attempt_budget": { "remaining": 3, "policy": "standard" },
  "idempotency_key": "acctdisc:account:SI-1234567:q_87f1:v1",
  "trace": { "run_id": "...", "policy_pack_id": "safe_v0_1" },
  "created_at": "2026-02-25T10:12:33Z"
}
```

Full schema: `docs/data-spine/DATA-SPINE-v0.1.md` §2.

## Testing

```
worker/tests/
└── test_worker.py   # Module existence test (skipped on Windows — fork incompatibility with RQ)
```

Run tests: `make test` (runs inside the worker container).

**Windows note:** RQ uses `os.fork()` which is not available on Windows. Worker tests are skipped on `sys.platform == "win32"`. Always run via Docker.

## Dev commands

```bash
make dev    # Start full stack including this worker
make test   # Run worker tests in container
make lint   # Ruff lint worker/
make fmt    # Ruff format worker/
```

## Safety constraint

`SEND_ENABLED=false` by default. The `sending_dispatch` organ must check this flag before creating any `SendAttempt`. If false, park the WorkItem with status `queued` and zero provider side effects.
