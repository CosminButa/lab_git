"""Contract tests for the three API clients against mocked HTTP."""
import pytest
import requests_mock as rm

from app.platforms.base import NotFound, PlatformError
from app.platforms.jira import JiraClient
from app.platforms.keycloak import KeycloakClient
from app.platforms.nextcloud import NextcloudClient

KC = "https://kc.example"
JIRA = "https://jira.example"
NC = "https://nc.example"


@pytest.fixture
def m():
    with rm.Mocker() as mock:
        yield mock


# ---------------- Keycloak ----------------
def _kc(m):
    m.post(f"{KC}/realms/r/protocol/openid-connect/token", json={"access_token": "tok", "expires_in": 300})
    return KeycloakClient(KC, realm="r", client_id="c", client_secret="s")


def test_keycloak_token_and_search(m):
    c = _kc(m)
    m.get(f"{KC}/admin/realms/r/users", json=[{"id": "u1", "username": "jdoe", "email": "j@x", "firstName": "J", "lastName": "D", "enabled": True}])
    users = c.search_users("jd")
    assert users[0].username == "jdoe" and users[0].display_name == "J D"
    assert m.request_history[-1].headers["Authorization"] == "Bearer tok"
    assert "search=jd" in m.request_history[-1].query
    # token is cached
    c.search_users("x")
    assert sum(1 for r in m.request_history if r.path.endswith("/token")) == 1


def test_keycloak_get_user_with_groups_and_group_ops(m):
    c = _kc(m)
    m.get(f"{KC}/admin/realms/r/users?username=jdoe&exact=true&max=2", json=[{"id": "u1", "username": "jdoe", "enabled": True}])
    m.get(f"{KC}/admin/realms/r/users/u1/groups", json=[{"id": "g1", "name": "dev", "path": "/dev"}])
    user = c.get_user("jdoe")
    assert user.groups[0].name == "/dev"
    m.put(f"{KC}/admin/realms/r/users/u1/groups/g2", status_code=204)
    c.add_to_group("jdoe", "g2")
    m.delete(f"{KC}/admin/realms/r/users/u1/groups/g1", status_code=204)
    c.remove_from_group("jdoe", "g1")
    m.put(f"{KC}/admin/realms/r/users/u1", status_code=204)
    c.set_enabled("jdoe", False)
    assert m.request_history[-1].json() == {"enabled": False}


def test_keycloak_create_user_sets_temporary_password(m):
    c = _kc(m)
    m.post(f"{KC}/admin/realms/r/users", status_code=201)
    m.get(f"{KC}/admin/realms/r/users?username=jdoe&exact=true&max=2", json=[{"id": "u1", "username": "jdoe", "enabled": True}])
    m.get(f"{KC}/admin/realms/r/users/u1/groups", json=[])
    c.create_user("jdoe", "j@x", "J", "D", "Secret12345!")
    body = m.request_history[1].json()
    assert body["credentials"] == [{"type": "password", "value": "Secret12345!", "temporary": True}]


def test_keycloak_nested_groups_are_flattened(m):
    c = _kc(m)
    m.get(f"{KC}/admin/realms/r/groups", json=[{"id": "g1", "name": "a", "path": "/a", "subGroups": [{"id": "g2", "name": "b", "path": "/a/b"}]}])
    assert [g.name for g in c.list_groups()] == ["/a", "/a/b"]


def test_keycloak_bad_credentials(m):
    m.post(f"{KC}/realms/r/protocol/openid-connect/token", status_code=401, json={"error": "unauthorized_client"})
    c = KeycloakClient(KC, realm="r", client_id="c", client_secret="s")
    with pytest.raises(PlatformError, match="client id/secret"):
        c.health()


def test_keycloak_missing_user(m):
    c = _kc(m)
    m.get(f"{KC}/admin/realms/r/users?username=ghost&exact=true&max=2", json=[])
    with pytest.raises(NotFound):
        c.get_user("ghost")


# ---------------- Jira ----------------
def test_jira_get_user_and_groups(m):
    c = JiraClient(JIRA, token="pat")
    m.get(
        f"{JIRA}/rest/api/2/user",
        json={"key": "JIRAUSER1", "name": "jdoe", "emailAddress": "j@x", "displayName": "John", "active": True, "groups": {"items": [{"name": "jira-users"}]}},
    )
    user = c.get_user("jdoe")
    assert user.groups[0].id == "jira-users"
    assert m.request_history[-1].headers["Authorization"] == "Bearer pat"
    m.post(f"{JIRA}/rest/api/2/group/user", status_code=201, json={})
    c.add_to_group("jdoe", "dev")
    assert "groupname=dev" in m.request_history[-1].query and m.request_history[-1].json() == {"name": "jdoe"}
    m.delete(f"{JIRA}/rest/api/2/group/user", status_code=200)
    c.remove_from_group("jdoe", "dev")
    assert "username=jdoe" in m.request_history[-1].query


