"""GET /api/dashboard: role-scoped summary built from live database queries."""
from flask_login import current_user, login_required

from . import models
from .api import api_bp, serialize_request
from .permissions import ADMINISTRATOR, CITIZEN, VOLUNTEER
from .validation import api_ok


def _items(rows):
    return [serialize_request(row, current_user) for row in rows]


@api_bp.get("/dashboard")
@login_required
def dashboard():
    user = current_user
    by_status = models.count_requests_by_status(user)
    shelters = models.count_shelters()
    resources = models.count_resources()

    data = {
        "role": user.role,
        "requests": {
            "total": sum(by_status.values()),
            "open": sum(by_status[status] for status in models.OPEN_STATUSES),
            "by_status": by_status,
        },
        # "open" / "available" count records whose status field says so.
        # They are stored values, not verified real-world availability.
        "shelters": {"total": shelters["total"], "open": shelters["open"]},
        "resources": {"total": resources["total"], "available": resources["available"]},
        "includes_demo_data": bool(shelters["demo"] or resources["demo"]),
    }

    if user.role == CITIZEN:
        data["recent_requests"] = _items(models.fetch_requests(user, order="newest", limit=5))
    elif user.role == VOLUNTEER:
        data["active_tasks"] = _items(models.fetch_requests(
            user, statuses=("assigned", "in_progress"), order="recently_updated", limit=10))
    elif user.role == ADMINISTRATOR:
        data["pending_requests"] = _items(models.fetch_requests(
            user, statuses=("pending",), order="oldest", limit=5))
        data["awaiting_assignment"] = _items(models.fetch_requests(
            user, statuses=("approved",), order="oldest", limit=5))
        data["open_by_priority"] = models.count_open_requests_by_priority()
        data["users"] = models.count_users_by_role()

    return api_ok(data)
