from types import SimpleNamespace

from app.permissions import ADMINISTRATOR, can_view_request, roles_required

REQUEST_ROW = {"created_by": 1, "assigned_volunteer_id": 2}


def _user(user_id, role):
    return SimpleNamespace(id=user_id, role=role, is_authenticated=True)


def test_creator_citizen_can_view():
    assert can_view_request(_user(1, "citizen"), REQUEST_ROW)


def test_other_citizen_cannot_view():
    assert not can_view_request(_user(9, "citizen"), REQUEST_ROW)


def test_assigned_volunteer_can_view():
    assert can_view_request(_user(2, "volunteer"), REQUEST_ROW)


def test_unrelated_volunteer_cannot_view():
    assert not can_view_request(_user(8, "volunteer"), REQUEST_ROW)


def test_unassigned_request_not_visible_to_volunteer():
    row = {"created_by": 1, "assigned_volunteer_id": None}
    assert not can_view_request(_user(2, "volunteer"), row)


def test_administrator_can_view_everything():
    assert can_view_request(_user(99, "administrator"), REQUEST_ROW)


def test_unknown_role_and_anonymous_cannot_view():
    assert not can_view_request(_user(1, "mystery"), REQUEST_ROW)
    anonymous = SimpleNamespace(is_authenticated=False)
    assert not can_view_request(anonymous, REQUEST_ROW)


def test_roles_required_page_and_api(app, client_for):
    @roles_required(ADMINISTRATOR)
    def admin_only():
        return "ok"

    app.add_url_rule("/_admin-only", "admin_only_page", admin_only)
    app.add_url_rule("/api/_admin-only", "admin_only_api", admin_only)

    anonymous = app.test_client()
    assert anonymous.get("/_admin-only").status_code == 302
    api_anon = anonymous.get("/api/_admin-only")
    assert api_anon.status_code == 401
    assert api_anon.get_json()["error"]["code"] == "unauthenticated"

    citizen, _ = client_for("citizen@example.com", role="citizen")
    assert citizen.get("/_admin-only").status_code == 403
    api_forbidden = citizen.get("/api/_admin-only")
    assert api_forbidden.status_code == 403
    assert api_forbidden.get_json()["error"]["code"] == "forbidden"

    admin, _ = client_for("admin@example.com", role="administrator")
    assert admin.get("/_admin-only").status_code == 200
    assert admin.get("/api/_admin-only").status_code == 200
