"""SDRN application factory."""
import os

from flask import Flask, jsonify, render_template, request
from flask_wtf.csrf import CSRFError
from jinja2 import TemplateNotFound

from . import cli, db
from .api import api_bp
from .auth import auth_bp
from .config import Config
from .extensions import csrf, login_manager
from .pages import pages_bp


def create_app(test_config=None):
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_object(Config)
    if test_config:
        app.config.update(test_config)

    os.makedirs(app.instance_path, exist_ok=True)
    if not app.config.get("DATABASE"):
        app.config["DATABASE"] = os.path.join(app.instance_path, "sdrn.sqlite")

    if not app.config.get("SECRET_KEY"):
        raise RuntimeError(
            "SECRET_KEY is not set. Copy .env.example to .env and set SECRET_KEY. "
            'Generate one with: python -c "import secrets; print(secrets.token_hex(32))"'
        )

    db.init_app(app)
    cli.init_app(app)
    csrf.init_app(app)
    login_manager.init_app(app)

    app.register_blueprint(pages_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(api_bp)

    register_error_handlers(app)

    @app.after_request
    def add_security_headers(response):
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "same-origin")
        return response

    @app.get("/health")
    def health():
        row = db.get_db().execute(
            "SELECT COUNT(*) AS n FROM sqlite_master "
            "WHERE type = 'table' AND name = 'users'"
        ).fetchone()
        return jsonify({"data": {"status": "ok", "database_initialised": row["n"] == 1}})

    return app


def register_error_handlers(app):
    def respond(status, code, title, message, template):
        """JSON for /api/... requests, an HTML error page for everything else."""
        if request.path.startswith("/api/"):
            return jsonify({"error": {"code": code, "message": message}}), status
        try:
            return render_template(template, error_status=status,
                                   error_title=title, error_message=message), status
        except TemplateNotFound:
            return message, status

    @app.errorhandler(CSRFError)
    def csrf_error(error):
        return respond(400, "csrf_failed", "Session check failed",
                       "Your session token is missing or expired. "
                       "Go back, refresh the page and try again.", "400.html")

    @app.errorhandler(400)
    def bad_request(error):
        return respond(400, "validation_error", "Bad request",
                       "The request could not be understood.", "400.html")

    @app.errorhandler(403)
    def forbidden(error):
        return respond(403, "forbidden", "Access denied",
                       "You do not have permission to view this page or perform this action.",
                       "403.html")

    @app.errorhandler(404)
    def not_found(error):
        return respond(404, "not_found", "Page not found",
                       "The page or record you asked for does not exist, "
                       "or you are not allowed to see it.", "404.html")

    @app.errorhandler(405)
    def method_not_allowed(error):
        return respond(405, "method_not_allowed", "Method not allowed",
                       "That action is not supported on this page.", "404.html")

    @app.errorhandler(500)
    def server_error(error):
        return respond(500, "server_error", "Something went wrong",
                       "An unexpected error occurred on our side. Please try again later.",
                       "500.html")
