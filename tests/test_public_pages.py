from app.permissions import admin_required


def _boom():
    raise RuntimeError("secret internal detail")


def _add_failing_routes(app):
    app.config["PROPAGATE_EXCEPTIONS"] = False  # let the 500 handler run in tests
    app.add_url_rule("/_boom", "boom_page", _boom)
    app.add_url_rule("/api/_boom", "boom_api", _boom)


# ---- Landing page -------------------------------------------------------------

def test_landing_page_for_anonymous_visitor(client):
    response = client.get("/")
    html = response.get_data(as_text=True)
    assert response.status_code == 200
    assert "Coordinate relief requests" in html
    assert "How it works" in html
    assert "not monitored for real emergencies" in html
    assert 'href="/register"' in html
    assert 'href="/login"' in html


def test_landing_page_for_logged_in_user_links_to_dashboard(client_for):
    user_client, _ = client_for("asha@example.com")
    html = user_client.get("/").get_data(as_text=True)
    assert "Go to dashboard" in html
    assert 'href="/register"' not in html


# ---- Login and registration pages ---------------------------------------------

def test_login_page_is_accessible_and_has_csrf(client):
    html = client.get("/login").get_data(as_text=True)
    assert 'for="email"' in html
    assert 'autocomplete="email"' in html
    assert 'autocomplete="current-password"' in html
    assert 'name="csrf_token"' in html
    assert "data-password-toggle" in html


def test_register_page_offers_only_public_roles(client):
    html = client.get("/register").get_data(as_text=True)
    assert 'value="citizen"' in html
    assert 'value="volunteer"' in html
    assert 'value="administrator"' not in html
    assert 'autocomplete="new-password"' in html
    assert 'name="confirm_password"' in html


def test_login_shows_session_expired_notice(client):
    html = client.get("/login?expired=1").get_data(as_text=True)
    assert "session has expired" in html


def test_login_keeps_next_in_hidden_field(client):
    html = client.get("/login?next=/dashboard").get_data(as_text=True)
    assert 'name="next" value="/dashboard"' in html


def test_login_empty_submission_shows_field_errors(client):
    response = client.post("/login", data={"email": "", "password": ""})
    html = response.get_data(as_text=True)
    assert response.status_code == 400
    assert "Enter your email address." in html
    assert 'aria-invalid="true"' in html


def test_register_errors_preserve_entered_values(client):
    response = client.post("/register", data={
        "full_name": "Asha Verma",
        "email": "asha@example.com",
        "role": "volunteer",
        "password": "short",
        "confirm_password": "short",
    })
    html = response.get_data(as_text=True)
    assert response.status_code == 400
    assert 'value="Asha Verma"' in html
    assert 'value="asha@example.com"' in html
    assert "Password must be" in html
    assert "short</" not in html  # the password is never echoed back


def test_protected_page_redirect_keeps_destination(client):
    response = client.get("/dashboard")
    assert response.status_code == 302
    assert "next=%2Fdashboard" in response.headers["Location"]


# ---- Error pages ----------------------------------------------------------------

def test_404_page_html(client):
    response = client.get("/no-such-page")
    html = response.get_data(as_text=True)
    assert response.status_code == 404
    assert "Page not found" in html
    assert "Go to home page" in html


def test_404_json_for_api_paths(client):
    response = client.get("/api/no-such-endpoint")
    assert response.status_code == 404
    assert response.get_json()["error"]["code"] == "not_found"


def test_405_page(client):
    response = client.get("/logout")
    assert response.status_code == 405
    assert "Method not allowed" in response.get_data(as_text=True)


def test_403_page_html(app, client_for):
    app.add_url_rule("/_admin-only", "admin_only_page", admin_required(lambda: "ok"))
    citizen, _ = client_for("asha@example.com", role="citizen")
    response = citizen.get("/_admin-only")
    assert response.status_code == 403
    assert "Access denied" in response.get_data(as_text=True)


def test_500_page_hides_internal_details(app, client):
    _add_failing_routes(app)
    response = client.get("/_boom")
    html = response.get_data(as_text=True)
    assert response.status_code == 500
    assert "Something went wrong" in html
    assert "secret internal detail" not in html
    assert "Traceback" not in html


def test_500_json_for_api_paths_hides_internal_details(app, client):
    _add_failing_routes(app)
    response = client.get("/api/_boom")
    assert response.status_code == 500
    assert response.get_json()["error"]["code"] == "server_error"
    assert "secret internal detail" not in response.get_data(as_text=True)


def test_csrf_failure_shows_friendly_page(csrf_app):
    response = csrf_app.test_client().post(
        "/login", data={"email": "a@example.com", "password": "Password123"})
    assert response.status_code == 400
    assert "Session check failed" in response.get_data(as_text=True)
