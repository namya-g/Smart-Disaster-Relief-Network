"""Database access functions. All SQL lives here and uses parameters only."""
from flask_login import UserMixin

from .db import get_db, transaction


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
