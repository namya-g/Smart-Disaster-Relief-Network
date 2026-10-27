"""Role constants and server-side permission checks."""
from functools import wraps

from flask import abort
from flask_login import current_user

from .extensions import login_manager

CITIZEN = "citizen"
VOLUNTEER = "volunteer"
ADMINISTRATOR = "administrator"
ROLES = (CITIZEN, VOLUNTEER, ADMINISTRATOR)


def roles_required(*allowed_roles):
    """Allow only logged-in users whose role is in allowed_roles.

    Anonymous users get the login redirect (pages) or a 401 JSON error (/api).
    Logged-in users with the wrong role get 403.
    """

    def decorator(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            if not current_user.is_authenticated:
                return login_manager.unauthorized()
            if current_user.role not in allowed_roles:
                abort(403)
            return view(*args, **kwargs)

        return wrapped

    return decorator


admin_required = roles_required(ADMINISTRATOR)


def can_view_request(user, request_row):
    """Citizens see their own requests, volunteers see requests assigned to
    them, administrators see everything. request_row needs created_by and
    assigned_volunteer_id (a dict or sqlite3.Row both work)."""
    if not getattr(user, "is_authenticated", False):
        return False
    if user.role == ADMINISTRATOR:
        return True
    if user.role == CITIZEN:
        return request_row["created_by"] == user.id
    if user.role == VOLUNTEER:
        return request_row["assigned_volunteer_id"] == user.id
    return False
