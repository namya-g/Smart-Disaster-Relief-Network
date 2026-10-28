import pytest

STATIC_FILES = [
    "css/style.css",
    "css/responsive.css",
    "js/app.js",
    "js/api.js",
    "js/dashboard.js",
]


@pytest.mark.parametrize("path", STATIC_FILES)
def test_static_assets_are_served(client, path):
    response = client.get("/static/" + path)
    assert response.status_code == 200
    response.close()


def test_dashboard_renders_app_shell(client_for):
    user_client, _ = client_for("asha@example.com", role="citizen")
    response = user_client.get("/dashboard")
    html = response.get_data(as_text=True)
    assert response.status_code == 200
    assert 'name="csrf-token"' in html
    assert "Skip to main content" in html
    assert 'id="sidebar"' in html
    assert 'action="/logout"' in html
    assert 'id="toast-region"' in html


def test_citizen_never_sees_admin_navigation(client_for):
    user_client, _ = client_for("asha@example.com", role="citizen")
    html = user_client.get("/dashboard").get_data(as_text=True)
    assert "Administration" not in html
    assert "All requests" not in html


def test_admin_navigation_appears_only_when_page_exists(app, client_for):
    admin_client, _ = client_for("admin@example.com", role="administrator")
    html = admin_client.get("/dashboard").get_data(as_text=True)
    assert ("Administration" in html) == ("pages.admin" in app.view_functions)


def test_volunteer_navigation_is_role_specific(client_for):
    volunteer_client, _ = client_for("vol@example.com", role="volunteer")
    html = volunteer_client.get("/dashboard").get_data(as_text=True)
    assert "New request" not in html
    assert "Administration" not in html


def test_dashboard_requires_login(client):
    response = client.get("/dashboard")
    assert response.status_code == 302
    assert "/login" in response.headers["Location"]
