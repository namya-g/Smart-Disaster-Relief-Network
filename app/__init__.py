"""SDRN application factory."""
import os

from flask import Flask, jsonify, render_template, request
from flask_wtf.csrf import CSRFError
from jinja2 import TemplateNotFound

from . import cli, db
from .config import Config
from .extensions import csrf, login_manager


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

    # Blueprints (auth, pages, api) are registered here in later phases.

    return app


def register_error_handlers(app):
    def respond(status, code, message, template):
        if request.path.startswith("/api/"):
            return jsonify({"error": {"code": code, "message": message}}), status
        try:
            return render_template(template), status
        except TemplateNotFound:
            # Templates arrive in Phase 4; plain text until then.
            return message, status

    @app.errorhandler(CSRFError)
    def csrf_error(error):
        return respond(400, "csrf_failed",
                       "Your session token is missing or expired. Refresh the page and try again.",
                       "500.html")

    @app.errorhandler(400)
    def bad_request(error):
        return respond(400, "validation_error", "The request was invalid.", "500.html")

    @app.errorhandler(403)
    def forbidden(error):
        return respond(403, "forbidden", "You do not have permission to do that.", "403.html")

    @app.errorhandler(404)
    def not_found(error):
        return respond(404, "not_found", "The requested page or record was not found.", "404.html")

    @app.errorhandler(405)
    def method_not_allowed(error):
        return respond(405, "method_not_allowed", "That method is not allowed here.", "404.html")

    @app.errorhandler(500)
    def server_error(error):
        return respond(500, "server_error",
                       "Something went wrong on our side. Please try again later.", "500.html")
