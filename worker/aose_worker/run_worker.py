import os

from redis import Redis
from rq import Worker, Queue

from aose_worker.router import RouteResultType, route


def process_work_item(work_item_id: str, stage: str) -> dict:
    """
    RQ job entry point. Routes a WorkItem by stage and returns the route result.

    This is the minimal integration path from the worker consume loop to the
    stage router (SPEC-C1). Full handler execution, DB interaction, structured
    event writes, and budget enforcement are implemented in later specs.

    Args:
        work_item_id: the persisted WorkItem primary key.
        stage: the WorkItem.stage value at enqueue time.

    Returns:
        A dict describing the routing outcome (result_type, stage, error_code).
    """
    result = route(stage)

    if result.result_type == RouteResultType.HANDLER_DISPATCH:
        # Business logic stub — actual handler execution is deferred (PH-EPIC-C-001).
        result.handler({"work_item_id": work_item_id, "stage": stage})

    return {
        "work_item_id": work_item_id,
        "result_type": result.result_type.value,
        "stage": result.stage,
        "error_code": result.error_code,
        "terminal_event_type": result.terminal_event_type,
    }


def main():
    redis_url = os.getenv("REDIS_URL", "redis://redis:6379/0")
    queue_name = os.getenv("RQ_QUEUE", "default")
    burst = os.getenv("RQ_BURST", "0") == "1"

    conn = Redis.from_url(redis_url)
    q = Queue(queue_name, connection=conn)
    w = Worker([q], connection=conn)
    w.work(burst=burst)


if __name__ == "__main__":
    main()
