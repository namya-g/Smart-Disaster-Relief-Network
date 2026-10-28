"""Input validation, the ApiError exception, and shared JSON response helpers."""
import math
import re

from flask import jsonify, request

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

# Roles a person may choose when registering publicly. 'administrator' is
# deliberately absent: admins are created only with `flask create-admin`.
PUBLIC_REGISTRATION_ROLES = ("citizen", "volunteer")

CATEGORIES = ("medical", "food", "water", "shelter", "rescue", "other")
PRIORITIES = ("low", "medium", "high", "critical")
STATUSES = ("pending", "approved", "rejected", "assigned",
            "in_progress", "resolved", "cancelled")

MAX_SQLITE_INT = 2**63 - 1


# ---- Errors and JSON envelope helpers --------------------------------------

class ApiError(Exception):
    """Raise inside API views; api.py turns it into the standard JSON error."""

    def __init__(self, status, code, message, fields=None):
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message
        self.fields = fields


def api_ok(data, status=200):
    return jsonify({"data": data}), status


def api_error(status, code, message, fields=None):
    body = {"error": {"code": code, "message": message}}
    if fields:
        body["error"]["fields"] = fields
    return jsonify(body), status


def get_json_object():
    """Return the JSON body, which must be an object (dict)."""
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        raise ApiError(400, "validation_error", "The request body must be a JSON object.")
    return payload


# ---- Field helpers ---------------------------------------------------------

def normalize_email(value):
    return (value or "").strip().lower()


def _clean_name(value):
    return " ".join((value or "").split())


def _required_text(payload, field, label, min_len, max_len, errors, collapse=False):
    value = payload.get(field)
    if not isinstance(value, str):
        errors[field] = f"{label} is required."
        return ""
    value = " ".join(value.split()) if collapse else value.strip()
    if not min_len <= len(value) <= max_len:
        errors[field] = f"{label} must be {min_len}-{max_len} characters."
    return value


def _optional_text(payload, field, label, max_len, errors):
    value = payload.get(field)
    if value is None:
        return None
    if not isinstance(value, str):
        errors[field] = f"{label} must be text."
        return None
    value = value.strip()
    if not value:
        return None
    if len(value) > max_len:
        errors[field] = f"{label} must be {max_len} characters or fewer."
    return value


def _parse_coordinate(value, field, label, low, high, errors):
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        errors[field] = f"{label} must be a number."
        return None
    try:
        number = float(value)
    except ValueError:
        errors[field] = f"{label} must be a number."
        return None
    if not math.isfinite(number):
        errors[field] = f"{label} must be a number."
        return None
    if not low <= number <= high:
        errors[field] = f"{label} must be between {low} and {high}."
        return None
    return number


def parse_coordinates(payload, errors):
    """Return (latitude, longitude). Both present or both missing."""
    lat = _parse_coordinate(payload.get("latitude"), "latitude", "Latitude", -90, 90, errors)
    lng = _parse_coordinate(payload.get("longitude"), "longitude", "Longitude", -180, 180, errors)
    if "latitude" not in errors and "longitude" not in errors and (lat is None) != (lng is None):
        missing = "longitude" if lng is None else "latitude"
        errors[missing] = "Provide both latitude and longitude, or leave both empty."
    return lat, lng


def _parse_int(raw, default, low, high, field, errors):
    if raw is None or raw == "":
        return default
    try:
        number = int(raw)
    except (TypeError, ValueError):
        errors[field] = f"{field} must be a whole number."
        return default
    if not low <= number <= high:
        errors[field] = f"{field} must be between {low} and {high}."
        return default
    return number


# ---- Form validators (registration, login) ---------------------------------
# Each returns (cleaned_values, errors). errors is empty when input is valid.

def validate_registration(form):
    errors = {}
    full_name = _clean_name(form.get("full_name"))
    email = normalize_email(form.get("email"))
    password = form.get("password") or ""
    confirm = form.get("confirm_password") or ""
    role = (form.get("role") or "").strip()

    if not 2 <= len(full_name) <= 100:
        errors["full_name"] = "Full name must be 2-100 characters."

    if not EMAIL_RE.match(email) or len(email) > 254:
        errors["email"] = "Enter a valid email address."

    if not 8 <= len(password) <= 128:
        errors["password"] = "Password must be 8-128 characters."
    elif not (re.search(r"[A-Za-z]", password) and re.search(r"\d", password)):
        errors["password"] = "Password must include at least one letter and one number."

    if "password" not in errors and password != confirm:
        errors["confirm_password"] = "Passwords do not match."

    if role not in PUBLIC_REGISTRATION_ROLES:
        errors["role"] = "Choose either citizen or volunteer."

    cleaned = {"full_name": full_name, "email": email, "password": password, "role": role}
    return cleaned, errors


def validate_login(form):
    errors = {}
    email = normalize_email(form.get("email"))
    password = form.get("password") or ""

    if not email:
        errors["email"] = "Enter your email address."
    if not password:
        errors["password"] = "Enter your password."
    if len(password) > 128 or len(email) > 254:
        errors["form"] = "Invalid email or password."

    return {"email": email, "password": password}, errors


# ---- API validators (JSON payloads) ----------------------------------------

def validate_request_create(payload):
    """Only these fields are read. Anything else the client sends (status,
    created_by, assigned_volunteer_id, ...) is ignored."""
    errors = {}
    title = _required_text(payload, "title", "Title", 3, 120, errors, collapse=True)
    description = _required_text(payload, "description", "Description", 5, 2000, errors)

    category = payload.get("category")
    if category not in CATEGORIES:
        errors["category"] = "Choose a valid category."

    priority = payload.get("priority")
    if priority is None or priority == "":
        priority = "medium"
    elif priority not in PRIORITIES:
        errors["priority"] = "Choose a valid priority."

    address = _optional_text(payload, "address", "Address", 300, errors)
    latitude, longitude = parse_coordinates(payload, errors)

    cleaned = {
        "title": title,
        "category": category,
        "description": description,
        "priority": priority,
        "address": address,
        "latitude": latitude,
        "longitude": longitude,
    }
    return cleaned, errors


def validate_status_change(payload):
    errors = {}
    status = payload.get("status")
    if status not in STATUSES:
        errors["status"] = "Choose a valid status."
    note = _optional_text(payload, "note", "Note", 500, errors)
    return {"status": status, "note": note}, errors


def validate_assignment(payload):
    errors = {}
    value = payload.get("assigned_volunteer_id")
    if isinstance(value, str) and value.strip().isdigit():
        value = int(value.strip())
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= MAX_SQLITE_INT:
        errors["assigned_volunteer_id"] = "Choose a volunteer."
        value = None
    return {"assigned_volunteer_id": value}, errors


def parse_list_filters(args):
    """Validate query parameters for GET /api/requests."""
    errors = {}
    status = (args.get("status") or "").strip()
    if status and status not in STATUSES:
        errors["status"] = "Unknown status."
    category = (args.get("category") or "").strip()
    if category and category not in CATEGORIES:
        errors["category"] = "Unknown category."
    search = " ".join((args.get("search") or "").split())
    if len(search) > 100:
        errors["search"] = "Search text must be 100 characters or fewer."
    limit = _parse_int(args.get("limit"), 50, 1, 100, "limit", errors)
    offset = _parse_int(args.get("offset"), 0, 0, 1_000_000, "offset", errors)
    filters = {"status": status, "category": category, "search": search,
               "limit": limit, "offset": offset}
    return filters, errors
