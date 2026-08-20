"""
Lightweight SQLite query logger.
Writes every search + metadata to logs/queries.db.
"""
import os
import sqlite3
import time
import threading

_DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "logs", "queries.db")
_lock    = threading.Lock()


def _conn():
    os.makedirs(os.path.dirname(_DB_PATH), exist_ok=True)
    c = sqlite3.connect(_DB_PATH, check_same_thread=False)
    c.execute("""
        CREATE TABLE IF NOT EXISTS queries (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            ts           REAL,
            query        TEXT,
            query_type   TEXT,
            result_count INTEGER,
            elapsed_ms   INTEGER,
            from_cache   INTEGER DEFAULT 0,
            corrected    TEXT
        )
    """)
    c.commit()
    return c


def log_query(query: str, query_type: str, result_count: int,
              elapsed_ms: int, from_cache: bool = False,
              corrected: str = "") -> None:
    """Non-blocking: runs in background thread so it never slows responses."""
    def _write():
        with _lock:
            try:
                c = _conn()
                c.execute(
                    "INSERT INTO queries (ts,query,query_type,result_count,elapsed_ms,from_cache,corrected) "
                    "VALUES (?,?,?,?,?,?,?)",
                    (time.time(), query, query_type, result_count,
                     elapsed_ms, int(from_cache), corrected)
                )
                c.commit()
                c.close()
            except Exception as e:
                print(f"[query_logger] write error: {e}")

    threading.Thread(target=_write, daemon=True).start()


def get_stats(limit: int = 10) -> dict:
    """Return basic analytics: top queries, total count, cache hit rate."""
    try:
        c = _conn()
        total      = c.execute("SELECT COUNT(*) FROM queries").fetchone()[0]
        cached     = c.execute("SELECT COUNT(*) FROM queries WHERE from_cache=1").fetchone()[0]
        top        = c.execute(
            "SELECT query, COUNT(*) as n FROM queries GROUP BY query ORDER BY n DESC LIMIT ?",
            (limit,)
        ).fetchall()
        c.close()
        return {
            "total_queries": total,
            "cache_hits":    cached,
            "hit_rate_pct":  round(cached / total * 100, 1) if total else 0,
            "top_queries":   [{"query": q, "count": n} for q, n in top],
        }
    except Exception as e:
        return {"error": str(e)}