-- Phase 1 minimal schema
CREATE TABLE IF NOT EXISTS logs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  request_id TEXT NOT NULL,
  endpoint TEXT NOT NULL,
  payload TEXT,
  response TEXT,
  status TEXT,
  latency_ms INTEGER,
  created_at TEXT NOT NULL
);

