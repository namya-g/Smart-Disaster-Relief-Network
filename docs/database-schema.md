# SDRN Database Schema

SQLite, accessed with Python's `sqlite3`. The schema is in `app/schema.sql`
and the live database is `instance/sdrn.sqlite` (never committed to Git).
All SQL is parameterised and lives in `app/models.py` (and the CLI commands in
`app/cli.py`). Foreign keys are switched on for every connection in
`app/db.py` (`PRAGMA foreign_keys = ON`).

## Relationships

```text
users ──< help_requests (created_by)
users ──< help_requests (assigned_volunteer_id, volunteers only)
help_requests ──< request_status_history (request_id)
users ──< request_status_history (changed_by)
users ──< resources (updated_by, optional)
shelters: standalone
```

## Tables

### `users`
| Column | Type | Rules |
|---|---|---|
| `id` | INTEGER | primary key |
| `full_name` | TEXT | 2–100 characters |
| `email` | TEXT | unique, case-insensitive, must already be lowercase |
| `password_hash` | TEXT | Werkzeug hash. Plain passwords are never stored. |
| `role` | TEXT | `citizen`, `volunteer`, `administrator` |
| `is_active` | INTEGER | 0 or 1, default 1. Inactive users cannot log in. |
| `created_at` | TEXT | UTC timestamp, default now |

### `help_requests`
| Column | Type | Rules |
|---|---|---|
| `id` | INTEGER | primary key |
| `created_by` | INTEGER | → `users.id`, required |
| `title` | TEXT | 3–120 characters |
| `category` | TEXT | `medical`, `food`, `water`, `shelter`, `rescue`, `other` |
| `description` | TEXT | 5–2000 characters |
| `priority` | TEXT | `low`, `medium`, `high`, `critical`; default `medium` |
| `status` | TEXT | `pending`, `approved`, `rejected`, `assigned`, `in_progress`, `resolved`, `cancelled`; default `pending` |
| `address` | TEXT | optional, up to 300 characters |
| `latitude`, `longitude` | REAL | optional; −90…90 and −180…180; **both set or both null** |
| `assigned_volunteer_id` | INTEGER | → `users.id`, optional |
| `created_at`, `updated_at` | TEXT | UTC timestamps |

A **trigger** (`trg_requests_volunteer_insert`, `trg_requests_volunteer_update`)
aborts any insert or update that sets `assigned_volunteer_id` to a user whose
role is not `volunteer`. The API checks this too; the trigger is a second layer.

### `request_status_history`
| Column | Type | Rules |
|---|---|---|
| `id` | INTEGER | primary key |
| `request_id` | INTEGER | → `help_requests.id`, deleted with the request |
| `changed_by` | INTEGER | → `users.id` |
| `old_status` | TEXT | null for the first entry (creation) |
| `new_status` | TEXT | a valid status |
| `note` | TEXT | optional, up to 500 characters |
| `created_at` | TEXT | UTC timestamp |

One row is written for creation and one for every valid status change or
assignment, in the same transaction as the change itself.

### `resources`
| Column | Type | Rules |
|---|---|---|
| `id` | INTEGER | primary key |
| `name` | TEXT | 2–120 characters |
| `category` | TEXT | `medical_supplies`, `food`, `water`, `blankets`, `equipment`, `other` |
| `quantity` | INTEGER | 0 or more |
| `unit` | TEXT | 1–30 characters, default `units` |
| `status` | TEXT | `available`, `low`, `unavailable`; default `available` |
| `address` | TEXT | optional |
| `latitude`, `longitude` | REAL | optional, same rules and pairing as above |
| `updated_by` | INTEGER | → `users.id`, optional |
| `is_demo` | INTEGER | 1 for fictional demonstration records |
| `created_at`, `updated_at` | TEXT | UTC timestamps |

### `shelters`
| Column | Type | Rules |
|---|---|---|
| `id` | INTEGER | primary key |
| `name` | TEXT | 2–120 characters |
| `address` | TEXT | optional |
| `latitude`, `longitude` | REAL | optional, same rules and pairing as above |
| `capacity` | INTEGER | 0 or more |
| `occupancy` | INTEGER | 0 or more and **not above `capacity`** |
| `status` | TEXT | `open`, `full`, `temporarily_closed`; default `open` |
| `is_demo` | INTEGER | 1 for fictional demonstration records |
| `created_at`, `updated_at` | TEXT | UTC timestamps |

## Indexes

`help_requests`: `created_by`, `assigned_volunteer_id`, `status`, `category` ·
`request_status_history`: `request_id` · `resources`: `(category, status)` ·
`shelters`: `status`. (`users.email` is indexed by its unique constraint.)

## Demonstration data

`flask --app run seed-demo` inserts 4 resources and 3 shelters, all named
`[DEMO] ...`, with `is_demo = 1` and made-up addresses and coordinates. They are
**fictional**: no availability, quantity or location is real or verified.
Running the command again adds nothing. No demo users are created.

## Setup commands (Windows PowerShell, venv active)

```powershell
flask --app run init-db            # create tables (safe to repeat)
flask --app run seed-demo          # optional fictional data
flask --app run create-admin       # prompts for name, email, password
flask --app run db-status          # tables and row counts
flask --app run init-db --reset    # DROPS ALL DATA, then recreates tables
```

`CREATE TABLE IF NOT EXISTS` means an existing database is **not** migrated when
`schema.sql` changes. During development, run `init-db --reset` and recreate
your accounts. Automated tests always use a fresh temporary database.
