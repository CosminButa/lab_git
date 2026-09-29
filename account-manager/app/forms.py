from flask_wtf import FlaskForm


class ConfirmForm(FlaskForm):
    """Empty form: carries only the CSRF token for POST-only actions."""
