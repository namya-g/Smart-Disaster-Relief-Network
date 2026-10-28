import json

from app.db import get_db

ALL_STATUSES = {"pending", "approved", "rejected", "assigned",
                "in_progress", "resolved", "cancelled"}


def _dash(client):
    response = client.get("/api/dashboard")
    assert response.status_code == 200
    return response.get_json()["data"]


def _set_created_at(app, request_id, value):
    with app.app_context():
        db = get_db()
        db.execute("UPDATE help_requests SET created_at = ? WHERE id = ?", (value, request_id))
        db.commit()


def _seed_demo(app):
    result = app.test_cli_runner().invoke(args=["seed-demo"])
    assert result.exit_code == 0, result.output


# ---- Access ---------------------------------------------------------------------------

def test_dashboard_requires_login(client):
    response = client.get("/api/dashboard")
    assert response.status_code == 401
    assert response.get_json()["error"]["code"] == "unauthenticated"


# ---- Citizen --------------------------------------------------------------------------

def test_citizen_dashboard_empty_state_is_zero_filled(client_for):
    citizen, _ = client_for("c@example.com")
    data = _dash(citizen)
    assert data["role"] == "citizen"
    assert set(data["requests"]["by_status"]) == ALL_STATUSES
    assert all(count == 0 for count in data["requests"]["by_status"].values())
    assert data["requests"]["total"] == 0 and data["requests"]["open"] == 0
    assert data["recent_requests"] == []
    assert data["shelters"] == {"total": 0, "open": 0}
    assert data["resources"] == {"total": 0, "available": 0}
    assert data["includes_demo_data"] is False
    for admin_only in ("pending_requests", "awaiting_assignment", "users", "open_by_priority"):
        assert admin_only not in data


def test_citizen_counts_only_own_requests(client_for, make_request):
    citizen_a, a_id = client_for("a@example.com")
    _, b_id = client_for("b@example.com")
    make_request(a_id, status="pending")
    make_request(a_id, status="approved")
    make_request(a_id, status="resolved")
    make_request(b_id, status="pending", title="Someone else's request")
    data = _dash(citizen_a)
    assert data["requests"]["total"] == 3
    assert data["requests"]["open"] == 2  # resolved is not open
    assert data["requests"]["by_status"]["pending"] == 1
    assert data["requests"]["by_status"]["resolved"] == 1
    assert len(data["recent_requests"]) == 3
    assert "Someone else's request" not in json.dumps(data)


def test_citizen_recent_requests_limited_to_five_newest_first(client_for, make_request):
    citizen, c_id = client_for("c@example.com")
    ids = [make_request(c_id, title=f"Request number {n}") for n in range(7)]
    recent = _dash(citizen)["recent_requests"]
    assert [item["id"] for item in recent] == list(reversed(ids))[:5]
    assert all("description" not in item and "created_by_name" not in item for item in recent)


# ---- Volunteer ------------------------------------------------------------------------

def test_volunteer_dashboard_only_covers_assigned_work(client_for, make_request):
    _, c_id = client_for("c@example.com")
    volunteer, v_id = client_for("v@example.com", role="volunteer")
    _, other_v_id = client_for("w@example.com", role="volunteer")
    assigned = make_request(c_id, status="assigned", assigned_volunteer_id=v_id)
    working = make_request(c_id, status="in_progress", assigned_volunteer_id=v_id)
    make_request(c_id, status="resolved", assigned_volunteer_id=v_id)
    make_request(c_id, status="assigned", assigned_volunteer_id=other_v_id)
    make_request(c_id, status="approved")  # unassigned: invisible to volunteers
    data = _dash(volunteer)
    assert data["role"] == "volunteer"
    assert data["requests"]["total"] == 3
    assert data["requests"]["by_status"]["assigned"] == 1
    assert data["requests"]["by_status"]["in_progress"] == 1
    assert data["requests"]["by_status"]["resolved"] == 1
    assert sorted(item["id"] for item in data["active_tasks"]) == sorted([assigned, working])
    assert "recent_requests" not in data and "users" not in data


