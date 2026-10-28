"""HTML page routes and shared template context."""
from flask import Blueprint, current_app, render_template, request, url_for
from flask_login import current_user, login_required

from .permissions import ADMINISTRATOR, CITIZEN, VOLUNTEER

pages_bp = Blueprint("pages", __name__)

ALL_ROLES = (CITIZEN, VOLUNTEER, ADMINISTRATOR)

# Sidebar navigation. An item shows only if the user's role matches AND its
# endpoint is registered, so links appear automatically as phases add pages.
# "also" lists other endpoints that should highlight this item.
NAV_ITEMS = [
    {"label": "Dashboard", "endpoint": "pages.dashboard", "icon": "home",
     "roles": ALL_ROLES, "also": ()},
    {"label": "My requests", "endpoint": "pages.requests", "icon": "list",
     "roles": (CITIZEN,), "also": ("pages.request_detail",)},
    {"label": "All requests", "endpoint": "pages.requests", "icon": "list",
     "roles": (ADMINISTRATOR,), "also": ("pages.request_detail",)},
    {"label": "New request", "endpoint": "pages.request_new", "icon": "plus",
     "roles": (CITIZEN,), "also": ()},
    {"label": "My tasks", "endpoint": "pages.volunteer", "icon": "clipboard",
     "roles": (VOLUNTEER,), "also": ("pages.request_detail",)},
    {"label": "Map", "endpoint": "pages.map_view", "icon": "map",
     "roles": ALL_ROLES, "also": ()},
    {"label": "Shelters", "endpoint": "pages.shelters", "icon": "tent",
     "roles": ALL_ROLES, "also": ()},
    {"label": "Resources", "endpoint": "pages.resources", "icon": "box",
     "roles": ALL_ROLES, "also": ()},
    {"label": "Administration", "endpoint": "pages.admin", "icon": "shield",
     "roles": (ADMINISTRATOR,), "also": ()},
]


@pages_bp.app_context_processor
def inject_navigation():
    if not current_user.is_authenticated:
        return {"nav_items": []}
    items = []
    for item in NAV_ITEMS:
        if current_user.role not in item["roles"]:
            continue
        if item["endpoint"] not in current_app.view_functions:
            continue
        active_endpoints = (item["endpoint"],) + tuple(item["also"])
        items.append({
            "label": item["label"],
            "href": url_for(item["endpoint"]),
            "icon": item["icon"],
            "active": request.endpoint in active_endpoints,
        })
    return {"nav_items": items}


@pages_bp.get("/")
def index():
    return render_template("index.html")


@pages_bp.get("/dashboard")
@login_required
def dashboard():
    return render_template("dashboard.html")
