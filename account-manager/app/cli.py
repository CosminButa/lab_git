import getpass
import sys
from pathlib import Path

import click
from flask import Flask

from .extensions import db
from .models import ROLE_ADMIN, Operator
from .platforms import provisioning
from .security import generate_password

MARKS = {"ok": "[OK]     ", "exists": "[EXISTA] ", "skipped": "[SARIT]  ", "error": "[EROARE] "}


def _echo(report: provisioning.Report) -> None:
    click.echo(f"== {report.username}")
    for step in report.steps:
        click.echo(f"{MARKS[step.status]}{step.name}: {step.message}")
    if report.password:
        click.echo(f"Parola (afisata o singura data): {report.password}")


def _platform(app: Flask, key: str, no_password: bool):
    client = app.extensions["platforms"].get(key)
    if client is None:
        raise click.ClickException(f"Platforma '{key}' nu este configurată (variabile de mediu lipsă).")
    if no_password and client.password_required:
        raise click.ClickException(f"{client.label} cere o parolă la creare.")
    return client


def register_cli(app: Flask) -> None:
    platform_arg = click.argument("platform", type=click.Choice(["keycloak", "jira", "nextcloud"]))

    @app.cli.command("create-admin")
    @click.argument("username")
    def create_admin(username: str) -> None:
        """Create (or promote) an administrator. The password is prompted, never passed as an argument."""
        password = getpass.getpass("Parola: ")
        if password != getpass.getpass("Confirmă parola: "):
            raise click.ClickException("Parolele nu coincid.")
        if len(password) < app.config["PASSWORD_MIN_LENGTH"]:
            raise click.ClickException(f"Parola trebuie să aibă minim {app.config['PASSWORD_MIN_LENGTH']} caractere.")
        operator = Operator.query.filter_by(username=username).first() or Operator(username=username, display_name=username)
        operator.role, operator.active, operator.must_change_password = ROLE_ADMIN, True, False
        operator.set_password(password)
        db.session.add(operator)
        db.session.commit()
        click.echo(f"Administratorul '{username}' este pregătit.")

    @app.cli.command("provision-user")
    @platform_arg
    @click.argument("username")
    @click.option("--email", default="")
    @click.option("--first-name", default="")
    @click.option("--last-name", default="")
    @click.option("--group", "groups", multiple=True, help="Grup de asociat; poate fi repetat.")
    @click.option("--no-password", is_flag=True, help="Nu seta parolă (doar Keycloak/Jira).")
    def provision_user(platform, username, email, first_name, last_name, groups, no_password):
        """Create a user on PLATFORM and add it to groups, verifying and reporting every step.

        Exit code 0 when every step is ok/exists, 1 when any step failed.
        """
        client = _platform(app, platform, no_password)
        password = None if no_password else generate_password()
        report = provisioning.provision_user(client, username, email, first_name, last_name, password, list(groups))
        _echo(report)
        sys.exit(1 if report.has_errors else 0)

    @app.cli.command("import-users")
    @platform_arg
    @click.argument("csv_file", type=click.Path(exists=True, dir_okay=False))
    @click.option("--no-password", is_flag=True, help="Nu seta parole (doar Keycloak/Jira).")
    def import_users(platform, csv_file, no_password):
        """Bulk-create users from a CSV (username,email,first_name,last_name,groups) with verified steps.

        Exit code 0 when every row is ok/exists, 1 when any row failed.
        """
        client = _platform(app, platform, no_password)
        rows = provisioning.parse_csv(Path(csv_file).read_text(encoding="utf-8"), app.config["IMPORT_MAX_ROWS"])
        reports = provisioning.import_rows(client, rows, not no_password)
        for report in reports:
            _echo(report)
        failed = sum(r.has_errors for r in reports)
        click.echo(f"Rezultat: {len(reports)} randuri, {sum(r.created for r in reports)} creati, {failed} cu erori")
        sys.exit(1 if failed else 0)
