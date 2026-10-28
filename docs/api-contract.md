# SDRN API Contract

This is the single source of truth for the JSON API. Frontend, backend and
tests must all use exactly these paths and field names.

**Status key:** ✅ implemented and covered by automated tests (tests are
written but must be run locally to confirm) · 🕒 planned, not implemented yet.

## 1. Conventions

| Topic | Rule |
|---|---|
| Base path | `/api/...` on the same origin as the pages. Use relative URLs. |
| Format | JSON in, JSON out. Request bodies must be a JSON **object**. |
| Authentication | Cookie session (Flask-Login). No tokens. |
| CSRF | `POST`, `PATCH` and `DELETE` need the header `X-CSRFToken` (value from `<meta name="csrf-token">`). `static/js/api.js` adds it automatically. |
| Timestamps | UTC text, `YYYY-MM-DDTHH:MM:SSZ`. |
| Success | `{"data": ...}` |
| List success | `{"data": {"items": [...], "total": N, "limit": N, "offset": N}}` |
| Error | `{"error": {"code": "...", "message": "...", "fields": {"field": "message"}}}`. `fields` appears only for validation errors. |
| Unknown fields | Ignored. Clients can never set `status`, `created_by` or `assigned_volunteer_id` when creating a request. |

### Error codes

| HTTP | `code` | Meaning |
|---|---|---|
| 400 | `validation_error` | Missing or invalid input. `fields` explains each problem. |
| 400 | `csrf_failed` | Missing or expired CSRF token. |
| 401 | `unauthenticated` | Not logged in or session expired. |
| 403 | `forbidden` | Logged in, but your role may not do this. |
| 404 | `not_found` | Record does not exist **or you are not allowed to see it** (the two are deliberately indistinguishable). |
| 405 | `method_not_allowed` | Wrong HTTP method for this path. |
| 409 | `invalid_transition` | The status change is not part of the workflow. |
| 409 | `conflict` | Someone else changed the record first. Reload and retry. |
| 500 | `server_error` | Unexpected server problem. No internals are exposed. |

## 2. Shared values

| Name | Allowed values |
|---|---|
| Roles | `citizen`, `volunteer`, `administrator` |
| Request `status` | `pending`, `approved`, `rejected`, `assigned`, `in_progress`, `resolved`, `cancelled` |
| Request `category` | `medical`, `food`, `water`, `shelter`, `rescue`, `other` |
| Request `priority` | `low`, `medium`, `high`, `critical` (self-reported, not verified) |
| Resource `category` | `medical_supplies`, `food`, `water`, `blankets`, `equipment`, `other` |
| Resource `status` | `available`, `low`, `unavailable` |
| Shelter `status` | `open`, `full`, `temporarily_closed` |

### Request workflow

| From | To | Who | How |
|---|---|---|---|
| `pending` | `approved` | administrator | `PATCH .../status` |
| `pending` | `rejected` | administrator | `PATCH .../status` |
| `pending` | `cancelled` | the creating citizen, or an administrator | `PATCH .../status` |
| `approved` | `assigned` | administrator | **`POST .../assign` only** |
| `approved` | `cancelled` | administrator | `PATCH .../status` |
| `assigned` | `in_progress` | the assigned volunteer | `PATCH .../status` |
| `in_progress` | `resolved` | the assigned volunteer | `PATCH .../status` |

`rejected`, `resolved` and `cancelled` are final. Any other move returns
`409 invalid_transition`. A move that exists but is not yours returns
`403 forbidden`. Every successful change is written to the status history.

## 3. Implemented endpoints ✅

### `GET /health`
No login. `{"data": {"status": "ok", "database_initialised": true}}`

### `GET /api/me`
Any logged-in user. Returns `{"data": {"id", "full_name", "email", "role"}}`.

### `GET /api/dashboard`
Any logged-in user. Every number is computed from the database for the
caller's role.

Always present:

```json
{
  "role": "citizen",
  "requests": {
    "total": 3, "open": 2,
    "by_status": {"pending": 1, "approved": 1, "rejected": 0, "assigned": 0,
                  "in_progress": 0, "resolved": 1, "cancelled": 0}
  },
  "shelters":  {"total": 3, "open": 1},
  "resources": {"total": 4, "available": 2},
  "includes_demo_data": true
}
```

- `open` = status in `pending`, `approved`, `assigned`, `in_progress`.
- `shelters.open` and `resources.available` count records whose stored status
  says so. They are not verified real-world availability.
- `includes_demo_data` is true if any fictional demo shelter/resource exists.

Extra fields by role:

