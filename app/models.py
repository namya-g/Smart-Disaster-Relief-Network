"""Database access functions. All SQL lives here and uses parameters only."""
from datetime import datetime, timezone

from flask_login import UserMixin

from .db import get_db, transaction
from .permissions import ROLES
from .validation import MAX_SQLITE_INT, PRIORITIES, STATUSES

OPEN_STATUSES = ("pending", "approved", "assigned", "in_progress")


def utc_now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _valid_id(value):
    return isinstance(value, int) and not isinstance(value, bool) and 0 < value <= MAX_SQLITE_INT


# ---- Users --------------------------------------------------------------------

class User(UserMixin):
    """Wraps a users row for Flask-Login. password_hash is never serialised."""

    def __init__(self, row):
        self.id = row["id"]
        self.full_name = row["full_name"]
        self.email = row["email"]
        self.role = row["role"]
        self.password_hash = row["password_hash"]
        self._active = bool(row["is_active"])

    @property
    def is_active(self):
        # UserMixin.is_authenticated depends on this, so inactive = logged out.
        return self._active

    def to_public_dict(self):
        return {
            "id": self.id,
            "full_name": self.full_name,
            "email": self.email,
            "role": self.role,
        }


def get_user_by_id(user_id):
    row = get_db().execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    return User(row) if row else None


def get_user_by_email(email):
    row = get_db().execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
    return User(row) if row else None


def create_user(full_name, email, password_hash, role):
    """Insert a user and return the new id. Raises sqlite3.IntegrityError on duplicates."""
    with transaction() as conn:
        cursor = conn.execute(
            "INSERT INTO users (full_name, email, password_hash, role) VALUES (?, ?, ?, ?)",
            (full_name, email, password_hash, role),
        )
        return cursor.lastrowid


def list_volunteers():
    """Active volunteers only, for the admin assignment picker."""
    return get_db().execute(
        "SELECT id, full_name, email FROM users "
        "WHERE role = 'volunteer' AND is_active = 1 "
        "ORDER BY full_name COLLATE NOCASE, id"
    ).fetchall()


def get_active_volunteer(user_id):
    if not _valid_id(user_id):
        return None
    return get_db().execute(
        "SELECT id, full_name FROM users "
        "WHERE id = ? AND role = 'volunteer' AND is_active = 1",
        (user_id,),
    ).fetchone()


def count_users_by_role():
    """Active users per role, zero-filled."""
    counts = {role: 0 for role in ROLES}
    rows = get_db().execute(
        "SELECT role, COUNT(*) AS n FROM users WHERE is_active = 1 GROUP BY role"
    ).fetchall()
    for row in rows:
        counts[row["role"]] = row["n"]
    return counts


# ---- Help requests ------------------------------------------------------------

_REQUEST_SELECT = (
    "SELECT r.*, c.full_name AS created_by_name, v.full_name AS assigned_volunteer_name "
    "FROM help_requests r "
    "JOIN users c ON c.id = r.created_by "
    "LEFT JOIN users v ON v.id = r.assigned_volunteer_id"
)

_ORDERS = {
    "newest": "r.created_at DESC, r.id DESC",
    "oldest": "r.created_at ASC, r.id ASC",
    "recently_updated": "r.updated_at DESC, r.id DESC",
}


def _visibility(user):
    """The single rule for which help_requests rows (alias r) a user may see.
    Returns (where_fragments, params)."""
    if user.role == "administrator":
        return [], []
    if user.role == "citizen":
        return ["r.created_by = ?"], [user.id]
    if user.role == "volunteer":
        return ["r.assigned_volunteer_id = ?"], [user.id]
    return ["1 = 0"], []


def _where_sql(fragments):
    return (" WHERE " + " AND ".join(fragments)) if fragments else ""


def get_request(request_id):
    if not _valid_id(request_id):
        return None
    return get_db().execute(_REQUEST_SELECT + " WHERE r.id = ?", (request_id,)).fetchone()


def get_request_history(request_id):
    return get_db().execute(
        "SELECT h.id, h.old_status, h.new_status, h.note, h.created_at, h.changed_by, "
        "u.full_name AS changed_by_name, u.role AS changed_by_role "
        "FROM request_status_history h JOIN users u ON u.id = h.changed_by "
        "WHERE h.request_id = ? ORDER BY h.id ASC",
        (request_id,),
    ).fetchall()


def _escape_like(text):
    return text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def list_requests(user, filters):
    """Return (rows, total) of the requests this user may see, newest first."""
    where, params = _visibility(user)

    if filters.get("status"):
        where.append("r.status = ?")
        params.append(filters["status"])
    if filters.get("category"):
        where.append("r.category = ?")
        params.append(filters["category"])
    if filters.get("search"):
        pattern = "%" + _escape_like(filters["search"]) + "%"
        where.append(
            "(r.title LIKE ? ESCAPE '\\' OR r.description LIKE ? ESCAPE '\\' "
            "OR COALESCE(r.address, '') LIKE ? ESCAPE '\\')"
        )
        params.extend([pattern, pattern, pattern])

    where_sql = _where_sql(where)
    db = get_db()
    total = db.execute(
        "SELECT COUNT(*) AS n FROM help_requests r" + where_sql, params
    ).fetchone()["n"]
    rows = db.execute(
        _REQUEST_SELECT + where_sql + " ORDER BY " + _ORDERS["newest"] + " LIMIT ? OFFSET ?",
        params + [filters.get("limit", 50), filters.get("offset", 0)],
    ).fetchall()
    return rows, total


