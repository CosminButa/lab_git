from flask_wtf import FlaskForm
from wtforms import PasswordField, StringField
from wtforms.validators import DataRequired, EqualTo, Length


class LoginForm(FlaskForm):
    username = StringField("Utilizator", validators=[DataRequired(), Length(max=64)])
    password = PasswordField("Parolă", validators=[DataRequired(), Length(max=256)])


class ChangePasswordForm(FlaskForm):
    current_password = PasswordField("Parola actuală", validators=[DataRequired(), Length(max=256)])
    new_password = PasswordField("Parola nouă", validators=[DataRequired(), Length(min=12, max=256)])
    confirm = PasswordField(
        "Confirmă parola nouă",
        validators=[DataRequired(), EqualTo("new_password", message="Parolele nu coincid.")],
    )
