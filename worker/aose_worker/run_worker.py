import os

from redis import Redis
from rq import Worker, Queue


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
