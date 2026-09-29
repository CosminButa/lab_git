from __future__ import annotations

from flask import Blueprint, abort, current_app, flash, redirect, render_template, request, url_for
from flask_login import login_required

from .. import audit
from ..forms import ConfirmForm
from ..security import USERNAME_RE, generate_password
from . import provisioning
from .base import NotFound, PlatformClient, PlatformError
from .forms import CreateUserForm, GroupForm, ImportForm, SearchForm

bp = Blueprint("platforms", __name__, url_prefix="/p")


def _client(key: str) -> PlatformClient:
    return current_app.extensions["platforms"].get(key) or abort(404)


def _checked(username: str) -> str:
    """Usernames come from URLs: enforce the safe character set before they reach an API."""
    return username if USERNAME_RE.match(username) else abort(400)


def _group_choices(client: PlatformClient, exclude: set[str] = frozenset()) -> tuple[list[tuple[str, str]], str | None]:
    try:
        return [(g.id, g.name) for g in client.cached_groups() if g.id not in exclude], None
    except PlatformError as exc:
        return [], str(exc)


def _detail(key: str, username: str):
    return redirect(url_for("platforms.user_detail", key=key, username=username))


def _render_report(client: PlatformClient, action: str, report: provisioning.Report, title: str):
    audit.record(client.key, action, target=report.username, outcome=report.outcome, details=report.summary())
    return render_template("platforms/report.html", client=client, report=report, title=title), (502 if report.has_errors else 200)


@bp.get("/<key>/")
@login_required
def users(key: str):
    client = _client(key)
    form = SearchForm(request.args)
    query = (form.q.data or "").strip()
    results, error = [], None
    if "q" in request.args:
        try:
            results = client.search_users(query, limit=current_app.config["SEARCH_RESULT_LIMIT"])
        except PlatformError as exc:
            error = str(exc)
    return render_template("platforms/users.html", client=client, form=form, results=results, error=error, query=query)


@bp.route("/<key>/users/new", methods=["GET", "POST"])
@login_required
def new_user(key: str):
    client = _client(key)
    form = CreateUserForm()
    form.groups.choices, groups_error = _group_choices(client)
    if groups_error:
        flash(f"Grupurile nu au putut fi încărcate: {groups_error}", "warning")
    if not form.validate_on_submit():
        return render_template("platforms/user_form.html", client=client, form=form)
    password = generate_password() if form.generate_password.data else form.password.data or None
    if password is None and client.password_required:
        flash("Această platformă cere o parolă. Introdu una sau bifează generarea automată.", "danger")
        return render_template("platforms/user_form.html", client=client, form=form), 400
    report = provisioning.provision_user(
        client, form.username.data, form.email.data, form.first_name.data, form.last_name.data, password, form.groups.data
    )
    if not form.generate_password.data:
        report.password = None  # operator typed it; nothing to reveal
    return _render_report(client, "user.provision", report, "Creare utilizator")


@bp.route("/<key>/users/import", methods=["GET", "POST"])
@login_required
def import_users(key: str):
    client = _client(key)
    form = ImportForm()
    if not form.validate_on_submit():
        return render_template("platforms/import.html", client=client, form=form, columns=provisioning.CSV_COLUMNS)
    if not form.generate_password.data and client.password_required:
        flash(f"{client.label} cere o parolă la creare; bifează generarea de parole.", "danger")
        return render_template("platforms/import.html", client=client, form=form, columns=provisioning.CSV_COLUMNS), 400
    try:
        text = form.file.data.read().decode("utf-8")
    except UnicodeDecodeError:
        flash("Fișierul trebuie să fie codificat UTF-8.", "danger")
        return render_template("platforms/import.html", client=client, form=form, columns=provisioning.CSV_COLUMNS), 400
    rows = provisioning.parse_csv(text, current_app.config["IMPORT_MAX_ROWS"])
    reports = provisioning.import_rows(client, rows, form.generate_password.data)
    for report in reports:
        audit.record(key, "user.import", target=report.username, outcome=report.outcome, details=report.summary())
    return render_template("platforms/import_result.html", client=client, reports=reports)


