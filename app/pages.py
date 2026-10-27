"""HTML page routes (temporary minimal version for Phase 3)."""
from flask import Blueprint, redirect, render_template, url_for
from flask_login import current_user, login_required

pages_bp = Blueprint("pages", __name__)


@pages_bp.get("/")
def index():
    if current_user.is_authenticated:
        return redirect(url_for("pages.dashboard"))
    return redirect(url_for("auth.login"))


@pages_bp.get("/dashboard")
@login_required
def dashboard():
    return render_template("dashboard.html")
