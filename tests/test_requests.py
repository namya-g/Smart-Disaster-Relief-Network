import pytest

from app.db import get_db

BASE = {
    "title": "Need drinking water",
    "category": "water",
    "description": "Family of four, no clean water since yesterday.",
    "priority": "high",
}


def _row(app, request_id):
    with app.app_context():
        return get_db().execute("SELECT * FROM help_requests WHERE id = ?",
                                (request_id,)).fetchone()


def _history(app, request_id):
    with app.app_context():
        rows = get_db().execute(
            "SELECT old_status, new_status FROM request_status_history "
            "WHERE request_id = ? ORDER BY id", (request_id,)).fetchall()
    return [(r["old_status"], r["new_status"]) for r in rows]


def _count_requests(app):
    with app.app_context():
        return get_db().execute("SELECT COUNT(*) AS n FROM help_requests").fetchone()["n"]


def _ids(response):
    return sorted(item["id"] for item in response.get_json()["data"]["items"])


# ---- Creation ---------------------------------------------------------------------------

def test_citizen_creates_request(app, client_for):
    citizen, user_id = client_for("c@example.com")
    response = citizen.post("/api/requests", json={
        **BASE, "address": "12 Fictional Lane", "latitude": 28.61, "longitude": 77.2})
    assert response.status_code == 201
    data = response.get_json()["data"]
    assert data["status"] == "pending"
    assert data["title"] == BASE["title"]
    assert data["latitude"] == 28.61
    assert [h["new_status"] for h in data["history"]] == ["pending"]
    assert "created_by_name" not in data  # citizens never see requester names
    assert _history(app, data["id"]) == [(None, "pending")]
    assert _row(app, data["id"])["created_by"] == user_id


def test_creation_works_without_priority_or_location(app, client_for):
    citizen, _ = client_for("c@example.com")
    payload = {k: v for k, v in BASE.items() if k != "priority"}
    response = citizen.post("/api/requests", json=payload)
    assert response.status_code == 201
    data = response.get_json()["data"]
    assert data["priority"] == "medium"
    assert data["latitude"] is None and data["longitude"] is None


def test_client_cannot_set_status_owner_or_assignee(app, client_for, make_user):
    volunteer_id = make_user("v@example.com", role="volunteer")
    citizen, user_id = client_for("c@example.com")
    response = citizen.post("/api/requests", json={
        **BASE, "status": "resolved", "assigned_volunteer_id": volunteer_id,
        "created_by": 999})
    assert response.status_code == 201
    row = _row(app, response.get_json()["data"]["id"])
    assert row["status"] == "pending"
    assert row["assigned_volunteer_id"] is None
    assert row["created_by"] == user_id


@pytest.mark.parametrize("override", [
    {"title": ""}, {"title": "ab"}, {"title": 123}, {"category": "pizza"},
    {"priority": "urgent"}, {"description": "x" * 2001}, {"description": "hi"},
    {"latitude": 28.6}, {"longitude": 77.2},
    {"latitude": 91, "longitude": 10}, {"latitude": 10, "longitude": 181},
    {"latitude": "abc", "longitude": 10}, {"latitude": True, "longitude": 10},
])
def test_invalid_request_is_rejected(app, client_for, override):
    citizen, _ = client_for("c@example.com")
    response = citizen.post("/api/requests", json={**BASE, **override})
    assert response.status_code == 400
    error = response.get_json()["error"]
    assert error["code"] == "validation_error"
    assert error["fields"]
    assert _count_requests(app) == 0


@pytest.mark.parametrize("missing", ["title", "category", "description"])
def test_missing_required_field_is_rejected(app, client_for, missing):
    citizen, _ = client_for("c@example.com")
    payload = {k: v for k, v in BASE.items() if k != missing}
    response = citizen.post("/api/requests", json=payload)
    assert response.status_code == 400
    assert missing in response.get_json()["error"]["fields"]


def test_non_object_and_non_json_bodies_are_rejected(client_for):
    citizen, _ = client_for("c@example.com")
    assert citizen.post("/api/requests", json=["x"]).status_code == 400
    assert citizen.post("/api/requests", data="not json").status_code == 400


