from flask_wtf import FlaskForm
from flask_wtf.file import FileAllowed, FileField, FileRequired
from wtforms import BooleanField, PasswordField, SelectField, SelectMultipleField, StringField
from wtforms.validators import DataRequired, Length, Optional, Regexp

from ..security import EMAIL_RE, USERNAME_RE

_strip = [lambda v: (v or "").strip()]


class SearchForm(FlaskForm):
    class Meta:
        csrf = False  # GET form

    q = StringField("Căutare", validators=[Optional(), Length(max=64)])


class CreateUserForm(FlaskForm):
    username = StringField(
        "Utilizator", filters=_strip,
        validators=[DataRequired(), Regexp(USERNAME_RE, message="Litere, cifre, . _ @ - (2-64 caractere), începe cu literă/cifră.")],
    )
    email = StringField("E-mail", filters=_strip, validators=[Optional(), Length(max=128), Regexp(EMAIL_RE, message="Adresă de e-mail invalidă.")])
    first_name = StringField("Prenume", filters=_strip, validators=[Length(max=64)])
    last_name = StringField("Nume", filters=_strip, validators=[Length(max=64)])
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


class ImportForm(FlaskForm):
    file = FileField("Fișier CSV", validators=[FileRequired(), FileAllowed(["csv", "txt"], "Doar fișiere .csv")])
    generate_password = BooleanField("Generează parole pentru utilizatorii noi", default=True)
