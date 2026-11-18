-- PC Insight local database schema (SQLite).
-- The applied version is tracked with PRAGMA user_version.

CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS snapshots (
    id               INTEGER PRIMARY KEY,
    ts               INTEGER NOT NULL,
    cpu_percent      REAL    NOT NULL,
    memory_percent   REAL    NOT NULL,
    memory_used      INTEGER NOT NULL,
    disk_read        INTEGER NOT NULL DEFAULT 0,
    disk_write       INTEGER NOT NULL DEFAULT 0,
    net_recv         INTEGER NOT NULL DEFAULT 0,
    net_sent         INTEGER NOT NULL DEFAULT 0,
    top_process      TEXT,
    top_proc_percent REAL    NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_snapshots_ts ON snapshots(ts);

CREATE TABLE IF NOT EXISTS storage_scans (
    id                INTEGER PRIMARY KEY,
    ts                INTEGER NOT NULL,
    duration_ms       INTEGER NOT NULL,
    total_bytes       INTEGER NOT NULL,
    reclaimable_bytes INTEGER NOT NULL,
    errors_count      INTEGER NOT NULL DEFAULT 0,
    mode              TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS storage_items (
    id         INTEGER PRIMARY KEY,
    scan_id    INTEGER NOT NULL REFERENCES storage_scans(id) ON DELETE CASCADE,
    path       TEXT    NOT NULL,
    size_bytes INTEGER NOT NULL,
    category   TEXT    NOT NULL,
    safety     TEXT    NOT NULL,
    confidence REAL    NOT NULL,
    reason     TEXT    NOT NULL DEFAULT ''
);

CREATE INDEX IF NOT EXISTS idx_storage_items_scan ON storage_items(scan_id);

CREATE TABLE IF NOT EXISTS diagnostic_runs (
    id          INTEGER PRIMARY KEY,
    ts          INTEGER NOT NULL,
    duration_ms INTEGER NOT NULL,
    critical    INTEGER NOT NULL DEFAULT 0,
    warning     INTEGER NOT NULL DEFAULT 0,
    info        INTEGER NOT NULL DEFAULT 0,
    mode        TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS findings (
    id             INTEGER PRIMARY KEY,
    run_id         INTEGER NOT NULL REFERENCES diagnostic_runs(id) ON DELETE CASCADE,
    rule_id        TEXT    NOT NULL,
    severity       TEXT    NOT NULL,
    title          TEXT    NOT NULL,
    detail         TEXT    NOT NULL DEFAULT '',
    recommendation TEXT    NOT NULL DEFAULT '',
    evidence       TEXT    NOT NULL DEFAULT ''
);

CREATE INDEX IF NOT EXISTS idx_findings_run ON findings(run_id);