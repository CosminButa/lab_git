from flask_wtf import FlaskForm
from wtforms import BooleanField, PasswordField, SelectField, SelectMultipleField, StringField
from wtforms.validators import DataRequired, Length, Optional, Regexp

USERNAME_RE = r"^[a-zA-Z0-9][a-zA-Z0-9._@-]{1,63}$"


class SearchForm(FlaskForm):
    class Meta:
        csrf = False  # GET form

    q = StringField("Căutare", validators=[Optional(), Length(max=64)])


class CreateUserForm(FlaskForm):
    username = StringField(
        "Utilizator",
        validators=[DataRequired(), Regexp(USERNAME_RE, message="Litere, cifre, . _ @ - (2-64 caractere), începe cu literă/cifră.")],
    )
    email = StringField("E-mail", validators=[Optional(), Length(max=128), Regexp(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", message="Adresă de e-mail invalidă.")])
    first_name = StringField("Prenume", validators=[Optional(), Length(max=64)])
    last_name = StringField("Nume", validators=[Optional(), Length(max=64)])
    password = PasswordField(
        "Parolă inițială",
        validators=[Optional(), Length(min=12, max=128)],
        description="Lasă gol pentru a genera una automat. Va fi afișată o singură dată.",
    )
    generate_password = BooleanField("Generează parolă", default=True)
    groups = SelectMultipleField("Grupuri", validators=[Optional()], validate_choice=True,
                                 description="Ține Ctrl/Cmd apăsat pentru selecție multiplă.")


class GroupForm(FlaskForm):
    group_id = SelectField("Grup", validators=[DataRequired()], validate_choice=True)


class ConfirmForm(FlaskForm):
    """CSRF-only form for POST actions."""
