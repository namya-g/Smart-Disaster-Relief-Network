"""JSON API (Phase 3: current-user endpoint only)."""
from flask import Blueprint
from flask_login import current_user, login_required

from .validation import api_ok

api_bp = Blueprint("api", __name__, url_prefix="/api")


@api_bp.get("/me")
@login_required
def me():
    return api_ok(current_user.to_public_dict())
