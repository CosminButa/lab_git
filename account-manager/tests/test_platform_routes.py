import html

from app.models import AuditLog


def test_unknown_platform_404(operator_client):
    assert operator_client.get("/p/nope/").status_code == 404


def test_create_user_generates_password_and_audits(app, operator_client, fake):
    r = operator_client.post(
        "/p/fake/users/new",
        data={"username": "jdoe", "email": "j@example.com", "first_name": "John", "last_name": "Doe", "generate_password": "y"},
    )
    assert r.status_code == 200
    page = r.get_data(as_text=True)
    assert "a fost creat și verificat" in page
    assert html.escape(fake.last_password) in page
    assert len(fake.last_password) >= 16
    with app.app_context():
        entry = AuditLog.query.filter_by(platform="fake", action="user.provision").one()
        assert entry.operator == "op" and entry.target == "jdoe" and entry.outcome == "ok"
        assert fake.last_password not in entry.details


def test_create_user_requires_password_when_platform_demands(operator_client, fake):
    r = operator_client.post("/p/fake/users/new", data={"username": "jdoe", "email": "j@example.com"})
    assert r.status_code == 400
    assert "jdoe" not in fake.users


def test_create_user_platform_error_is_shown_and_audited(app, operator_client, fake):
    fake.fail_next = "Fake: platforma e jos"
    r = operator_client.post("/p/fake/users/new", data={"username": "jdoe", "generate_password": "y"})
    assert r.status_code == 502
    page = r.get_data(as_text=True)
    assert "platforma e jos" in page and 'class="secret"' not in page
    with app.app_context():
        assert AuditLog.query.filter_by(action="user.provision", outcome="error").count() == 1


def test_create_with_groups_and_existing_user(app, operator_client, fake):
    fake.create_user("jdoe", "", "", "", "x")
    r = operator_client.post("/p/fake/users/new", data={"username": "jdoe", "generate_password": "y", "groups": ["g1", "g2"]})
    assert r.status_code == 200
    page = r.get_data(as_text=True)
    assert "există deja" in page and 'class="secret"' not in page
    assert [g.id for g in fake.users["jdoe"].groups] == ["g1", "g2"]


def test_username_validation(operator_client):
    r = operator_client.post("/p/fake/users/new", data={"username": "bad user!", "generate_password": "y"})
    assert r.status_code == 200 and "Litere, cifre" in r.get_data(as_text=True)
    assert operator_client.get("/p/fake/users/bad%20name%21").status_code == 400


def test_group_membership_flow(operator_client, fake):
    fake.create_user("jdoe", "j@example.com", "John", "Doe", "Password12345!")
    r = operator_client.post("/p/fake/users/jdoe/groups/add", data={"group_id": "g1"})
    assert r.status_code == 200 and "adăugat și verificat" in r.get_data(as_text=True)
    assert [g.id for g in fake.users["jdoe"].groups] == ["g1"]
    detail = operator_client.get("/p/fake/users/jdoe").get_data(as_text=True)
    assert "Group One" in detail
    assert '<option value="g1"' not in detail  # already a member, not offered again
    r = operator_client.post("/p/fake/users/jdoe/groups/remove", data={"group_id": "g1"}, follow_redirects=True)
    assert "scos din grup" in r.get_data(as_text=True)
    assert fake.users["jdoe"].groups == []


def test_add_to_unknown_group_rejected(operator_client, fake):
    fake.create_user("jdoe", "", "", "", "Password12345!")
    r = operator_client.post("/p/fake/users/jdoe/groups/add", data={"group_id": "nope"}, follow_redirects=True)
    assert "Grup invalid" in r.get_data(as_text=True)


def test_add_group_to_missing_user_reports_error(operator_client):
    r = operator_client.post("/p/fake/users/ghost/groups/add", data={"group_id": "g1"})
    assert r.status_code == 502
    assert "nu există" in r.get_data(as_text=True)


def test_disable_enable_reset_delete(operator_client, fake):
    fake.create_user("jdoe", "", "", "", "Password12345!")
    assert "dezactivat" in operator_client.post("/p/fake/users/jdoe/disable", follow_redirects=True).get_data(as_text=True)
    assert fake.users["jdoe"].enabled is False
    assert "activat" in operator_client.post("/p/fake/users/jdoe/enable", follow_redirects=True).get_data(as_text=True)
    assert fake.users["jdoe"].enabled is True
    r = operator_client.post("/p/fake/users/jdoe/reset-password")
    assert r.status_code == 200 and html.escape(fake.last_password) in r.get_data(as_text=True)
    # delete needs the username typed back
    r = operator_client.post("/p/fake/users/jdoe/delete", data={"confirm_username": "wrong"}, follow_redirects=True)
    assert "Nimic nu a fost șters" in r.get_data(as_text=True) and "jdoe" in fake.users
    r = operator_client.post("/p/fake/users/jdoe/delete", data={"confirm_username": "jdoe"}, follow_redirects=True)
    assert "a fost șters" in r.get_data(as_text=True) and "jdoe" not in fake.users


def test_search_and_missing_user(operator_client, fake):
    fake.create_user("jdoe", "", "", "", "Password12345!")
    r = operator_client.get("/p/fake/?q=jd")
    assert "jdoe" in r.get_data(as_text=True)
    r = operator_client.get("/p/fake/users/ghost", follow_redirects=True)
    assert "nu există" in r.get_data(as_text=True)


def test_health_endpoint(operator_client, fake):
    assert operator_client.get("/p/fake/health").json["ok"] is True
    fake.fail_next = "Fake: down"
    r = operator_client.get("/p/fake/health")
    assert r.status_code == 502 and r.json["ok"] is False