def test_only_citizens_can_create_and_anonymous_gets_401(client, client_for):
    volunteer, _ = client_for("v@example.com", role="volunteer")
    admin, _ = client_for("a@example.com", role="administrator")
    assert volunteer.post("/api/requests", json=BASE).status_code == 403
    assert admin.post("/api/requests", json=BASE).status_code == 403
    assert client.post("/api/requests", json=BASE).status_code == 401


# ---- Listing, visibility, filters ------------------------------------------------------------

def _scenario(client_for, make_request):
    admin, _ = client_for("admin@example.com", role="administrator")
    citizen_a, a_id = client_for("a@example.com")
    citizen_b, b_id = client_for("b@example.com")
    volunteer, v_id = client_for("v@example.com", role="volunteer")
    other_volunteer, _ = client_for("w@example.com", role="volunteer")
    r1 = make_request(a_id, title="Water for family", category="water")
    r2 = make_request(a_id, title="Medicine needed", category="medical",
                      status="assigned", assigned_volunteer_id=v_id)
    r3 = make_request(b_id, title="Food parcels", category="food", status="approved")
    return {"admin": admin, "a": citizen_a, "b": citizen_b, "v": volunteer,
            "w": other_volunteer, "r1": r1, "r2": r2, "r3": r3}


def test_each_role_sees_only_permitted_requests(client_for, make_request):
    s = _scenario(client_for, make_request)
    assert _ids(s["a"].get("/api/requests")) == sorted([s["r1"], s["r2"]])
    assert _ids(s["b"].get("/api/requests")) == [s["r3"]]
    assert _ids(s["v"].get("/api/requests")) == [s["r2"]]
    assert _ids(s["w"].get("/api/requests")) == []
    assert _ids(s["admin"].get("/api/requests")) == sorted([s["r1"], s["r2"], s["r3"]])


def test_list_items_hide_private_fields(client_for, make_request):
    s = _scenario(client_for, make_request)
    citizen_items = s["a"].get("/api/requests").get_json()["data"]["items"]
    for item in citizen_items:
        assert "description" not in item
        assert "created_by_name" not in item
        assert "email" not in str(item).lower()
    admin_items = s["admin"].get("/api/requests").get_json()["data"]["items"]
    assert all("created_by_name" in item for item in admin_items)
    assert "password" not in str(admin_items).lower()


def test_filters_and_search(client_for, make_request):
    s = _scenario(client_for, make_request)
    admin = s["admin"]
    assert _ids(admin.get("/api/requests?status=approved")) == [s["r3"]]
    assert _ids(admin.get("/api/requests?category=medical")) == [s["r2"]]
    assert _ids(admin.get("/api/requests?search=WATER")) == [s["r1"]]
    assert _ids(admin.get("/api/requests?status=pending&category=food")) == []
    assert _ids(admin.get("/api/requests?search=%25")) == []  # a literal % matches nothing


def test_invalid_filters_are_rejected(client_for):
    admin, _ = client_for("admin@example.com", role="administrator")
    for query in ("status=bogus", "category=bogus", "limit=0", "limit=abc",
                  "offset=-1", "search=" + "x" * 101):
        response = admin.get("/api/requests?" + query)
        assert response.status_code == 400, query
        assert response.get_json()["error"]["code"] == "validation_error"


def test_pagination(client_for, make_request):
    admin, _ = client_for("admin@example.com", role="administrator")
    _, c_id = client_for("c@example.com")
    for index in range(5):
        make_request(c_id, title=f"Request number {index}")
    page = admin.get("/api/requests?limit=2").get_json()["data"]
    assert len(page["items"]) == 2 and page["total"] == 5 and page["limit"] == 2
    last = admin.get("/api/requests?limit=2&offset=4").get_json()["data"]
    assert len(last["items"]) == 1 and last["offset"] == 4


def test_list_requires_login(client):
    assert client.get("/api/requests").status_code == 401


# ---- Detail -------------------------------------------------------------------------------------

def test_detail_visibility(client_for, make_request):
    s = _scenario(client_for, make_request)
    assert s["a"].get(f"/api/requests/{s['r2']}").status_code == 200
    assert s["v"].get(f"/api/requests/{s['r2']}").status_code == 200
    assert s["admin"].get(f"/api/requests/{s['r2']}").status_code == 200
    for other in (s["b"], s["w"]):
        response = other.get(f"/api/requests/{s['r2']}")
        assert response.status_code == 404
        assert response.get_json()["error"]["code"] == "not_found"
    assert s["v"].get(f"/api/requests/{s['r1']}").status_code == 404  # not assigned to them