@bp.get("/<key>/users/<username>")
@login_required
def user_detail(key: str, username: str):
    client = _client(key)
    try:
        user = client.get_user(_checked(username))
    except PlatformError as exc:
        flash(str(exc), "warning" if isinstance(exc, NotFound) else "danger")
        return redirect(url_for("platforms.users", key=key))
    group_form = GroupForm()
    group_form.group_id.choices, groups_error = _group_choices(client, {g.id for g in user.groups})
    if groups_error:
        flash(groups_error, "warning")
    return render_template("platforms/user_detail.html", client=client, user=user, group_form=group_form, confirm=ConfirmForm())


def _action(client: PlatformClient, username: str, action: str, fn, success_message: str, success_url: str | None = None, **details):
    """Run a state-changing call with CSRF check and audit trail, then return to the user page."""
    _checked(username)
    if not ConfirmForm().validate_on_submit():
        abort(400)
    detail = " ".join(f"{k}={v}" for k, v in details.items())
    try:
        fn()
    except PlatformError as exc:
        audit.record(client.key, action, target=username, outcome="error", details=f"{detail} {exc}".strip())
        flash(str(exc), "danger")
        return _detail(client.key, username)
    audit.record(client.key, action, target=username, details=detail)
    flash(success_message, "success")
    return redirect(success_url) if success_url else _detail(client.key, username)


@bp.post("/<key>/users/<username>/groups/add")
@login_required
def add_group(key: str, username: str):
    client = _client(key)
    form = GroupForm()
    form.group_id.choices, groups_error = _group_choices(client)
    if groups_error or not form.validate_on_submit():
        flash(groups_error or "Grup invalid.", "danger")
        return _detail(key, _checked(username))
    report = provisioning.assign_group(client, _checked(username), form.group_id.data)
    return _render_report(client, "group.add", report, "Asociere la grup")


@bp.post("/<key>/users/<username>/groups/remove")
@login_required
def remove_group(key: str, username: str):
    client = _client(key)
    group_id = request.form.get("group_id", "")
    if not 0 < len(group_id) <= 255:
        abort(400)
    return _action(client, username, "group.remove", lambda: client.remove_from_group(username, group_id), "Utilizator scos din grup.", group=group_id)


@bp.post("/<key>/users/<username>/enable")
@login_required
def enable_user(key: str, username: str):
    client = _client(key)
    return _action(client, username, "user.enable", lambda: client.set_enabled(username, True), "Cont activat.")


@bp.post("/<key>/users/<username>/disable")
@login_required
def disable_user(key: str, username: str):
    client = _client(key)
    return _action(client, username, "user.disable", lambda: client.set_enabled(username, False), "Cont dezactivat.")


@bp.post("/<key>/users/<username>/reset-password")
@login_required
def reset_password(key: str, username: str):
    client = _client(key)
    if not ConfirmForm().validate_on_submit():
        abort(400)
    report = provisioning.reset_password(client, _checked(username))
    return _render_report(client, "user.reset_password", report, "Resetare parolă")


@bp.post("/<key>/users/<username>/delete")
@login_required
def delete_user(key: str, username: str):
    client = _client(key)
    if request.form.get("confirm_username") != username:
        flash("Confirmarea nu corespunde cu numele utilizatorului. Nimic nu a fost șters.", "danger")
        return _detail(key, _checked(username))
    return _action(
        client, username, "user.delete", lambda: client.delete_user(username),
        f"Utilizatorul {username} a fost șters din {client.label}.", success_url=url_for("platforms.users", key=key),
    )


@bp.get("/<key>/health")
@login_required
def health(key: str):
    try:
        _client(key).health()
    except PlatformError as exc:
        return {"platform": key, "ok": False, "error": str(exc)}, 502
    return {"platform": key, "ok": True}
