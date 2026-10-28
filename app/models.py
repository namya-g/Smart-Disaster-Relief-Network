"""Database access functions. All SQL lives here and uses parameters only."""
from datetime import datetime, timezone

from flask_login import UserMixin

from .db import get_db, transaction
from .validation import MAX_SQLITE_INT


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


# ---- Help requests ------------------------------------------------------------

_REQUEST_SELECT = (
    "SELECT r.*, c.full_name AS created_by_name, v.full_name AS assigned_volunteer_name "
    "FROM help_requests r "
    "JOIN users c ON c.id = r.created_by "
    "LEFT JOIN users v ON v.id = r.assigned_volunteer_id"
)


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
    where, params = [], []
    if user.role == "citizen":
        where.append("r.created_by = ?")
        params.append(user.id)
    elif user.role == "volunteer":
        where.append("r.assigned_volunteer_id = ?")
        params.append(user.id)
    elif user.role != "administrator":
        where.append("1 = 0")

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

    where_sql = (" WHERE " + " AND ".join(where)) if where else ""
    db = get_db()
    total = db.execute(
        "SELECT COUNT(*) AS n FROM help_requests r" + where_sql, params
    ).fetchone()["n"]
    rows = db.execute(
        _REQUEST_SELECT + where_sql + " ORDER BY r.created_at DESC, r.id DESC LIMIT ? OFFSET ?",
        params + [filters.get("limit", 50), filters.get("offset", 0)],
    ).fetchall()
    return rows, total


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