def test_unknown_and_huge_ids_return_404(client_for):
    admin, _ = client_for("admin@example.com", role="administrator")
    assert admin.get("/api/requests/9999").status_code == 404
    assert admin.get("/api/requests/99999999999999999999").status_code == 404
    assert admin.get("/api/requests/abc").status_code == 404


def test_detail_contains_description_history_and_actions(client_for, make_request):
    s = _scenario(client_for, make_request)
    citizen_view = s["a"].get(f"/api/requests/{s['r1']}").get_json()["data"]
    assert citizen_view["description"]
    assert citizen_view["allowed_transitions"] == ["cancelled"]
    assert citizen_view["can_assign"] is False
    admin_view = s["admin"].get(f"/api/requests/{s['r3']}").get_json()["data"]
    assert admin_view["allowed_transitions"] == ["cancelled"]
    assert admin_view["can_assign"] is True
    volunteer_view = s["v"].get(f"/api/requests/{s['r2']}").get_json()["data"]
    assert volunteer_view["allowed_transitions"] == ["in_progress"]
    assert volunteer_view["created_by_name"]


def test_detail_requires_login(client):
    assert client.get("/api/requests/1").status_code == 401


# ---- Status changes --------------------------------------------------------------------------------

def _patch(client, request_id, status, note=None):
    body = {"status": status}
    if note is not None:
        body["note"] = note
    return client.patch(f"/api/requests/{request_id}/status", json=body)


def test_admin_approves_and_history_is_recorded(app, client_for, make_request):
    admin, _ = client_for("admin@example.com", role="administrator")
    _, c_id = client_for("c@example.com")
    request_id = make_request(c_id)
    response = _patch(admin, request_id, "approved", note="Verified by phone")
    assert response.status_code == 200
    data = response.get_json()["data"]
    assert data["status"] == "approved"
    assert data["history"][-1]["note"] == "Verified by phone"
    assert data["history"][-1]["changed_by_role"] == "administrator"
    assert _history(app, request_id) == [(None, "pending"), ("pending", "approved")]


def test_admin_can_reject_and_rejected_is_final(client_for, make_request):
    admin, _ = client_for("admin@example.com", role="administrator")
    _, c_id = client_for("c@example.com")
    request_id = make_request(c_id)
    assert _patch(admin, request_id, "rejected").status_code == 200
    again = _patch(admin, request_id, "approved")
    assert again.status_code == 409
    assert again.get_json()["error"]["code"] == "invalid_transition"


def test_invalid_transitions_are_rejected(client_for, make_request):
    admin, _ = client_for("admin@example.com", role="administrator")
    _, c_id = client_for("c@example.com")
    request_id = make_request(c_id)
    for target in ("resolved", "in_progress", "pending"):
        response = _patch(admin, request_id, target)
        assert response.status_code == 409, target
        assert response.get_json()["error"]["code"] == "invalid_transition"


def test_unknown_status_value_is_rejected(client_for, make_request):
    admin, _ = client_for("admin@example.com", role="administrator")
    _, c_id = client_for("c@example.com")
    request_id = make_request(c_id)
    response = _patch(admin, request_id, "banana")
    assert response.status_code == 400
    assert "status" in response.get_json()["error"]["fields"]


def test_status_endpoint_cannot_assign(client_for, make_request):
    admin, _ = client_for("admin@example.com", role="administrator")
    _, c_id = client_for("c@example.com")
    request_id = make_request(c_id, status="approved")
    response = _patch(admin, request_id, "assigned")
    assert response.status_code == 409
    assert "assign endpoint" in response.get_json()["error"]["message"]


def test_citizen_cannot_approve_own_request(app, client_for, make_request):
    citizen, c_id = client_for("c@example.com")
    request_id = make_request(c_id)
    assert _patch(citizen, request_id, "approved").status_code == 403
    assert _row(app, request_id)["status"] == "pending"


def test_citizen_can_cancel_own_pending_request(app, client_for, make_request):
    citizen, c_id = client_for("c@example.com")
    request_id = make_request(c_id)
    response = _patch(citizen, request_id, "cancelled")
    assert response.status_code == 200
    assert _history(app, request_id)[-1] == ("pending", "cancelled")


