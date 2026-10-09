import os
import logging
import psycopg
from psycopg_pool import ConnectionPool

try:
    from secrets import DB_URL
except ImportError:
    DB_URL = os.getenv("DB_URL")

def print_db():
    print(DB_URL)

def get_db_url() -> str:
    if not DB_URL:
        raise ValueError("Database URL is not configured. Set DB_URL environment variable.")
    return DB_URL

def connect() -> psycopg.Connection:
    try:
        return psycopg.connect(conninfo=get_db_url())
    except Exception:
        print("Could not connect to the database!")

def connect_pool(
    min: int = 4,
    max: int = 25,
    timeout: float = 10.0,) -> ConnectionPool:
    url = get_db_url()
    try:
        pool = ConnectionPool(
            min_size=min,
            max_size=max,
            conninfo=url,
        )
        return pool
    except (Exception, psycopg.DatabaseError) as error:
        print("PostgreSQL pool connection error: ", error)
        logging.critical("Failed to initialize PostgreSQL ConnectionPool: %s", error)
        raise

if __name__ == "__main__":
    # print_db()
    connect()