| Role | Extra fields |
|---|---|
| citizen | `recent_requests` (own, newest first, max 5) |
| volunteer | `active_tasks` (own assigned, status `assigned` or `in_progress`, max 10) |
| administrator | `pending_requests` and `awaiting_assignment` (oldest first, max 5 each), `open_by_priority` (`low`/`medium`/`high`/`critical`), `users` (active accounts per role) |

`by_status` counts only requests the caller may see. Items in the lists use
the *request summary* shape below.

### Request object

**Summary** (list endpoints):

| Field | Notes |
|---|---|
| `id`, `title`, `category`, `priority`, `status` | |
| `address`, `latitude`, `longitude` | `null` when not supplied |
| `assigned_volunteer_id`, `assigned_volunteer_name` | `null` until assigned |
| `created_at`, `updated_at` | |
| `created_by_name` | **Only for administrators and volunteers.** Never email addresses. |

**Detail** adds:

| Field | Notes |
|---|---|
| `description` | Only in the detail view |
| `history` | Array of `{id, old_status, new_status, note, created_at, changed_by_role, changed_by_name}`. `changed_by_name` is `null` unless the viewer is an administrator or the person who made the change. |
| `allowed_transitions` | Statuses this viewer may set with `PATCH .../status` right now. Use it to decide which buttons to show. |
| `can_assign` | `true` only for an administrator viewing an `approved` request |

### `GET /api/requests`
Any logged-in user. Returns only requests the caller may see: a citizen's own,
a volunteer's assigned, all for an administrator.

| Query | Rule |
|---|---|
| `status` | One status value |
| `category` | One category value |
| `search` | Up to 100 characters, matched against title, description and address (case-insensitive; `%` and `_` are literal) |
| `limit` | 1–100, default 50 |
| `offset` | 0 or more, default 0 |

Invalid values return `400 validation_error` with `fields`. Newest first.

### `POST /api/requests`
Citizens only (volunteers and administrators get `403`).

```json
{
  "title": "Need drinking water",
  "category": "water",
  "description": "Family of four, no clean water since yesterday.",
  "priority": "high",
  "address": "12 Fictional Lane",
  "latitude": 28.61,
  "longitude": 77.2
}
```

| Field | Rule |
|---|---|
| `title` | required, 3–120 characters |
| `category` | required, one of the categories |
| `description` | required, 5–2000 characters |
| `priority` | optional, default `medium` |
| `address` | optional, up to 300 characters |
| `latitude`, `longitude` | optional, but both or neither. −90…90 and −180…180 |

Returns `201` with the **detail** object. Status is always `pending`.

### `GET /api/requests/<id>`
Returns the **detail** object. `404` for unknown IDs and for requests the
caller may not see.

### `PATCH /api/requests/<id>/status`
Body: `{"status": "approved", "note": "optional, up to 500 characters"}`.
Returns the updated **detail** object. Errors: `400` (bad value), `403` (not
your move), `404`, `409 invalid_transition`, `409 conflict`.
Cannot be used to assign (see below).

### `POST /api/requests/<id>/assign`
Administrators only. Body: `{"assigned_volunteer_id": 7}`. The request must be
`approved`, and the user must be an **active registered volunteer**. Returns the
updated **detail** object with status `assigned`. Errors: `400` (not a valid
volunteer), `404`, `409 invalid_transition` (not approved), `409 conflict`.

### `GET /api/volunteers`
Administrators only. `{"data": {"items": [{"id", "full_name", "email"}]}}`,
active volunteers, sorted by name.

## 4. Planned endpoints 🕒 (not implemented yet)

Field names below are agreed. If they change when built, this file is updated
in the same batch.

| Endpoint | Who | Phase |
|---|---|---|
| `GET /api/resources` | any logged-in user | 7 |
| `POST /api/resources` | administrator | 7 |
| `PATCH /api/resources/<id>` | administrator | 7 |
| `DELETE /api/resources/<id>` | administrator | 7 |
| `GET /api/shelters` | any logged-in user | 7 |
| `POST /api/shelters` | administrator | 7 |
| `PATCH /api/shelters/<id>` | administrator | 7 |
| `DELETE /api/shelters/<id>` | administrator | 7 |
| `GET /api/map-data` | any logged-in user, scoped by role | 8 |

- **Resource fields:** `id, name, category, quantity, unit, status, address, latitude, longitude, is_demo, updated_at`.
- **Shelter fields:** `id, name, address, latitude, longitude, capacity, occupancy, status, is_demo, updated_at`.
- **Map-data record fields:** `id, type` (`request`, `shelter` or `resource`), `name, category, status, latitude, longitude, updated_at`. Request markers are limited to what the caller may see and never include requester names, emails or descriptions.