def test_citizen_cancellation_restrictions(client_for, make_request, make_user):
    citizen, c_id = client_for("c@example.com")
    volunteer_id = make_user("v@example.com", role="volunteer")
    approved = make_request(c_id, status="approved")
    assigned = make_request(c_id, status="assigned", assigned_volunteer_id=volunteer_id)
    assert _patch(citizen, approved, "cancelled").status_code == 403
    assert _patch(citizen, assigned, "cancelled").status_code == 409


def test_other_citizen_cannot_touch_request(app, client_for, make_request):
    _, a_id = client_for("a@example.com")
    citizen_b, _ = client_for("b@example.com")
    request_id = make_request(a_id)
    assert _patch(citizen_b, request_id, "cancelled").status_code == 404
    assert _row(app, request_id)["status"] == "pending"


def test_unrelated_volunteer_gets_404_and_assignee_cannot_approve(client_for, make_request):
    _, c_id = client_for("c@example.com")
    assignee, v_id = client_for("v@example.com", role="volunteer")
    stranger, _ = client_for("w@example.com", role="volunteer")
    pending = make_request(c_id)
    assigned = make_request(c_id, status="assigned", assigned_volunteer_id=v_id)
    assert _patch(stranger, pending, "approved").status_code == 404
    assert _patch(stranger, assigned, "in_progress").status_code == 404
    assert _patch(assignee, assigned, "approved").status_code == 409


def test_volunteer_completes_assigned_work_in_order(app, client_for, make_request):
    _, c_id = client_for("c@example.com")
    volunteer, v_id = client_for("v@example.com", role="volunteer")
    request_id = make_request(c_id, status="assigned", assigned_volunteer_id=v_id)
    skip = _patch(volunteer, request_id, "resolved")
    assert skip.status_code == 409  # cannot skip in_progress
    assert _patch(volunteer, request_id, "in_progress").status_code == 200
    assert _patch(volunteer, request_id, "resolved").status_code == 200
    assert _history(app, request_id) == [
        (None, "pending"), ("assigned", "in_progress"), ("in_progress", "resolved")]
    assert _patch(volunteer, request_id, "in_progress").status_code == 409  # resolved is final


def test_admin_can_cancel_approved_request(client_for, make_request):
    admin, _ = client_for("admin@example.com", role="administrator")
    _, c_id = client_for("c@example.com")
    request_id = make_request(c_id, status="approved")
    assert _patch(admin, request_id, "cancelled").status_code == 200


def test_history_names_are_hidden_from_citizens(client_for, make_request):
    admin, _ = client_for("admin@example.com", role="administrator", full_name="Alice Admin")
    citizen, c_id = client_for("c@example.com", full_name="Carl Citizen")
    request_id = make_request(c_id)
    _patch(admin, request_id, "approved")
    history = citizen.get(f"/api/requests/{request_id}").get_json()["data"]["history"]
    assert history[0]["changed_by_name"] == "Carl Citizen"  # their own action
    assert history[1]["changed_by_name"] is None  # the administrator's name is hidden
    assert history[1]["changed_by_role"] == "administrator"
    admin_history = admin.get(f"/api/requests/{request_id}").get_json()["data"]["history"]
    assert admin_history[1]["changed_by_name"] == "Alice Admin"


def test_status_change_requires_login(client):
    assert client.patch("/api/requests/1/status", json={"status": "approved"}).status_code == 401


# ---- Assignment ----------------------------------------------------------------------------------------

def _assign(client, request_id, volunteer_id):
    return client.post(f"/api/requests/{request_id}/assign",
                       json={"assigned_volunteer_id": volunteer_id})


def test_admin_assigns_approved_request_to_volunteer(app, client_for, make_request):
    admin, _ = client_for("admin@example.com", role="administrator")
    _, c_id = client_for("c@example.com")
    volunteer, v_id = client_for("v@example.com", role="volunteer", full_name="Vera Volunteer")
    request_id = make_request(c_id, status="approved")
    response = _assign(admin, request_id, v_id)
    assert response.status_code == 200
    data = response.get_json()["data"]
    assert data["status"] == "assigned"
    assert data["assigned_volunteer_id"] == v_id
    assert data["assigned_volunteer_name"] == "Vera Volunteer"
    assert _history(app, request_id)[-1] == ("approved", "assigned")
    assert volunteer.get(f"/api/requests/{request_id}").status_code == 200  # now visible


