import getpass

import click
from flask import Flask

from .extensions import db
from .models import ROLE_ADMIN, Operator


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
