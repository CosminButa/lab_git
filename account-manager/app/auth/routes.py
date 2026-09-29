import logging

from flask import Blueprint, abort, current_app, flash, redirect, render_template, request, session, url_for
from flask_login import current_user, login_required, login_user, logout_user

from .. import audit
from ..extensions import db
from ..models import Operator
from ..security import RateLimiter
from .forms import ChangePasswordForm, LoginForm

bp = Blueprint("auth", __name__)
log = logging.getLogger(__name__)


def _rate_limiter() -> RateLimiter:
    limiter = current_app.extensions.get("login_limiter")
    if limiter is None:
        limiter = RateLimiter(limit=current_app.config["LOGIN_RATE_LIMIT_PER_MINUTE"])
        current_app.extensions["login_limiter"] = limiter
    return limiter


@bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("index"))
    form = LoginForm()
    if form.validate_on_submit():
        if not _rate_limiter().allow(request.remote_addr):
            log.warning("login rate limit hit from %s", request.remote_addr)
            abort(429)
        username = form.username.data.strip()
        operator = Operator.query.filter_by(username=username).first()
        generic_error = "Utilizator sau parolă incorecte."

        if operator is None or not operator.active:
            # Same message and similar timing for unknown / disabled accounts.
            Operator(password_hash="scrypt:32768:8:1$x$y").check_password(form.password.data)
            flash(generic_error, "danger")
            return render_template("auth/login.html", form=form), 401

        if operator.is_locked:
            flash("Cont blocat temporar din cauza prea multor încercări eșuate. Încearcă mai târziu.", "danger")
            return render_template("auth/login.html", form=form), 423

        if not operator.check_password(form.password.data):
            operator.register_failure(
                current_app.config["LOGIN_MAX_FAILURES"], current_app.config["LOGIN_LOCKOUT_MINUTES"]
            )
            db.session.commit()
            log.warning("failed login for '%s' from %s", username, request.remote_addr)
            flash(generic_error, "danger")
            return render_template("auth/login.html", form=form), 401

        operator.register_success()
        db.session.commit()
        session.clear()  # prevent session fixation
        login_user(operator, remember=False)
        session.permanent = True
        audit.record("app", "login", target=operator.username)
        if operator.must_change_password:
            flash("Trebuie să îți schimbi parola înainte de a continua.", "warning")
            return redirect(url_for("auth.change_password"))
        return redirect(url_for("index"))
    return render_template("auth/login.html", form=form)


@bp.post("/logout")
@login_required
def logout():
    audit.record("app", "logout", target=current_user.username)
    logout_user()
    session.clear()
    flash("Te-ai deconectat.", "info")
    return redirect(url_for("auth.login"))


@bp.route("/account/password", methods=["GET", "POST"])
@login_required
def change_password():
    form = ChangePasswordForm()
    form.new_password.validators[1].min = current_app.config["PASSWORD_MIN_LENGTH"]
    if form.validate_on_submit():
        if not current_user.check_password(form.current_password.data):
            flash("Parola actuală este greșită.", "danger")
            return render_template("auth/change_password.html", form=form), 400
        if form.new_password.data == form.current_password.data:
            flash("Parola nouă trebuie să fie diferită de cea actuală.", "danger")
            return render_template("auth/change_password.html", form=form), 400
        operator = current_user._get_current_object()
        operator.set_password(form.new_password.data)
        operator.must_change_password = False
        db.session.commit()
        # set_password rotated the session token; re-login so this session stays valid
        login_user(operator, remember=False)
        audit.record("app", "change_password", target=operator.username)
        flash("Parola a fost schimbată.", "success")
        return redirect(url_for("index"))
    return render_template("auth/change_password.html", form=form)


@bp.get("/account")
@login_required
def account():
    return render_template("auth/account.html")
