import pytest
from werkzeug.security import generate_password_hash

from app import create_app
from app.db import get_db, init_db

TEST_PASSWORD = "Password123"


def _build_app(tmp_path, csrf_enabled):
    app = create_app({
        "TESTING": True,
        "SECRET_KEY": "test-secret-key",
        "DATABASE": str(tmp_path / "test.sqlite"),
        "WTF_CSRF_ENABLED": csrf_enabled,
        "SESSION_COOKIE_SECURE": False,  # test client uses plain http
    })
    with app.app_context():
        init_db()
    return app


@pytest.fixture
def app(tmp_path):
    """App with CSRF disabled (most tests); fresh temporary database."""
    return _build_app(tmp_path, csrf_enabled=False)


@pytest.fixture
def csrf_app(tmp_path):
    """App with CSRF protection ON, for testing the CSRF mechanism itself."""
    return _build_app(tmp_path, csrf_enabled=True)


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def make_user(app):
    """Insert a user directly and return its id."""

    def _make(email, role="citizen", password=TEST_PASSWORD,
              full_name="Test User", is_active=1):
        with app.app_context():
            db = get_db()
            cursor = db.execute(
                "INSERT INTO users (full_name, email, password_hash, role, is_active) "
                "VALUES (?, ?, ?, ?, ?)",
                (full_name, email, generate_password_hash(password), role, is_active),
            )
            db.commit()
            return cursor.lastrowid

    return _make


@pytest.fixture
def client_for(app, make_user):
    """Create a user and return (logged-in test client, user id)."""

    def _client_for(email, role="citizen"):
        user_id = make_user(email, role=role)
        user_client = app.test_client()
        response = user_client.post("/login", data={"email": email, "password": TEST_PASSWORD})
        assert response.status_code == 302, "test login failed"
        return user_client, user_id

    return _client_for
