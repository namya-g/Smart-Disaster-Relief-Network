"""Role constants, permission checks, and the request workflow rules."""
from functools import wraps

from flask import abort
from flask_login import current_user

from .extensions import login_manager

CITIZEN = "citizen"
VOLUNTEER = "volunteer"
ADMINISTRATOR = "administrator"
ROLES = (CITIZEN, VOLUNTEER, ADMINISTRATOR)

# ---- Workflow ----------------------------------------------------------------
# (old_status, new_status) -> who may make the change.
#   "admin"    any administrator
#   "creator"  the citizen who created the request
#   "assignee" the volunteer the request is assigned to
# approved -> assigned is NOT here: it happens only through the assign endpoint.
TRANSITIONS = {
    ("pending", "approved"): ("admin",),
    ("pending", "rejected"): ("admin",),
    ("pending", "cancelled"): ("admin", "creator"),
    ("approved", "cancelled"): ("admin",),
    ("assigned", "in_progress"): ("assignee",),
    ("in_progress", "resolved"): ("assignee",),
}


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


def actor_relations(user, request_row):
    """How this user relates to this request: a subset of
    {"admin", "creator", "assignee"}."""
    relations = set()
    if not getattr(user, "is_authenticated", False):
        return relations
    if user.role == ADMINISTRATOR:
        relations.add("admin")
    if user.role == CITIZEN and request_row["created_by"] == user.id:
        relations.add("creator")
    assigned = request_row["assigned_volunteer_id"]
    if user.role == VOLUNTEER and assigned is not None and assigned == user.id:
        relations.add("assignee")
    return relations


def check_transition(user, request_row, new_status):
    """Return "ok", "invalid" (not in the workflow), or "forbidden"
    (in the workflow, but this user may not do it)."""
    allowed = TRANSITIONS.get((request_row["status"], new_status))
    if allowed is None:
        return "invalid"
    if actor_relations(user, request_row) & set(allowed):
        return "ok"
    return "forbidden"


def available_transitions(user, request_row):
    """Statuses this user may move the request to via the status endpoint."""
    return [new for (old, new) in TRANSITIONS
            if old == request_row["status"]
            and check_transition(user, request_row, new) == "ok"]


def can_assign(user, request_row):
    return (getattr(user, "is_authenticated", False)
            and user.role == ADMINISTRATOR
            and request_row["status"] == "approved")
