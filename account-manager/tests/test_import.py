from app.platforms import provisioning
from app.platforms.provisioning import EXISTS, OK, parse_csv

CSV = """username,email,first_name,last_name,groups
jdoe,j@example.com,John,Doe,g1|g2
existing,,,,g1
noone,,,,
bad user,x@example.com,,,
dup,,,,
dup,,,,
,,,,
"""


def test_parse_csv_rows_and_validation():
    rows = parse_csv(CSV, max_rows=100)
    assert [r.username for r in rows] == ["jdoe", "existing", "noone", "bad user", "dup", "dup"]
    assert rows[0].groups == ["g1", "g2"] and rows[0].email == "j@example.com"
    assert rows[2].groups == [] and rows[2].error == ""
    assert "invalid" in rows[3].error


def test_parse_csv_semicolon_bom_and_limit():
    rows = parse_csv("﻿Username;Groups\na;g1\nb;g2\nc;\n", max_rows=2)
    assert [r.username for r in rows[:2]] == ["a", "b"] and rows[0].groups == ["g1"]
    assert "limita" in rows[2].error


def test_parse_csv_missing_header():
    rows = parse_csv("name,email\nx,y\n", max_rows=10)
    assert len(rows) == 1 and "username" in rows[0].error


def test_import_rows(fake):
    fake.create_user("existing", "", "", "", "x")
    reports = provisioning.import_rows(fake, parse_csv(CSV, 100), with_password=True)
    by_name = {r.username: r for r in reports}
    assert by_name["jdoe"].created and by_name["jdoe"].password and [g.id for g in fake.users["jdoe"].groups] == ["g1", "g2"]
    assert not by_name["existing"].created and by_name["existing"].password is None
    assert ("Creare utilizator", EXISTS) in [(s.name, s.status) for s in by_name["existing"].steps]
    assert [g.id for g in fake.users["existing"].groups] == ["g1"]
    assert by_name["noone"].created and fake.users["noone"].groups == []  # no group column -> no membership
    assert by_name["bad user"].has_errors and by_name["bad user"].steps[0].name == "Validare"
    dups = [r for r in reports if r.username == "dup"]
    assert dups[0].created and dups[1].has_errors and "de mai multe ori" in dups[1].steps[0].message
    assert "dup" in fake.users and len(fake.users) == 4


def test_import_without_password(fake):
    fake.password_required = False
    reports = provisioning.import_rows(fake, parse_csv("username\nnp\n", 10), with_password=False)
    assert reports[0].created and reports[0].password is None and fake.last_password is None


def test_import_route(app, operator_client, fake):
    from io import BytesIO

    from app.models import AuditLog

    r = operator_client.get("/p/fake/users/import")
    assert r.status_code == 200 and "username,email,first_name,last_name,groups" in r.get_data(as_text=True)
    data = {"file": (BytesIO(CSV.encode()), "users.csv"), "generate_password": "y"}
    r = operator_client.post("/p/fake/users/import", data=data, content_type="multipart/form-data")
    page = r.get_data(as_text=True)
    assert r.status_code == 200
    assert "4 utilizatori creați" in page and "2 cu erori" in page
    assert "jdoe" in page and "Grupul 'g1'" not in page
    with app.app_context():
        assert AuditLog.query.filter_by(action="user.import").count() == 6


def test_import_route_rejects_non_utf8_and_missing_password(operator_client, fake):
    from io import BytesIO

    r = operator_client.post(
        "/p/fake/users/import", data={"file": (BytesIO(b"\xff\xfe"), "u.csv"), "generate_password": "y"}, content_type="multipart/form-data"
    )
    assert r.status_code == 400 and "UTF-8" in r.get_data(as_text=True)
    r = operator_client.post("/p/fake/users/import", data={"file": (BytesIO(b"username\na\n"), "u.csv")}, content_type="multipart/form-data")
    assert r.status_code == 400 and "a" not in fake.users


def test_cli_import(app, fake, tmp_path):
    path = tmp_path / "u.csv"
    path.write_text("username,groups\ncli1,g1\ncli2,nope\n", encoding="utf-8")
    result = app.test_cli_runner().invoke(args=["import-users", "keycloak", str(path)])
    assert result.exit_code == 1 and "nu este configurată" in result.output  # keycloak not configured in tests
    app.extensions["platforms"].register(type("K", (type(fake),), {"key": "keycloak"})())
    k = app.extensions["platforms"].get("keycloak")
    result = app.test_cli_runner().invoke(args=["import-users", "keycloak", str(path)])
    assert result.exit_code == 1  # cli2 -> group 'nope' missing
    assert "[OK]     Grup g1" in result.output and "[EROARE] Grup nope" in result.output
    assert "2 creati, 1 cu erori" in result.output and set(k.users) == {"cli1", "cli2"}


def test_reset_password_report(fake):
    report = provisioning.reset_password(fake, "ghost")
    assert report.has_errors and report.password is None
    fake.create_user("jdoe", "", "", "", "x")
    report = provisioning.reset_password(fake, "jdoe")
    assert not report.has_errors and report.password == fake.last_password
    assert [(s.name, s.status) for s in report.steps] == [("Verificare utilizator", OK), ("Resetare parolă", OK)]
