"""JSON API: current user, help requests, volunteers.

Other endpoint groups live in small modules that attach routes to api_bp:
api_dashboard.py, api_catalog.py, api_map.py (added in later phases).
"""
import sqlite3

from flask import Blueprint, request
from flask_login import current_user, login_required

from . import models
from .permissions import (ADMINISTRATOR, CITIZEN, VOLUNTEER, admin_required,
                          available_transitions, can_assign, can_view_request,
                          check_transition, roles_required)
from .validation import (ApiError, api_error, api_ok, get_json_object,
                         parse_list_filters, validate_assignment,
                         validate_request_create, validate_status_change)

api_bp = Blueprint("api", __name__, url_prefix="/api")

SUMMARY_FIELDS = ("id", "title", "category", "priority", "status", "address",
                  "latitude", "longitude", "assigned_volunteer_id",
                  "created_at", "updated_at")


@api_bp.errorhandler(ApiError)
def handle_api_error(error):
    return api_error(error.status, error.code, error.message, error.fields)


def _fail_if_invalid(errors):
    if errors:
        raise ApiError(400, "validation_error",
                       "Please check the highlighted fields and try again.", errors)


# ---- Serialisation ---------------------------------------------------------------

def _serialize_history(rows, viewer):
    items = []
    for entry in rows:
        # Names are shown only to administrators and to the person who acted.
        show_name = viewer.role == ADMINISTRATOR or entry["changed_by"] == viewer.id
        items.append({
            "id": entry["id"],
            "old_status": entry["old_status"],
            "new_status": entry["new_status"],
            "note": entry["note"],
            "created_at": entry["created_at"],
            "changed_by_role": entry["changed_by_role"],
            "changed_by_name": entry["changed_by_name"] if show_name else None,
        })
    return items


def serialize_request(row, viewer, detail=False):
    data = {field: row[field] for field in SUMMARY_FIELDS}
    data["assigned_volunteer_name"] = row["assigned_volunteer_name"]
    if viewer.role in (ADMINISTRATOR, VOLUNTEER):
        data["created_by_name"] = row["created_by_name"]
    if detail:
        data["description"] = row["description"]
        data["history"] = _serialize_history(models.get_request_history(row["id"]), viewer)
        data["allowed_transitions"] = available_transitions(viewer, row)
        data["can_assign"] = bool(can_assign(viewer, row))
    return data


def _get_visible_request(request_id):
    """404 both for unknown ids and for requests this user may not see, so
    ids cannot be probed."""
    row = models.get_request(request_id)
    if row is None or not can_view_request(current_user, row):
        raise ApiError(404, "not_found", "Request not found.")
    return row


def _detail_response(request_id, status=200):
    row = models.get_request(request_id)
    return api_ok(serialize_request(row, current_user, detail=True), status)


# ---- Current user -------------------------------------------------------------------

@api_bp.get("/me")
@login_required
def me():
    return api_ok(current_user.to_public_dict())


# ---- Help requests ------------------------------------------------------------------

@api_bp.get("/requests")
@login_required
def list_requests():
    filters, errors = parse_list_filters(request.args)
    _fail_if_invalid(errors)
    rows, total = models.list_requests(current_user, filters)
    return api_ok({
        "items": [serialize_request(row, current_user) for row in rows],
        "total": total,
        "limit": filters["limit"],
        "offset": filters["offset"],
    })


@api_bp.post("/requests")
@roles_required(CITIZEN)
def create_request():
    cleaned, errors = validate_request_create(get_json_object())
    _fail_if_invalid(errors)
    request_id = models.create_request(current_user.id, cleaned)
    return _detail_response(request_id, 201)


@api_bp.get("/requests/<int:request_id>")
@login_required
def get_request(request_id):
    _get_visible_request(request_id)
    return _detail_response(request_id)


@api_bp.patch("/requests/<int:request_id>/status")
@login_required
def update_request_status(request_id):
    row = _get_visible_request(request_id)
    cleaned, errors = validate_status_change(get_json_object())
    _fail_if_invalid(errors)

    old_status = row["status"]
    new_status = cleaned["status"]

    if old_status == "approved" and new_status == "assigned":
        raise ApiError(409, "invalid_transition",
                       "Use the assign endpoint to assign an approved request to a volunteer.")

    outcome = check_transition(current_user, row, new_status)
    if outcome == "invalid":
        raise ApiError(409, "invalid_transition",
                       "A request cannot move from "
                       f"{old_status.replace('_', ' ')} to {new_status.replace('_', ' ')}.")
    if outcome == "forbidden":
        raise ApiError(403, "forbidden", "You are not allowed to make that change.")

    if not models.change_status(request_id, old_status, new_status,
                                current_user.id, cleaned["note"]):
        raise ApiError(409, "conflict",
                       "This request was changed by someone else. Reload the page and try again.")
    return _detail_response(request_id)


@api_bp.post("/requests/<int:request_id>/assign")
@admin_required
def assign_request(request_id):
    row = models.get_request(request_id)
    if row is None:
        raise ApiError(404, "not_found", "Request not found.")
    cleaned, errors = validate_assignment(get_json_object())
    _fail_if_invalid(errors)

    if row["status"] != "approved":
        raise ApiError(409, "invalid_transition", "Only approved requests can be assigned.")

    volunteer = models.get_active_volunteer(cleaned["assigned_volunteer_id"])
    if volunteer is None:
        raise ApiError(400, "validation_error",
                       "Please check the highlighted fields and try again.",
                       {"assigned_volunteer_id": "Choose an active registered volunteer."})

    try:
        assigned = models.assign_request(request_id, volunteer["id"], current_user.id)
    except sqlite3.IntegrityError:
        # The database trigger refused a non-volunteer (defence in depth).
        raise ApiError(400, "validation_error",
                       "Please check the highlighted fields and try again.",
                       {"assigned_volunteer_id": "Choose an active registered volunteer."})
    if not assigned:
        raise ApiError(409, "conflict",
                       "This request was changed by someone else. Reload the page and try again.")
    return _detail_response(request_id)


# ---- Volunteers (administrators only) -----------------------------------------------

@api_bp.get("/volunteers")
@admin_required
def list_volunteers():
    return api_ok({"items": [
        {"id": row["id"], "full_name": row["full_name"], "email": row["email"]}
        for row in models.list_volunteers()
    ]})