def test_jira_create_without_password_sends_notification(m):
    c = JiraClient(JIRA, token="pat")
    m.post(f"{JIRA}/rest/api/2/user", status_code=201, json={})
    m.get(f"{JIRA}/rest/api/2/user", json={"name": "jdoe", "active": True})
    c.create_user("jdoe", "j@x", "John", "Doe", None)
    body = m.request_history[0].json()
    assert body["notification"] is True and "password" not in body and body["displayName"] == "John Doe"


def test_jira_error_message_extracted(m):
    c = JiraClient(JIRA, token="pat")
    m.post(f"{JIRA}/rest/api/2/user", status_code=400, json={"errorMessages": [], "errors": {"username": "A user with that username already exists."}})
    with pytest.raises(PlatformError, match="already exists"):
        c.create_user("jdoe", "j@x", "", "", "x")


def test_jira_forbidden(m):
    c = JiraClient(JIRA, token="pat")
    m.get(f"{JIRA}/rest/api/2/myself", status_code=403)
    with pytest.raises(PlatformError, match="acces refuzat"):
        c.health()


def test_jira_groups_picker(m):
    c = JiraClient(JIRA, token="pat")
    m.get(f"{JIRA}/rest/api/2/groups/picker", json={"groups": [{"name": "a"}, {"name": "b"}]})
    assert [g.id for g in c.list_groups()] == ["a", "b"]


# ---------------- Nextcloud ----------------
def _ocs(data, code=100, message="OK"):
    return {"ocs": {"meta": {"status": "ok" if code == 100 else "failure", "statuscode": code, "message": message}, "data": data}}


def test_nextcloud_get_user(m):
    c = NextcloudClient(NC, username="admin", app_password="app-pw")
    m.get(f"{NC}/ocs/v1.php/cloud/users/jdoe", json=_ocs({"id": "jdoe", "email": "j@x", "displayname": "John", "enabled": True, "groups": ["admin", "dev"]}))
    user = c.get_user("jdoe")
    assert [g.id for g in user.groups] == ["admin", "dev"]
    req = m.request_history[-1]
    assert req.headers["OCS-APIRequest"] == "true" and "format=json" in req.query
    assert req.headers["Authorization"].startswith("Basic ")


def test_nextcloud_search_fetches_details(m):
    c = NextcloudClient(NC, username="admin", app_password="app-pw")
    m.get(f"{NC}/ocs/v1.php/cloud/users?search=j&limit=50&format=json", json=_ocs({"users": ["jdoe"]}))
    m.get(f"{NC}/ocs/v1.php/cloud/users/jdoe", json=_ocs({"id": "jdoe", "enabled": False}))
    users = c.search_users("j")
    assert users[0].username == "jdoe" and users[0].enabled is False


def test_nextcloud_ocs_failure_code(m):
    c = NextcloudClient(NC, username="admin", app_password="app-pw")
    m.post(f"{NC}/ocs/v1.php/cloud/users", json=_ocs([], code=102, message="User already exists"))
    with pytest.raises(PlatformError, match="User already exists"):
        c.create_user("jdoe", "", "", "", "Secret12345!")
    m.get(f"{NC}/ocs/v1.php/cloud/users/ghost", json=_ocs([], code=404, message="User does not exist"))
    with pytest.raises(NotFound):
        c.get_user("ghost")


def test_nextcloud_group_and_enable_ops(m):
    c = NextcloudClient(NC, username="admin", app_password="app-pw")
    m.post(f"{NC}/ocs/v1.php/cloud/users/jdoe/groups", json=_ocs([]))
    c.add_to_group("jdoe", "dev")
    assert m.request_history[-1].text == "groupid=dev"
    m.delete(f"{NC}/ocs/v1.php/cloud/users/jdoe/groups", json=_ocs([]))
    c.remove_from_group("jdoe", "dev")
    m.put(f"{NC}/ocs/v1.php/cloud/users/jdoe/disable", json=_ocs([]))
    c.set_enabled("jdoe", False)
    m.put(f"{NC}/ocs/v1.php/cloud/users/jdoe", json=_ocs([]))
    c.reset_password("jdoe", "NewSecret123!")
    assert "key=password" in m.request_history[-1].text
