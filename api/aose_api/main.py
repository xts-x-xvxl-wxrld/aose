from fastapi import FastAPI, HTTPException
import os
import psycopg
from psycopg import OperationalError

app = FastAPI(title="AOSE API")


@app.get("/healthz")
def healthz():
    db_url = os.getenv("DATABASE_URL")
    if db_url:
        try:
            with psycopg.connect(db_url) as conn:
                conn.execute("SELECT 1")
        except OperationalError:
            raise HTTPException(status_code=503, detail="Database connection failed")
    return {"status": "ok", "env": os.getenv("APP_ENV", "local")}
