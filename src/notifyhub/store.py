import sqlite3
import threading
import time

class Store:
    def __init__(self, path):
        self.lock = threading.RLock()
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("CREATE TABLE IF NOT EXISTS requests (id TEXT PRIMARY KEY, fingerprint TEXT, method TEXT, status TEXT, detail TEXT, updated REAL)")
        self.db.commit()

    def get(self, request_id):
        with self.lock:
            row = self.db.execute("SELECT id, fingerprint, method, status, detail FROM requests WHERE id=?", (request_id,)).fetchone()
        return dict(zip(("id", "fingerprint", "method", "status", "detail"), row)) if row else None

    def insert(self, message, fingerprint):
        with self.lock, self.db:
            self.db.execute("INSERT INTO requests VALUES (?,?,?,?,?,?)", (message["id"], fingerprint, message["method"], "accepted", "", time.time()))

    def update(self, request_id, status, detail=""):
        with self.lock, self.db:
            self.db.execute("UPDATE requests SET status=?, detail=?, updated=? WHERE id=?", (status, detail[:300], time.time(), request_id))

    def remove(self, request_id):
        with self.lock, self.db:
            self.db.execute("DELETE FROM requests WHERE id=?", (request_id,))

    def recover(self):
        with self.lock, self.db:
            self.db.execute("UPDATE requests SET status='interrupted', detail='Background restarted; delivery may have occurred', updated=? WHERE status IN ('accepted','running')", (time.time(),))

    def prune(self, age):
        with self.lock, self.db:
            self.db.execute("DELETE FROM requests WHERE updated<? AND status NOT IN ('accepted','running')", (time.time()-age,))

    def close(self):
        self.db.close()
