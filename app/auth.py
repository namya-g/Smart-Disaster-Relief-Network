"""Authentication: register, login, logout."""
import sqlite3
from urllib.parse import urlparse

from flask import Blueprint, flash, redirect, render_template, request, session, url_for
from flask_login import current_user, login_user, logout_user
from werkzeug.security import check_password_hash, generate_password_hash

from . import models
from .extensions import login_manager
from .validation import api_error, validate_login, validate_registration

auth_bp = Blueprint("auth", __name__)

# Checked when the email is unknown, so response time doesn't reveal which
# emails are registered.
_DUMMY_HASH = generate_password_hash("not-a-real-password")


@login_manager.user_loader
def load_user(user_id):
    try:
        return models.get_user_by_id(int(user_id))
    except (TypeError, ValueError):
        return None


@login_manager.unauthorized_handler
def unauthorized():
    if request.path.startswith("/api/"):
        return api_error(401, "unauthenticated", "Please log in to continue.")
    flash("Please log in to continue.", "info")
    target = request.path
    if request.query_string:
        target += "?" + request.query_string.decode("utf-8", "replace")
    return redirect(url_for("auth.login", next=target))


def _safe_next(target):
    """Return target only if it is a local path (prevents open redirects)."""
    if not target or not target.startswith("/") or target.startswith("//") or "\\" in target:
        return None
    if any(ord(char) < 32 for char in target):
        return None
    parsed = urlparse(target)
    if parsed.scheme or parsed.netloc:
        return None
    return target


@auth_bp.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("pages.dashboard"))
    if request.method == "GET":
        return render_template("register.html", errors={}, form={})

    cleaned, errors = validate_registration(request.form)
    form_values = {
        "full_name": cleaned["full_name"],
        "email": cleaned["email"],
        "role": cleaned["role"],
    }
    if errors:
        return render_template("register.html", errors=errors, form=form_values), 400

    duplicate = {"email": "An account with this email already exists."}
    if models.get_user_by_email(cleaned["email"]):
        return render_template("register.html", errors=duplicate, form=form_values), 409
    try:
        models.create_user(
            cleaned["full_name"],
            cleaned["email"],
            generate_password_hash(cleaned["password"]),
            cleaned["role"],
        )
    except sqlite3.IntegrityError:
        # Another request registered the same email at the same moment.
        return render_template("register.html", errors=duplicate, form=form_values), 409

    flash("Account created. Please log in.", "success")
    return redirect(url_for("auth.login"))


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("pages.dashboard"))
    next_url = _safe_next(request.values.get("next"))
    if request.method == "GET":
        expired = request.args.get("expired") == "1"
        return render_template("login.html", errors={}, form={}, next=next_url, expired=expired)

    cleaned, errors = validate_login(request.form)
    form_values = {"email": cleaned["email"]}
    if errors:
        return render_template("login.html", errors=errors, form=form_values,
                               next=next_url, expired=False), 400

    user = models.get_user_by_email(cleaned["email"])
    password_ok = check_password_hash(user.password_hash if user else _DUMMY_HASH,
                                      cleaned["password"])
    if not user or not password_ok or not user.is_active:
        # Same message for every failure: don't reveal which part was wrong.
        generic = {"form": "Invalid email or password."}
        return render_template("login.html", errors=generic, form=form_values,
                               next=next_url, expired=False), 401

    session.clear()
    login_user(user)
    session.permanent = True
    return redirect(next_url or url_for("pages.dashboard"))


@auth_bp.post("/logout")
def logout():
    logout_user()
    flash("You have been logged out.", "success")
    return redirect(url_for("auth.login"))
