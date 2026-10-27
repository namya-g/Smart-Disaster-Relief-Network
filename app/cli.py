"""Flask CLI commands for database setup and administration."""
import re
import sqlite3

import click
from flask import current_app
from flask.cli import with_appcontext
from werkzeug.security import generate_password_hash

from .db import get_db, init_db, transaction

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

# FICTIONAL demonstration data. Not real places, supplies, or availability.
# Columns: name, category, quantity, unit, status, address, latitude, longitude
DEMO_RESOURCES = [
    ("[DEMO] First-aid kits", "medical_supplies", 150, "kits", "available",
     "Fictional demo address A", 28.6139, 77.2090),
    ("[DEMO] Drinking water", "water", 40, "crates", "low",
     "Fictional demo address B", 28.6200, 77.2200),
    ("[DEMO] Blankets", "blankets", 0, "pieces", "unavailable",
     "Fictional demo address C", 28.6050, 77.2000),
    ("[DEMO] Packaged food", "food", 300, "packs", "available",
     "Fictional demo address D", 28.6300, 77.2150),
]

# Columns: name, address, latitude, longitude, capacity, occupancy, status
DEMO_SHELTERS = [
    ("[DEMO] Community Hall Shelter", "Fictional demo address E", 28.6100, 77.2300, 120, 45, "open"),
    ("[DEMO] School Ground Shelter", "Fictional demo address F", 28.6250, 77.1950, 80, 80, "full"),
    ("[DEMO] Sports Complex Shelter", "Fictional demo address G", 28.5980, 77.2120, 60, 0, "temporarily_closed"),
]

NOT_INITIALISED = "Database is not initialised. Run: flask --app run init-db"


@click.command("init-db")
@click.option("--reset", is_flag=True, help="Drop all tables first. DESTROYS ALL DATA.")
@with_appcontext
def init_db_command(reset):
    """Create the database tables."""
    if reset and not click.confirm("This will DELETE ALL DATA. Continue?"):
        click.echo("Cancelled.")
        return
    init_db(reset=reset)
    click.echo(f"Database ready at {current_app.config['DATABASE']}")


@click.command("seed-demo")
@with_appcontext
def seed_demo_command():
    """Insert fictional demo resources and shelters (safe to repeat)."""
    added_resources = 0
    added_shelters = 0
    try:
        with transaction() as conn:
            for row in DEMO_RESOURCES:
                exists = conn.execute(
                    "SELECT 1 FROM resources WHERE name = ? AND is_demo = 1", (row[0],)
                ).fetchone()
                if exists:
                    continue
                conn.execute(
                    "INSERT INTO resources (name, category, quantity, unit, status, "
                    "address, latitude, longitude, is_demo) VALUES (?,?,?,?,?,?,?,?,1)",
                    row,
                )
                added_resources += 1
            for row in DEMO_SHELTERS:
                exists = conn.execute(
                    "SELECT 1 FROM shelters WHERE name = ? AND is_demo = 1", (row[0],)
                ).fetchone()
                if exists:
                    continue
                conn.execute(
                    "INSERT INTO shelters (name, address, latitude, longitude, "
                    "capacity, occupancy, status, is_demo) VALUES (?,?,?,?,?,?,?,1)",
                    row,
                )
                added_shelters += 1
    except sqlite3.OperationalError as exc:
        raise click.ClickException(f"{NOT_INITIALISED} ({exc})")
    click.echo(
        f"Added {added_resources} demo resources and {added_shelters} demo shelters "
        "(all fictional)."
    )


@click.command("create-admin")
@with_appcontext
def create_admin_command():
    """Create an administrator account (interactive)."""
    full_name = click.prompt("Full name").strip()
    email = click.prompt("Email").strip().lower()
    password = click.prompt("Password", hide_input=True, confirmation_prompt=True)

    if not 2 <= len(full_name) <= 100:
        raise click.ClickException("Full name must be 2-100 characters.")
    if not EMAIL_RE.match(email) or len(email) > 254:
        raise click.ClickException("Please enter a valid email address.")
    if len(password) < 8:
        raise click.ClickException("Password must be at least 8 characters.")

    try:
        with transaction() as conn:
            conn.execute(
                "INSERT INTO users (full_name, email, password_hash, role) "
                "VALUES (?, ?, ?, 'administrator')",
                (full_name, email, generate_password_hash(password)),
            )
    except sqlite3.IntegrityError:
        raise click.ClickException("An account with that email already exists.")
    except sqlite3.OperationalError as exc:
        raise click.ClickException(f"{NOT_INITIALISED} ({exc})")
    click.echo(f"Administrator created: {email}")


@click.command("db-status")
@with_appcontext
def db_status_command():
    """Show tables and row counts (for checking setup)."""
    db = get_db()
    tables = [
        row["name"]
        for row in db.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' "
            "AND name NOT LIKE 'sqlite_%' ORDER BY name"
        )
    ]
    if not tables:
        click.echo(NOT_INITIALISED)
        return
    click.echo(f"Database: {current_app.config['DATABASE']}")
    for name in tables:  # names come from sqlite_master, not user input
        count = db.execute(f'SELECT COUNT(*) AS n FROM "{name}"').fetchone()["n"]
        click.echo(f"  {name}: {count} rows")


def init_app(app):
    app.cli.add_command(init_db_command)
    app.cli.add_command(seed_demo_command)
    app.cli.add_command(create_admin_command)
    app.cli.add_command(db_status_command)