def test_assignment_requires_approved_status(client_for, make_request):
    admin, _ = client_for("admin@example.com", role="administrator")
    _, c_id = client_for("c@example.com")
    _, v_id = client_for("v@example.com", role="volunteer")
    pending = make_request(c_id)
    response = _assign(admin, pending, v_id)
    assert response.status_code == 409
    assert response.get_json()["error"]["code"] == "invalid_transition"


def test_cannot_assign_the_same_request_twice(client_for, make_request):
    admin, _ = client_for("admin@example.com", role="administrator")
    _, c_id = client_for("c@example.com")
    _, v_id = client_for("v@example.com", role="volunteer")
    request_id = make_request(c_id, status="approved")
    assert _assign(admin, request_id, v_id).status_code == 200
    assert _assign(admin, request_id, v_id).status_code == 409


def test_assignment_rejects_non_volunteers_and_unknown_users(app, client_for, make_request, make_user):
    admin, admin_id = client_for("admin@example.com", role="administrator")
    _, c_id = client_for("c@example.com")
    inactive_id = make_user("old@example.com", role="volunteer", is_active=0)
    request_id = make_request(c_id, status="approved")
    for bad in (c_id, admin_id, 9999, inactive_id):
        response = _assign(admin, request_id, bad)
        assert response.status_code == 400, bad
        assert "assigned_volunteer_id" in response.get_json()["error"]["fields"]
    assert _row(app, request_id)["status"] == "approved"


@pytest.mark.parametrize("body", [{}, {"assigned_volunteer_id": None},
                                  {"assigned_volunteer_id": True},
                                  {"assigned_volunteer_id": "abc"},
                                  {"assigned_volunteer_id": -3}])
def test_assignment_requires_a_valid_volunteer_id(client_for, make_request, body):
    admin, _ = client_for("admin@example.com", role="administrator")
    _, c_id = client_for("c@example.com")
    request_id = make_request(c_id, status="approved")
    response = admin.post(f"/api/requests/{request_id}/assign", json=body)
    assert response.status_code == 400


def test_assignment_of_unknown_request_is_404(client_for):
    admin, _ = client_for("admin@example.com", role="administrator")
    _, v_id = client_for("v@example.com", role="volunteer")
    assert _assign(admin, 9999, v_id).status_code == 404


def test_volunteers_and_citizens_cannot_assign(app, client_for, make_request):
    _, c_id = client_for("c@example.com")
    citizen, _ = client_for("c2@example.com")
    volunteer, v_id = client_for("v@example.com", role="volunteer")
    request_id = make_request(c_id, status="approved")
    assert _assign(volunteer, request_id, v_id).status_code == 403  # no self-assignment
    assert _assign(citizen, request_id, v_id).status_code == 403
    assert _row(app, request_id)["assigned_volunteer_id"] is None


def test_assign_requires_login(client):
    assert client.post("/api/requests/1/assign",
                       json={"assigned_volunteer_id": 1}).status_code == 401


# ---- Volunteer list --------------------------------------------------------------------------------------

def test_admin_lists_active_volunteers_only(client_for, make_user):
    admin, _ = client_for("admin@example.com", role="administrator")
    active_id = make_user("v1@example.com", role="volunteer", full_name="Active One")
    make_user("v2@example.com", role="volunteer", full_name="Gone", is_active=0)
    make_user("c@example.com", role="citizen", full_name="Not A Volunteer")
    response = admin.get("/api/volunteers")
    assert response.status_code == 200
    items = response.get_json()["data"]["items"]
    assert [item["id"] for item in items] == [active_id]
    assert set(items[0]) == {"id", "full_name", "email"}
    assert "password" not in str(items).lower()


def test_volunteer_list_is_admin_only(client, client_for):
    citizen, _ = client_for("c@example.com")
    volunteer, _ = client_for("v@example.com", role="volunteer")
    assert citizen.get("/api/volunteers").status_code == 403
    assert volunteer.get("/api/volunteers").status_code == 403
    assert client.get("/api/volunteers").status_code == 401
