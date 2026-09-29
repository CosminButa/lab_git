from flask_wtf import FlaskForm
from wtforms import BooleanField, SelectField, StringField
from wtforms.validators import DataRequired, Length, Regexp

from ..models import ROLE_ADMIN, ROLE_OPERATOR

USERNAME_RE = r"^[a-zA-Z0-9._@-]{2,64}$"


class OperatorForm(FlaskForm):
    username = StringField(
        "Utilizator",
        validators=[DataRequired(), Regexp(USERNAME_RE, message="Doar litere, cifre, . _ @ - (2-64 caractere).")],
    )
    display_name = StringField("Nume afișat", validators=[Length(max=128)])
    role = SelectField("Rol", choices=[(ROLE_OPERATOR, "Operator"), (ROLE_ADMIN, "Administrator")])
    active = BooleanField("Activ", default=True)


class EditOperatorForm(OperatorForm):
    username = None  # the username is immutable once created
