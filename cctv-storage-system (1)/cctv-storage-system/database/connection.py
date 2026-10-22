"""PostgreSQL access helpers (connection pool + small query API)."""
from contextlib import contextmanager

import pandas as pd
import psycopg2
import psycopg2.extras
from psycopg2.pool import ThreadedConnectionPool

from backend.config.settings import DB

# NUMERIC -> float so engines/pandas never see decimal.Decimal
_DEC2FLOAT = psycopg2.extensions.new_type(
    psycopg2.extensions.DECIMAL.values, "DEC2FLOAT",
    lambda v, cur: float(v) if v is not None else None)
psycopg2.extensions.register_type(_DEC2FLOAT)

_pool = None


def _get_pool():
    global _pool
    if _pool is None:
        _pool = ThreadedConnectionPool(1, 10, **DB)
    return _pool


@contextmanager
def get_conn():
    pool = _get_pool()
    conn = pool.getconn()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        pool.putconn(conn)


@contextmanager
def transaction():
    """Yield a dict cursor; commit on success, roll back on error."""
    with get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            yield cur


def fetch_all(sql, params=None):
    with transaction() as cur:
        cur.execute(sql, params)
        return [dict(r) for r in cur.fetchall()]


def fetch_one(sql, params=None):
    rows = fetch_all(sql, params)
    return rows[0] if rows else None


def fetch_df(sql, params=None):
    return pd.DataFrame(fetch_all(sql, params))


def execute(sql, params=None):
    with transaction() as cur:
        cur.execute(sql, params)
        return cur.rowcount


def execute_values(sql, rows, template=None, page_size=1000):
    """Bulk insert/update helper (sql must contain a single %s placeholder)."""
    if not rows:
        return
    with transaction() as cur:
        psycopg2.extras.execute_values(cur, sql, rows, template=template, page_size=page_size)
