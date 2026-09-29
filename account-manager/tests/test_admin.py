from app.models import AuditLog, Operator


def test_operator_cannot_access_admin_pages(operator_client):
    assert operator_client.get("/admin/operators").status_code == 403
    assert operator_client.get("/admin/audit").status_code == 403


def test_admin_creates_operator_with_temp_password(app, admin_client):
    r = admin_client.post(
        "/admin/operators/new",
        data={"username": "newop", "display_name": "New Op", "role": "operator", "active": "y"},
    )
    assert r.status_code == 200
    html = r.get_data(as_text=True)
    assert "Operator creat" in html and 'class="secret"' in html
    with app.app_context():
        op = Operator.query.filter_by(username="newop").first()
        assert op is not None and op.must_change_password
        assert AuditLog.query.filter_by(action="operator.create", target="newop", outcome="ok").count() == 1


def test_admin_cannot_demote_self(app, admin_client):
    with app.app_context():
        admin_id = Operator.query.filter_by(username="admin").first().id
    r = admin_client.post(f"/admin/operators/{admin_id}/edit", data={"display_name": "x", "role": "operator", "active": "y"})
    assert r.status_code == 400
    with app.app_context():
        assert Operator.query.get(admin_id).is_admin


def test_deactivating_operator_kills_session(app, admin_client):
    op_client = app.test_client()
    op_client.post("/login", data={"username": "op", "password": "OperatorPassword123!"})
    assert op_client.get("/").status_code == 200
    with app.app_context():
        op_id = Operator.query.filter_by(username="op").first().id
    admin_client.post(f"/admin/operators/{op_id}/edit", data={"display_name": "Operator", "role": "operator"})
    assert op_client.get("/").status_code == 302


def test_delete_operator(app, admin_client):
    with app.app_context():
        op_id = Operator.query.filter_by(username="op").first().id
    r = admin_client.post(f"/admin/operators/{op_id}/delete", follow_redirects=True)
    assert "a fost șters" in r.get_data(as_text=True)
    with app.app_context():
        assert Operator.query.filter_by(username="op").first() is None


def test_audit_page_lists_entries(admin_client):
    r = admin_client.get("/admin/audit")
    assert r.status_code == 200
    assert "login" in r.get_data(as_text=True)
