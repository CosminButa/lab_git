from __future__ import annotations

from flask import Blueprint, abort, current_app, flash, redirect, render_template, request, url_for
from flask_login import login_required

from .. import audit
from ..security import generate_password
from .base import NotFound, PlatformClient, PlatformError
from .forms import ConfirmForm, CreateUserForm, GroupForm, SearchForm

bp = Blueprint("platforms", __name__, url_prefix="/p")


def _client(key: str) -> PlatformClient:
    client = current_app.extensions["platforms"].get(key)
    if client is None:
        abort(404)
    return client


def _validate_username(username: str) -> str:
    """Usernames come from URLs; keep them to a safe character set before hitting an API."""
    if not username or len(username) > 64 or not all(c.isalnum() or c in "._@-" for c in username):
        abort(400)
    return username


def _group_form(client: PlatformClient, exclude: set[str]) -> GroupForm:
    form = GroupForm()
    groups = client.list_groups()
    form.group_id.choices = [(g.id, g.name) for g in groups if g.id not in exclude]
    return form


@bp.get("/<key>/")
@login_required
def users(key: str):
    client = _client(key)
    form = SearchForm(request.args)
    query = (form.q.data or "").strip()
    results, error = [], None
    if request.args.get("q") is not None or key == "keycloak":
        try:
            results = client.search_users(query)
        except PlatformError as exc:
            error = str(exc)
    return render_template("platforms/users.html", client=client, form=form, results=results, error=error, query=query)


@bp.route("/<key>/users/new", methods=["GET", "POST"])
@login_required
def new_user(key: str):
    client = _client(key)
    form = CreateUserForm()
    if request.method == "GET":
        form.generate_password.data = True
    if form.validate_on_submit():
        username = form.username.data.strip()
        password: str | None = None
        shown_password: str | None = None
        if form.generate_password.data:
            password = shown_password = generate_password()
        elif form.password.data:
            password = form.password.data
        elif client.password_required:
            flash("Această platformă cere o parolă. Introdu una sau bifează generarea automată.", "danger")
            return render_template("platforms/user_form.html", client=client, form=form), 400
        try:
            user = client.create_user(
                username,
                (form.email.data or "").strip(),
                (form.first_name.data or "").strip(),
                (form.last_name.data or "").strip(),
                password,
            )
        except PlatformError as exc:
            audit.record(key, "user.create", target=username, outcome="error", details=str(exc))
            flash(str(exc), "danger")
            return render_template("platforms/user_form.html", client=client, form=form), 502
        audit.record(key, "user.create", target=username, details=f"email={user.email}")
        return render_template("platforms/user_created.html", client=client, user=user, shown_password=shown_password)
    return render_template("platforms/user_form.html", client=client, form=form)


@bp.get("/<key>/users/<username>")
@login_required
def user_detail(key: str, username: str):
    client = _client(key)
    _validate_username(username)
    try:
        user = client.get_user(username)
        group_form = _group_form(client, {g.id for g in user.groups})
    except NotFound as exc:
        flash(str(exc), "warning")
        return redirect(url_for("platforms.users", key=key))
    except PlatformError as exc:
        flash(str(exc), "danger")
        return redirect(url_for("platforms.users", key=key))
    return render_template(
        "platforms/user_detail.html", client=client, user=user, group_form=group_form, confirm=ConfirmForm()
    )


def _action(key: str, username: str, action: str, fn, success_message: str, **audit_details):
    """Run a state-changing platform call with CSRF check, audit trail and consistent flashing."""
    _validate_username(username)
    if not ConfirmForm().validate_on_submit():
        abort(400)
    details = " ".join(f"{k}={v}" for k, v in audit_details.items())
    try:
        fn()
    except PlatformError as exc:
        audit.record(key, action, target=username, outcome="error", details=f"{details} {exc}".strip())
        flash(str(exc), "danger")
        return redirect(url_for("platforms.user_detail", key=key, username=username))
    audit.record(key, action, target=username, details=details)
    flash(success_message, "success")
    return redirect(url_for("platforms.user_detail", key=key, username=username))


@bp.post("/<key>/users/<username>/groups/add")
@login_required
def add_group(key: str, username: str):
    client = _client(key)
    _validate_username(username)
    form = GroupForm()
    try:
        form.group_id.choices = [(g.id, g.name) for g in client.list_groups()]
    except PlatformError as exc:
        flash(str(exc), "danger")
        return redirect(url_for("platforms.user_detail", key=key, username=username))
    if not form.validate_on_submit():
        flash("Grup invalid.", "danger")
        return redirect(url_for("platforms.user_detail", key=key, username=username))
    group_id = form.group_id.data
    return _action(
        key, username, "group.add", lambda: client.add_to_group(username, group_id), "Utilizator adăugat în grup.", group=group_id
    )


@bp.post("/<key>/users/<username>/groups/remove")
@login_required
def remove_group(key: str, username: str):
    client = _client(key)
    group_id = request.form.get("group_id", "")
    if not group_id or len(group_id) > 255:
        abort(400)
    return _action(
        key, username, "group.remove", lambda: client.remove_from_group(username, group_id), "Utilizator scos din grup.", group=group_id
    )


@bp.post("/<key>/users/<username>/enable")
@login_required
def enable_user(key: str, username: str):
    client = _client(key)
    return _action(key, username, "user.enable", lambda: client.set_enabled(username, True), "Cont activat.")


@bp.post("/<key>/users/<username>/disable")
@login_required
def disable_user(key: str, username: str):
    client = _client(key)
    return _action(key, username, "user.disable", lambda: client.set_enabled(username, False), "Cont dezactivat.")


@bp.post("/<key>/users/<username>/reset-password")
@login_required
def reset_password(key: str, username: str):
    client = _client(key)
    _validate_username(username)
    if not ConfirmForm().validate_on_submit():
        abort(400)
    new_password = generate_password()
    try:
        client.reset_password(username, new_password)
    except PlatformError as exc:
        audit.record(key, "user.reset_password", target=username, outcome="error", details=str(exc))
        flash(str(exc), "danger")
        return redirect(url_for("platforms.user_detail", key=key, username=username))
    audit.record(key, "user.reset_password", target=username)
    return render_template("platforms/password_reset.html", client=client, username=username, shown_password=new_password)


@bp.post("/<key>/users/<username>/delete")
@login_required
def delete_user(key: str, username: str):
    client = _client(key)
    _validate_username(username)
    if not ConfirmForm().validate_on_submit():
        abort(400)
    if request.form.get("confirm_username", "") != username:
        flash("Confirmarea nu corespunde cu numele utilizatorului. Nimic nu a fost șters.", "danger")
        return redirect(url_for("platforms.user_detail", key=key, username=username))
    try:
        client.delete_user(username)
    except PlatformError as exc:
        audit.record(key, "user.delete", target=username, outcome="error", details=str(exc))
        flash(str(exc), "danger")
        return redirect(url_for("platforms.user_detail", key=key, username=username))
    audit.record(key, "user.delete", target=username)
    flash(f"Utilizatorul {username} a fost șters din {client.label}.", "success")
    return redirect(url_for("platforms.users", key=key))


@bp.get("/<key>/health")
@login_required
def health(key: str):
    client = _client(key)
    try:
        client.health()
    except PlatformError as exc:
        return {"platform": key, "ok": False, "error": str(exc)}, 502
    return {"platform": key, "ok": True}
