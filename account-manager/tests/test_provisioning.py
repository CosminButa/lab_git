from app.platforms import provisioning
from app.platforms.base import PlatformUser
from app.platforms.provisioning import ERROR, EXISTS, OK, SKIPPED


def statuses(report):
    return [(s.name, s.status) for s in report.steps]


def test_create_and_verify_with_groups(fake):
    report = provisioning.provision_user(fake, "jdoe", "j@x", "John", "Doe", "Secret12345!", ["g1", "g2"])
    assert not report.has_errors and report.created
    assert statuses(report) == [
        ("Conexiune", OK),
        ("Creare utilizator", OK),
        ("Verificare utilizator", OK),
        ("Grup g1", OK),
        ("Grup g2", OK),
    ]
    assert [g.id for g in fake.users["jdoe"].groups] == ["g1", "g2"]


def test_existing_user_is_not_recreated(fake):
    fake.create_user("jdoe", "", "", "", "x")
    fake.last_password = None
    report = provisioning.provision_user(fake, "jdoe", "", "", "", "Secret12345!", ["g1"])
    assert not report.has_errors and not report.created
    assert ("Creare utilizator", EXISTS) in statuses(report)
    assert ("Grup g1", OK) in statuses(report)
    assert fake.last_password is None  # no password was set on the existing account


def test_missing_group_reported(fake):
    report = provisioning.provision_user(fake, "jdoe", "", "", "", "Secret12345!", ["nope", "g1"])
    assert report.has_errors and report.created
    assert ("Grup nope", ERROR) in statuses(report)
    assert ("Grup g1", OK) in statuses(report)
    assert "nu există" in next(s.message for s in report.steps if s.name == "Grup nope")


def test_already_member_reported(fake):
    fake.create_user("jdoe", "", "", "", "x")
    fake.add_to_group("jdoe", "g1")
    report = provisioning.assign_group(fake, "jdoe", "g1")
    assert statuses(report) == [("Verificare utilizator", OK), ("Grup g1", EXISTS)]


def test_assign_group_to_missing_user(fake):
    report = provisioning.assign_group(fake, "ghost", "g1")
    assert report.has_errors
    assert statuses(report) == [("Verificare utilizator", ERROR), ("Grup g1", SKIPPED)]
    assert "nu există" in report.steps[0].message


def test_platform_down_skips_everything(fake):
    fake.fail_next = "Fake: down"
    report = provisioning.provision_user(fake, "jdoe", "", "", "", "Secret12345!", ["g1"])
    assert statuses(report) == [("Conexiune", ERROR), ("Creare utilizator", SKIPPED), ("Grup g1", SKIPPED)]
    assert "jdoe" not in fake.users


def test_create_failure_skips_groups(fake):
    fake.fail_after_health = "Fake: quota"
    report = provisioning.provision_user(fake, "jdoe", "", "", "", "Secret12345!", ["g1"])
    assert ("Creare utilizator", ERROR) in statuses(report) or ("Verificare utilizator", ERROR) in statuses(report)
    assert ("Grup g1", SKIPPED) in statuses(report)


def test_membership_verified_after_add(fake):
    fake.create_user("jdoe", "", "", "", "x")
    fake.silent_group_add = True  # platform says OK but does nothing
    report = provisioning.assign_group(fake, "jdoe", "g1")
    assert report.has_errors
    assert "nu apare" in report.steps[-1].message


def test_group_cache_and_refresh(fake):
    assert fake.find_group("g1").name == "Group One"
    fake.groups.append(fake.groups[0].__class__("g3", "Group Three"))
    # cache is stale but find_group refreshes once before giving up
    assert fake.find_group("g3").name == "Group Three"
    assert fake.find_group("nope") is None
