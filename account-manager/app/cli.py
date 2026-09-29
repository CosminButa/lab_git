import getpass
import sys

import click
from flask import Flask

from .extensions import db
from .models import ROLE_ADMIN, Operator
from .platforms import provisioning
from .security import generate_password


def register_cli(app: Flask) -> None:
    @app.cli.command("create-admin")
    @click.argument("username")
    def create_admin(username: str) -> None:
        """Create (or promote) an administrator. The password is prompted, never passed as an argument."""
        password = getpass.getpass("Parola: ")
        confirm = getpass.getpass("Confirmă parola: ")
        if password != confirm:
            raise click.ClickException("Parolele nu coincid.")
        if len(password) < app.config["PASSWORD_MIN_LENGTH"]:
            raise click.ClickException(f"Parola trebuie să aibă minim {app.config['PASSWORD_MIN_LENGTH']} caractere.")
        operator = Operator.query.filter_by(username=username).first()
        if operator is None:
            operator = Operator(username=username, display_name=username)
            db.session.add(operator)
        operator.role = ROLE_ADMIN
        operator.active = True
        operator.must_change_password = False
        operator.set_password(password)
        db.session.commit()
        click.echo(f"Administratorul '{username}' este pregătit.")

    @app.cli.command("provision-user")
    @click.argument("platform", type=click.Choice(["keycloak", "jira", "nextcloud"]))
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
        client = app.extensions["platforms"].get(platform)
        if client is None:
            raise click.ClickException(f"Platforma '{platform}' nu este configurată (variabile de mediu lipsă).")
        if no_password and client.password_required:
            raise click.ClickException(f"{client.label} cere o parolă la creare.")
        password = None if no_password else generate_password()
        report = provisioning.provision_user(client, username, email, first_name, last_name, password, list(groups))
        marks = {"ok": "[OK]     ", "exists": "[EXISTA] ", "skipped": "[SARIT]  ", "error": "[EROARE] "}
        for step in report.steps:
            click.echo(f"{marks[step.status]}{step.name}: {step.message}")
        if report.created and password:
            click.echo(f"Parola initiala (afisata o singura data): {password}")
        click.echo("Rezultat: " + ("OK" if not report.has_errors else "EROARE"))
        sys.exit(1 if report.has_errors else 0)