# ---- Administrator ----------------------------------------------------------------------

def test_admin_dashboard_counts_everything(client_for, make_request, make_user):
    admin, _ = client_for("admin@example.com", role="administrator")
    _, a_id = client_for("a@example.com")
    _, b_id = client_for("b@example.com")
    v_id = make_user("v@example.com", role="volunteer")
    make_user("gone@example.com", role="volunteer", is_active=0)
    make_request(a_id, status="pending", priority="critical")
    make_request(b_id, status="pending", priority="low")
    make_request(a_id, status="approved", priority="high")
    make_request(b_id, status="assigned", priority="high", assigned_volunteer_id=v_id)
    make_request(a_id, status="resolved", priority="critical")  # closed: not in open_by_priority
    data = _dash(admin)
    assert data["role"] == "administrator"
    assert data["requests"]["total"] == 5
    assert data["requests"]["open"] == 4
    assert data["requests"]["by_status"]["pending"] == 2
    assert data["open_by_priority"] == {"low": 1, "medium": 0, "high": 2, "critical": 1}
    assert data["users"] == {"citizen": 2, "volunteer": 1, "administrator": 1}  # inactive excluded
    assert len(data["pending_requests"]) == 2
    assert len(data["awaiting_assignment"]) == 1
    assert all("created_by_name" in item for item in data["pending_requests"])


def test_admin_queues_are_oldest_first(app, client_for, make_request):
    admin, _ = client_for("admin@example.com", role="administrator")
    _, c_id = client_for("c@example.com")
    newer = make_request(c_id, title="Newer request")
    older = make_request(c_id, title="Older request")
    _set_created_at(app, newer, "2026-02-01T00:00:00Z")
    _set_created_at(app, older, "2026-01-01T00:00:00Z")
    queue = _dash(admin)["pending_requests"]
    assert [item["id"] for item in queue] == [older, newer]


def test_numbers_update_after_a_status_change(client_for, make_request):
    admin, _ = client_for("admin@example.com", role="administrator")
    _, c_id = client_for("c@example.com")
    request_id = make_request(c_id)
    before = _dash(admin)
    assert before["requests"]["by_status"]["pending"] == 1
    assert admin.patch(f"/api/requests/{request_id}/status",
                       json={"status": "approved"}).status_code == 200
    after = _dash(admin)
    assert after["requests"]["by_status"]["pending"] == 0
    assert after["requests"]["by_status"]["approved"] == 1
    assert [item["id"] for item in after["awaiting_assignment"]] == [request_id]
    assert after["pending_requests"] == []


# ---- Shelters, resources and demo labelling ------------------------------------------------

def test_shelter_and_resource_counts_with_demo_data(app, client_for):
    _seed_demo(app)
    citizen, _ = client_for("c@example.com")
    data = _dash(citizen)
    assert data["shelters"] == {"total": 3, "open": 1}
    assert data["resources"] == {"total": 4, "available": 2}
    assert data["includes_demo_data"] is True


def test_demo_flag_is_false_for_real_records_only(app, client_for):
    with app.app_context():
        db = get_db()
        db.execute("INSERT INTO shelters (name, capacity, occupancy, status, is_demo) "
                   "VALUES ('Real hall', 50, 10, 'open', 0)")
        db.commit()
    citizen, _ = client_for("c@example.com")
    data = _dash(citizen)
    assert data["shelters"] == {"total": 1, "open": 1}
    assert data["includes_demo_data"] is False


# ---- Privacy -----------------------------------------------------------------------------------

def test_dashboard_never_exposes_emails_or_password_data(client_for, make_request, make_user):
    admin, _ = client_for("admin@example.com", role="administrator")
    citizen, c_id = client_for("c@example.com")
    volunteer, v_id = client_for("v@example.com", role="volunteer")
    make_request(c_id, status="assigned", assigned_volunteer_id=v_id)
    make_request(c_id)
    for client in (admin, citizen, volunteer):
        text = json.dumps(_dash(client)).lower()
        assert "@" not in text
        assert "password" not in text
        assert "hash" not in text