def fetch_requests(user, statuses=None, order="newest", limit=5):
    """A short list of visible requests, optionally limited to some statuses.
    order is one of: newest, oldest, recently_updated (internal use only)."""
    where, params = _visibility(user)
    if statuses:
        where.append("r.status IN (" + ",".join("?" for _ in statuses) + ")")
        params.extend(statuses)
    return get_db().execute(
        _REQUEST_SELECT + _where_sql(where) + " ORDER BY " + _ORDERS[order] + " LIMIT ?",
        params + [limit],
    ).fetchall()


def count_requests_by_status(user):
    """Visible requests per status, zero-filled for every status."""
    where, params = _visibility(user)
    rows = get_db().execute(
        "SELECT r.status AS status, COUNT(*) AS n FROM help_requests r"
        + _where_sql(where) + " GROUP BY r.status",
        params,
    ).fetchall()
    counts = {status: 0 for status in STATUSES}
    for row in rows:
        counts[row["status"]] = row["n"]
    return counts


def count_open_requests_by_priority():
    """All still-open requests per self-reported priority (administrators only)."""
    rows = get_db().execute(
        "SELECT priority, COUNT(*) AS n FROM help_requests "
        "WHERE status IN (" + ",".join("?" for _ in OPEN_STATUSES) + ") GROUP BY priority",
        OPEN_STATUSES,
    ).fetchall()
    counts = {priority: 0 for priority in PRIORITIES}
    for row in rows:
        counts[row["priority"]] = row["n"]
    return counts


def create_request(user_id, data):
    """Insert a pending request and its first history entry; return the new id."""
    with transaction() as conn:
        cursor = conn.execute(
            "INSERT INTO help_requests (created_by, title, category, description, "
            "priority, address, latitude, longitude) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (user_id, data["title"], data["category"], data["description"],
             data["priority"], data["address"], data["latitude"], data["longitude"]),
        )
        request_id = cursor.lastrowid
        conn.execute(
            "INSERT INTO request_status_history (request_id, changed_by, old_status, new_status) "
            "VALUES (?, ?, NULL, 'pending')",
            (request_id, user_id),
        )
        return request_id


def change_status(request_id, expected_status, new_status, changed_by, note=None):
    """Atomically move a request from expected_status to new_status and log it.

    Returns False (and changes nothing) if the request is no longer in
    expected_status, e.g. because someone else changed it first."""
    with transaction() as conn:
        cursor = conn.execute(
            "UPDATE help_requests SET status = ?, updated_at = ? WHERE id = ? AND status = ?",
            (new_status, utc_now(), request_id, expected_status),
        )
        if cursor.rowcount != 1:
            return False
        conn.execute(
            "INSERT INTO request_status_history "
            "(request_id, changed_by, old_status, new_status, note) VALUES (?, ?, ?, ?, ?)",
            (request_id, changed_by, expected_status, new_status, note),
        )
        return True


def assign_request(request_id, volunteer_id, changed_by, note=None):
    """Atomically assign an approved request to a volunteer. False if it is no
    longer approved."""
    with transaction() as conn:
        cursor = conn.execute(
            "UPDATE help_requests SET status = 'assigned', assigned_volunteer_id = ?, "
            "updated_at = ? WHERE id = ? AND status = 'approved'",
            (volunteer_id, utc_now(), request_id),
        )
        if cursor.rowcount != 1:
            return False
        conn.execute(
            "INSERT INTO request_status_history "
            "(request_id, changed_by, old_status, new_status, note) "
            "VALUES (?, ?, 'approved', 'assigned', ?)",
            (request_id, changed_by, note),
        )
        return True


# ---- Shelter and resource summaries (full CRUD arrives in Phase 7) -----------------

def count_shelters():
    """Totals over all shelter records: total, open (status = 'open'), demo."""
    row = get_db().execute(
        "SELECT COUNT(*) AS total, "
        "COALESCE(SUM(CASE WHEN status = 'open' THEN 1 ELSE 0 END), 0) AS open, "
        "COALESCE(SUM(is_demo), 0) AS demo FROM shelters"
    ).fetchone()
    return {"total": row["total"], "open": row["open"], "demo": row["demo"]}


def count_resources():
    """Totals over all resource records: total, available (status = 'available'), demo."""
    row = get_db().execute(
        "SELECT COUNT(*) AS total, "
        "COALESCE(SUM(CASE WHEN status = 'available' THEN 1 ELSE 0 END), 0) AS available, "
        "COALESCE(SUM(is_demo), 0) AS demo FROM resources"
    ).fetchone()
    return {"total": row["total"], "available": row["available"], "demo": row["demo"]}
