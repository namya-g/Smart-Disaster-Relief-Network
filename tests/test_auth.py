import re

import pytest
from werkzeug.security import check_password_hash

from app.db import get_db

GOOD = {
    "full_name": "Asha Verma",
    "email": "asha@example.com",
    "password": "Password123",
    "confirm_password": "Password123",
    "role": "citizen",
}


def _fetch_user(app, email):
    with app.app_context():
        return get_db().execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()


def _count_users(app):
    with app.app_context():
        return get_db().execute("SELECT COUNT(*) AS n FROM users").fetchone()["n"]


# ---- Registration -----------------------------------------------------------

def test_register_success_creates_citizen(app, client):
    response = client.post("/register", data=GOOD)
    assert response.status_code == 302
    assert "/login" in response.headers["Location"]
    user = _fetch_user(app, "asha@example.com")
    assert user is not None and user["role"] == "citizen"


def test_register_volunteer_allowed(app, client):
    client.post("/register", data={**GOOD, "role": "volunteer"})
    assert _fetch_user(app, "asha@example.com")["role"] == "volunteer"


def test_register_cannot_create_administrator(app, client):
    response = client.post("/register", data={**GOOD, "role": "administrator"})
    assert response.status_code == 400
    assert _count_users(app) == 0


def test_register_email_is_normalised(app, client):
    client.post("/register", data={**GOOD, "email": "  ASHA@Example.COM "})
    assert _fetch_user(app, "asha@example.com") is not None


@pytest.mark.parametrize("override", [
    {"email": "not-an-email"},
    {"password": "short1", "confirm_password": "short1"},
    {"password": "onlyletters", "confirm_password": "onlyletters"},
    {"confirm_password": "Different123"},
    {"full_name": "A"},
])
def test_register_invalid_input_rejected(app, client, override):
    response = client.post("/register", data={**GOOD, **override})
    assert response.status_code == 400
    assert _count_users(app) == 0


def test_register_duplicate_email_rejected(app, client, make_user):
    make_user("asha@example.com")
    response = client.post("/register", data={**GOOD, "email": "ASHA@example.com"})
    assert response.status_code == 409
    assert _count_users(app) == 1


def test_password_is_stored_hashed(app, client):
    client.post("/register", data=GOOD)
    stored = _fetch_user(app, "asha@example.com")["password_hash"]
    assert stored != GOOD["password"]
    assert GOOD["password"] not in stored
    assert check_password_hash(stored, GOOD["password"])


# ---- Login / logout ---------------------------------------------------------

def test_login_success_and_api_me(client, make_user):
    make_user("asha@example.com", full_name="Asha Verma")
    response = client.post("/login", data={"email": "asha@example.com", "password": "Password123"})
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/dashboard")

    me = client.get("/api/me")
    assert me.status_code == 200
    data = me.get_json()["data"]
    assert data["email"] == "asha@example.com"
    assert data["role"] == "citizen"
    assert "password_hash" not in data and "password" not in data


def test_login_wrong_password(client, make_user):
    make_user("asha@example.com")
    response = client.post("/login", data={"email": "asha@example.com", "password": "WrongPass999"})
    assert response.status_code == 401
    assert client.get("/api/me").status_code == 401


def test_login_unknown_email(client):
    response = client.post("/login", data={"email": "nobody@example.com", "password": "Password123"})
    assert response.status_code == 401
    assert b"Invalid email or password." in response.data


def test_login_inactive_user_rejected(client, make_user):
    make_user("asha@example.com", is_active=0)
    response = client.post("/login", data={"email": "asha@example.com", "password": "Password123"})
    assert response.status_code == 401


def test_logout_ends_session(client_for):
    user_client, _ = client_for("asha@example.com")
    assert user_client.get("/api/me").status_code == 200
    response = user_client.post("/logout")
    assert response.status_code == 302
    assert user_client.get("/api/me").status_code == 401


def test_logout_requires_post(client_for):
    user_client, _ = client_for("asha@example.com")
    assert user_client.get("/logout").status_code == 405


# ---- Unauthenticated access -------------------------------------------------

def test_api_me_unauthenticated_returns_json_401(client):
    response = client.get("/api/me")
    assert response.status_code == 401
    assert response.get_json()["error"]["code"] == "unauthenticated"


def test_dashboard_redirects_anonymous_to_login(client):
    response = client.get("/dashboard")
    assert response.status_code == 302
    assert "/login" in response.headers["Location"]


def test_login_next_parameter_blocks_external_redirect(client, make_user):
    make_user("asha@example.com")
    response = client.post("/login", data={
        "email": "asha@example.com",
        "password": "Password123",
        "next": "https://evil.example/steal",
    })
    assert response.status_code == 302
    assert "evil.example" not in response.headers["Location"]


# ---- CSRF -------------------------------------------------------------------

def test_csrf_blocks_post_without_token(csrf_app):
    client = csrf_app.test_client()
    response = client.post("/register", data=GOOD)
    assert response.status_code == 400


def test_csrf_allows_post_with_valid_token(csrf_app):
    client = csrf_app.test_client()
    page = client.get("/register").get_data(as_text=True)
    token = re.search(r'name="csrf_token" value="([^"]+)"', page).group(1)
    response = client.post("/register", data={**GOOD, "csrf_token": token})
    assert response.status_code == 302
