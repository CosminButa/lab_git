from app.extensions import db
from app.models import Operator
from tests.conftest import login


def test_unauthenticated_redirects_to_login(client):
    r = client.get("/")
    assert r.status_code == 302 and "/login" in r.headers["Location"]
    r = client.get("/p/fake/")
    assert r.status_code == 302 and "/login" in r.headers["Location"]


def test_login_success_and_logout(client):
    r = login(client, "admin", "AdminPassword123!")
    assert r.status_code == 200
    assert "Platforme" in r.get_data(as_text=True)
    r = client.post("/logout", follow_redirects=True)
    assert "Autentificare" in r.get_data(as_text=True)
    assert client.get("/").status_code == 302


def test_login_wrong_password_and_unknown_user_same_message(client):
    r1 = client.post("/login", data={"username": "admin", "password": "wrong-password-xx"})
    r2 = client.post("/login", data={"username": "nobody", "password": "wrong-password-xx"})
    assert r1.status_code == 401 and r2.status_code == 401
    assert "Utilizator sau parolă incorecte" in r1.get_data(as_text=True)
    assert "Utilizator sau parolă incorecte" in r2.get_data(as_text=True)


def test_lockout_after_failures(app, client):
    for _ in range(app.config["LOGIN_MAX_FAILURES"]):
        client.post("/login", data={"username": "op", "password": "bad-password-xxx"})
    r = client.post("/login", data={"username": "op", "password": "OperatorPassword123!"})
    assert r.status_code == 423
    with app.app_context():
        assert Operator.query.filter_by(username="op").first().is_locked


def test_disabled_operator_cannot_login(app, client):
    with app.app_context():
        op = Operator.query.filter_by(username="op").first()
        op.active = False
        db.session.commit()
    r = client.post("/login", data={"username": "op", "password": "OperatorPassword123!"})
    assert r.status_code == 401


def test_must_change_password_is_enforced(app, client):
    with app.app_context():
        op = Operator.query.filter_by(username="op").first()
        op.must_change_password = True
        db.session.commit()
    login(client, "op", "OperatorPassword123!")
    r = client.get("/p/fake/")
    assert r.status_code == 302 and "/account/password" in r.headers["Location"]
    r = client.post(
        "/account/password",
        data={"current_password": "OperatorPassword123!", "new_password": "BrandNewPassword456!", "confirm": "BrandNewPassword456!"},
        follow_redirects=True,
    )
    assert "Parola a fost schimbată" in r.get_data(as_text=True)
    assert client.get("/p/fake/").status_code == 200


def test_password_change_rotates_other_sessions(app):
    c1, c2 = app.test_client(), app.test_client()
    login(c1, "op", "OperatorPassword123!")
    login(c2, "op", "OperatorPassword123!")
    c1.post(
        "/account/password",
        data={"current_password": "OperatorPassword123!", "new_password": "BrandNewPassword456!", "confirm": "BrandNewPassword456!"},
    )
    assert c1.get("/").status_code == 200
    assert c2.get("/").status_code == 302  # old session invalidated


def test_security_headers_present(client):
    r = client.get("/login")
    assert r.headers["X-Frame-Options"] == "DENY"
    assert "default-src 'self'" in r.headers["Content-Security-Policy"]
    assert r.headers["Cache-Control"] == "no-store"


def test_healthz_is_public(client):
    assert client.get("/healthz").json == {"status": "ok"}


def test_bootstrap_admin_is_idempotent_across_workers(tmp_path):
    """Two app instances (like two gunicorn workers) bootstrapping the same DB must not crash."""
    from app import create_app
    from app.config import TestConfig
    from app.models import Operator

    class Cfg(TestConfig):
        SQLALCHEMY_DATABASE_URI = f"sqlite:///{tmp_path}/boot.db"
        BOOTSTRAP_ADMIN_USERNAME = "boot"
        BOOTSTRAP_ADMIN_PASSWORD = "BootstrapPassword123!"

    a1 = create_app(Cfg)
    # Simulate the race: second instance runs the bootstrap after the first committed.
    a2 = create_app(Cfg)
    with a2.app_context():
        from app import _bootstrap_admin
        _bootstrap_admin(a2)
        assert Operator.query.filter_by(username="boot").count() == 1
    with a1.app_context():
        assert Operator.query.filter_by(username="boot").one().must_change_password
