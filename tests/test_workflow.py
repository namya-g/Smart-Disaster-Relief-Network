import sqlite3
from types import SimpleNamespace

import pytest

from app import models
from app.db import get_db
from app.permissions import available_transitions, can_assign, check_transition
from app.validation import STATUSES


def _user(role, user_id):
    return SimpleNamespace(id=user_id, role=role, is_authenticated=True)


def _req(status, created_by=1, assigned=None):
    return {"status": status, "created_by": created_by, "assigned_volunteer_id": assigned}


ADMIN = _user("administrator", 100)
OWNER = _user("citizen", 1)
OTHER_CITIZEN = _user("citizen", 2)
ASSIGNEE = _user("volunteer", 10)
OTHER_VOLUNTEER = _user("volunteer", 11)

ADMIN_MOVES = {
    ("pending", "approved"), ("pending", "rejected"),
    ("pending", "cancelled"), ("approved", "cancelled"),
}


def test_admin_can_make_exactly_the_admin_moves():
    for old in STATUSES:
        for new in STATUSES:
            outcome = check_transition(ADMIN, _req(old), new)
            if (old, new) in ADMIN_MOVES:
                assert outcome == "ok", (old, new)
            else:
                assert outcome in ("invalid", "forbidden"), (old, new)


@pytest.mark.parametrize("terminal", ["rejected", "resolved", "cancelled"])
def test_terminal_states_have_no_moves_for_anyone(terminal):
    request_row = _req(terminal, assigned=10)
    for user in (ADMIN, OWNER, ASSIGNEE):
        assert available_transitions(user, request_row) == []


def test_owner_may_only_cancel_while_pending():
    assert available_transitions(OWNER, _req("pending")) == ["cancelled"]
    assert check_transition(OWNER, _req("approved"), "cancelled") == "forbidden"
    assert check_transition(OWNER, _req("assigned", assigned=10), "cancelled") == "invalid"
    assert check_transition(OWNER, _req("pending"), "approved") == "forbidden"


def test_other_citizen_gets_nothing():
    assert available_transitions(OTHER_CITIZEN, _req("pending")) == []


def test_only_the_assignee_can_progress_assigned_work():
    assigned = _req("assigned", assigned=10)
    assert check_transition(ASSIGNEE, assigned, "in_progress") == "ok"
    assert check_transition(OTHER_VOLUNTEER, assigned, "in_progress") == "forbidden"
    assert check_transition(ADMIN, assigned, "in_progress") == "forbidden"
    assert check_transition(ASSIGNEE, assigned, "resolved") == "invalid"  # cannot skip a step

    in_progress = _req("in_progress", assigned=10)
    assert check_transition(ASSIGNEE, in_progress, "resolved") == "ok"
    assert check_transition(OTHER_VOLUNTEER, in_progress, "resolved") == "forbidden"


def test_assigning_is_not_a_status_transition():
    for user in (ADMIN, OWNER, ASSIGNEE):
        assert check_transition(user, _req("approved"), "assigned") == "invalid"


def test_available_transitions_for_admin():
    assert available_transitions(ADMIN, _req("pending")) == ["approved", "rejected", "cancelled"]
    assert available_transitions(ADMIN, _req("approved")) == ["cancelled"]


def test_can_assign_only_admin_and_only_when_approved():
    assert can_assign(ADMIN, _req("approved"))
    assert not can_assign(ADMIN, _req("pending"))
    assert not can_assign(ADMIN, _req("assigned", assigned=10))
    assert not can_assign(OWNER, _req("approved"))
    assert not can_assign(ASSIGNEE, _req("approved"))


# ---- Database-level safeguards ------------------------------------------------------

def test_change_status_refuses_stale_expected_status(app, make_user, make_request):
    citizen_id = make_user("c@example.com")
    request_id = make_request(citizen_id)
    with app.app_context():
        assert models.change_status(request_id, "approved", "cancelled", citizen_id) is False
        db = get_db()
        status = db.execute("SELECT status FROM help_requests WHERE id = ?",
                            (request_id,)).fetchone()["status"]
        history = db.execute("SELECT COUNT(*) AS n FROM request_status_history "
                             "WHERE request_id = ?", (request_id,)).fetchone()["n"]
    assert status == "pending"
    assert history == 1


def test_database_trigger_blocks_assigning_a_non_volunteer(app, make_user, make_request):
    citizen_id = make_user("c@example.com")
    other_citizen_id = make_user("o@example.com")
    request_id = make_request(citizen_id)
    with app.app_context():
        with pytest.raises(sqlite3.IntegrityError):
            get_db().execute(
                "UPDATE help_requests SET assigned_volunteer_id = ? WHERE id = ?",
                (other_citizen_id, request_id),
            )
