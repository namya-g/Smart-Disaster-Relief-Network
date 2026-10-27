"""Input validation and shared JSON response helpers."""
import re

from flask import jsonify

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

# Roles a person may choose when registering publicly. 'administrator' is
# deliberately absent: admins are created only with `flask create-admin`.
PUBLIC_REGISTRATION_ROLES = ("citizen", "volunteer")


# ---- JSON envelope helpers -------------------------------------------------

def api_ok(data, status=200):
    return jsonify({"data": data}), status


def api_error(status, code, message, fields=None):
    body = {"error": {"code": code, "message": message}}
    if fields:
        body["error"]["fields"] = fields
    return jsonify(body), status


# ---- Field helpers ---------------------------------------------------------

def normalize_email(value):
    return (value or "").strip().lower()


def _clean_name(value):
    return " ".join((value or "").split())


# ---- Form validators -------------------------------------------------------
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
