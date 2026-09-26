-- DevProof AI — SQLite schema
-- ST-4: Complete schema for sessions, analyses, fix_suggestions, fix_approvals, reports.
-- Uses IF NOT EXISTS so init_db() is safe to call repeatedly.

CREATE TABLE IF NOT EXISTS sessions (
    id              TEXT PRIMARY KEY,
    created_at      DATETIME NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    project_id      TEXT NOT NULL,
    project_name    TEXT NOT NULL,
    bug_description TEXT NOT NULL,
    status          TEXT NOT NULL DEFAULT 'created'
        CHECK (status IN ('created', 'analyzed', 'fix_proposed', 'fix_approved', 'fix_rejected', 'verified'))
);

CREATE TABLE IF NOT EXISTS analyses (
    id              TEXT PRIMARY KEY,
    session_id      TEXT NOT NULL REFERENCES sessions(id),
    relevant_files  TEXT NOT NULL DEFAULT '[]',   -- JSON: FileRelevance[]
    root_causes     TEXT NOT NULL DEFAULT '[]',   -- JSON: RootCause[]
    created_at      DATETIME NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

CREATE TABLE IF NOT EXISTS fix_suggestions (
    id              TEXT PRIMARY KEY,
    session_id      TEXT NOT NULL REFERENCES sessions(id),
    file_path       TEXT NOT NULL,
    original        TEXT NOT NULL,
    suggested       TEXT NOT NULL,
    explanation     TEXT NOT NULL,
    created_at      DATETIME NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

CREATE TABLE IF NOT EXISTS fix_approvals (
    id              TEXT PRIMARY KEY,
    session_id      TEXT NOT NULL REFERENCES sessions(id),
    approved        INTEGER NOT NULL CHECK (approved IN (0, 1)),   -- 1 = approved, 0 = rejected
    feedback        TEXT,                                           -- optional rejection reason
    created_at      DATETIME NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

CREATE TABLE IF NOT EXISTS reports (
    id              TEXT PRIMARY KEY,
    session_id      TEXT NOT NULL REFERENCES sessions(id),
    tests_generated TEXT NOT NULL DEFAULT '[]',   -- JSON: {file, code}[]
    test_output     TEXT NOT NULL DEFAULT '',     -- raw pytest stdout+stderr
    tests_passed    INTEGER NOT NULL DEFAULT 0,
    tests_failed    INTEGER NOT NULL DEFAULT 0,
    verdict         TEXT NOT NULL DEFAULT 'ERROR'
        CHECK (verdict IN ('PASS', 'FAIL', 'PARTIAL', 'ERROR')),
    summary         TEXT NOT NULL DEFAULT '',
    created_at      DATETIME NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);
