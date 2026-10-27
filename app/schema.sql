-- SDRN database schema (SQLite). Safe to run repeatedly (IF NOT EXISTS).
-- Foreign keys are enforced per connection in db.py (PRAGMA foreign_keys = ON).

CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    full_name     TEXT NOT NULL CHECK (length(full_name) BETWEEN 2 AND 100),
    email         TEXT NOT NULL UNIQUE COLLATE NOCASE CHECK (email = lower(email)),
    password_hash TEXT NOT NULL,
    role          TEXT NOT NULL CHECK (role IN ('citizen', 'volunteer', 'administrator')),
    is_active     INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1)),
    created_at    TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

CREATE TABLE IF NOT EXISTS help_requests (
    id                    INTEGER PRIMARY KEY AUTOINCREMENT,
    created_by            INTEGER NOT NULL REFERENCES users(id),
    title                 TEXT NOT NULL CHECK (length(title) BETWEEN 3 AND 120),
    category              TEXT NOT NULL CHECK (category IN
                              ('medical', 'food', 'water', 'shelter', 'rescue', 'other')),
    description           TEXT NOT NULL CHECK (length(description) BETWEEN 5 AND 2000),
    priority              TEXT NOT NULL DEFAULT 'medium' CHECK (priority IN
                              ('low', 'medium', 'high', 'critical')),
    status                TEXT NOT NULL DEFAULT 'pending' CHECK (status IN
                              ('pending', 'approved', 'rejected', 'assigned',
                               'in_progress', 'resolved', 'cancelled')),
    address               TEXT CHECK (address IS NULL OR length(address) <= 300),
    latitude              REAL CHECK (latitude IS NULL OR (latitude BETWEEN -90 AND 90)),
    longitude             REAL CHECK (longitude IS NULL OR (longitude BETWEEN -180 AND 180)),
    assigned_volunteer_id INTEGER REFERENCES users(id),
    created_at            TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    updated_at            TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    CHECK ((latitude IS NULL) = (longitude IS NULL))
);

CREATE TABLE IF NOT EXISTS request_status_history (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    request_id INTEGER NOT NULL REFERENCES help_requests(id) ON DELETE CASCADE,
    changed_by INTEGER NOT NULL REFERENCES users(id),
    old_status TEXT CHECK (old_status IS NULL OR old_status IN
                   ('pending', 'approved', 'rejected', 'assigned',
                    'in_progress', 'resolved', 'cancelled')),
    new_status TEXT NOT NULL CHECK (new_status IN
                   ('pending', 'approved', 'rejected', 'assigned',
                    'in_progress', 'resolved', 'cancelled')),
    note       TEXT CHECK (note IS NULL OR length(note) <= 500),
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

CREATE TABLE IF NOT EXISTS resources (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    name       TEXT NOT NULL CHECK (length(name) BETWEEN 2 AND 120),
    category   TEXT NOT NULL CHECK (category IN
                   ('medical_supplies', 'food', 'water', 'blankets', 'equipment', 'other')),
    quantity   INTEGER NOT NULL DEFAULT 0 CHECK (quantity >= 0),
    unit       TEXT NOT NULL DEFAULT 'units' CHECK (length(unit) BETWEEN 1 AND 30),
    status     TEXT NOT NULL DEFAULT 'available' CHECK (status IN
                   ('available', 'low', 'unavailable')),
    address    TEXT CHECK (address IS NULL OR length(address) <= 300),
    latitude   REAL CHECK (latitude IS NULL OR (latitude BETWEEN -90 AND 90)),
    longitude  REAL CHECK (longitude IS NULL OR (longitude BETWEEN -180 AND 180)),
    updated_by INTEGER REFERENCES users(id),
    is_demo    INTEGER NOT NULL DEFAULT 0 CHECK (is_demo IN (0, 1)),
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    CHECK ((latitude IS NULL) = (longitude IS NULL))
);

CREATE TABLE IF NOT EXISTS shelters (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    name       TEXT NOT NULL CHECK (length(name) BETWEEN 2 AND 120),
    address    TEXT CHECK (address IS NULL OR length(address) <= 300),
    latitude   REAL CHECK (latitude IS NULL OR (latitude BETWEEN -90 AND 90)),
    longitude  REAL CHECK (longitude IS NULL OR (longitude BETWEEN -180 AND 180)),
    capacity   INTEGER NOT NULL CHECK (capacity >= 0),
    occupancy  INTEGER NOT NULL DEFAULT 0 CHECK (occupancy >= 0),
    status     TEXT NOT NULL DEFAULT 'open' CHECK (status IN
                   ('open', 'full', 'temporarily_closed')),
    is_demo    INTEGER NOT NULL DEFAULT 0 CHECK (is_demo IN (0, 1)),
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    CHECK (occupancy <= capacity),
    CHECK ((latitude IS NULL) = (longitude IS NULL))
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_requests_created_by ON help_requests(created_by);
CREATE INDEX IF NOT EXISTS idx_requests_assigned   ON help_requests(assigned_volunteer_id);
CREATE INDEX IF NOT EXISTS idx_requests_status     ON help_requests(status);
CREATE INDEX IF NOT EXISTS idx_requests_category   ON help_requests(category);
CREATE INDEX IF NOT EXISTS idx_history_request     ON request_status_history(request_id);
CREATE INDEX IF NOT EXISTS idx_resources_cat_stat  ON resources(category, status);
CREATE INDEX IF NOT EXISTS idx_shelters_status     ON shelters(status);

-- Only users whose role is 'volunteer' may be assigned to a request.
CREATE TRIGGER IF NOT EXISTS trg_requests_volunteer_insert
BEFORE INSERT ON help_requests
WHEN NEW.assigned_volunteer_id IS NOT NULL
 AND (SELECT role FROM users WHERE id = NEW.assigned_volunteer_id) IS NOT 'volunteer'
BEGIN
    SELECT RAISE(ABORT, 'assigned_volunteer_id must reference a volunteer');
END;

CREATE TRIGGER IF NOT EXISTS trg_requests_volunteer_update
BEFORE UPDATE OF assigned_volunteer_id ON help_requests
WHEN NEW.assigned_volunteer_id IS NOT NULL
 AND (SELECT role FROM users WHERE id = NEW.assigned_volunteer_id) IS NOT 'volunteer'
BEGIN
    SELECT RAISE(ABORT, 'assigned_volunteer_id must reference a volunteer');
END;
