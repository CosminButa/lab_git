from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from .. import audit
from ..extensions import db
from ..models import ROLE_ADMIN, AuditLog, Operator
from ..security import admin_required, generate_password
from .forms import ConfirmForm, EditOperatorForm, OperatorForm

bp = Blueprint("admin", __name__, url_prefix="/admin")


@bp.get("/operators")
@login_required
@admin_required
def operators():
    items = Operator.query.order_by(Operator.username).all()
    return render_template("admin/operators.html", operators=items, confirm=ConfirmForm())


@bp.route("/operators/new", methods=["GET", "POST"])
@login_required
@admin_required
def new_operator():
    form = OperatorForm()
    if form.validate_on_submit():
        username = form.username.data.strip()
        if Operator.query.filter_by(username=username).first():
            flash("Există deja un operator cu acest nume.", "danger")
            return render_template("admin/operator_form.html", form=form, title="Operator nou"), 400
        temp_password = generate_password()
        operator = Operator(
            username=username,
            display_name=form.display_name.data.strip() or username,
            role=form.role.data,
            active=form.active.data,
            must_change_password=True,
        )
        operator.set_password(temp_password)
        db.session.add(operator)
        db.session.commit()
        audit.record("app", "operator.create", target=username, details=f"role={operator.role}")
        # The temporary password is shown exactly once and never stored in clear text.
        return render_template("admin/operator_created.html", operator=operator, temp_password=temp_password)
    return render_template("admin/operator_form.html", form=form, title="Operator nou")


@bp.route("/operators/<int:operator_id>/edit", methods=["GET", "POST"])
@login_required
@admin_required
def edit_operator(operator_id: int):
    operator = db.session.get(Operator, operator_id) or abort(404)
    form = EditOperatorForm(obj=operator)
    if form.validate_on_submit():
        if operator.id == current_user.id and (form.role.data != ROLE_ADMIN or not form.active.data):
            flash("Nu îți poți retrage propriul rol de administrator sau dezactiva propriul cont.", "danger")
            return render_template("admin/operator_form.html", form=form, title=f"Editare {operator.username}"), 400
        operator.display_name = form.display_name.data.strip() or operator.username
        operator.role = form.role.data
        if operator.active and not form.active.data:
            operator.rotate_session_token()  # kick out any live session
        operator.active = form.active.data
        db.session.commit()
        audit.record("app", "operator.update", target=operator.username, details=f"role={operator.role} active={operator.active}")
        flash("Operator actualizat.", "success")
        return redirect(url_for("admin.operators"))
    return render_template("admin/operator_form.html", form=form, title=f"Editare {operator.username}")


@bp.post("/operators/<int:operator_id>/reset-password")
@login_required
@admin_required
def reset_operator_password(operator_id: int):
    form = ConfirmForm()
    if not form.validate_on_submit():
        abort(400)
    operator = db.session.get(Operator, operator_id) or abort(404)
    temp_password = generate_password()
    operator.set_password(temp_password)
    operator.must_change_password = True
    operator.locked_until = None
    operator.failed_logins = 0
    db.session.commit()
    audit.record("app", "operator.reset_password", target=operator.username)
    return render_template("admin/operator_created.html", operator=operator, temp_password=temp_password, reset=True)


@bp.post("/operators/<int:operator_id>/delete")
@login_required
@admin_required
def delete_operator(operator_id: int):
    form = ConfirmForm()
    if not form.validate_on_submit():
        abort(400)
    operator = db.session.get(Operator, operator_id) or abort(404)
    if operator.id == current_user.id:
        flash("Nu îți poți șterge propriul cont.", "danger")
        return redirect(url_for("admin.operators"))
    username = operator.username
    db.session.delete(operator)
    db.session.commit()
    audit.record("app", "operator.delete", target=username)
    flash(f"Operatorul {username} a fost șters.", "success")
    return redirect(url_for("admin.operators"))


@bp.get("/audit")
@login_required
@admin_required
def audit_log():
    page = max(request.args.get("page", 1, type=int), 1)
    per_page = 50
    query = AuditLog.query.order_by(AuditLog.ts.desc())
    platform = request.args.get("platform", "").strip()
    if platform:
        query = query.filter(AuditLog.platform == platform)
    entries = query.offset((page - 1) * per_page).limit(per_page + 1).all()
    has_next = len(entries) > per_page
    return render_template(
        "admin/audit.html", entries=entries[:per_page], page=page, has_next=has_next, platform=platform
    )
