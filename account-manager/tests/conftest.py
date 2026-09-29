import pytest

from app import create_app
from app.config import TestConfig
from app.extensions import db
from app.models import ROLE_ADMIN, ROLE_OPERATOR, Operator
from app.platforms import Registry
from app.platforms.base import Group, NotFound, PlatformClient, PlatformError, PlatformUser


class FakeClient(PlatformClient):
    """In-memory platform used to exercise the generic routes."""

    key = "fake"
    label = "Fake"
    password_required = True

    def __init__(self):
        super().__init__("https://fake.example", min_interval=0)
        self.users: dict[str, PlatformUser] = {}
        self.groups = [Group("g1", "Group One"), Group("g2", "Group Two")]
        self.fail_next: str | None = None
        self.fail_after_health: str | None = None
        self.silent_group_add = False
        self.last_password = None

    def _maybe_fail(self):
        if self.fail_next:
            msg, self.fail_next = self.fail_next, None
            raise PlatformError(msg)

    def health(self):
        self._maybe_fail()
        if self.fail_after_health:
            self.fail_next, self.fail_after_health = self.fail_after_health, None

    def search_users(self, query, limit=50):
        self._maybe_fail()
        return [u for u in self.users.values() if query.lower() in u.username.lower()]

    def get_user(self, username):
        self._maybe_fail()
        if username not in self.users:
            raise NotFound("Fake: nu există")
        user = self.users[username]
        return PlatformUser(user.username, user.email, user.display_name, user.enabled, user.id, list(user.groups))

    def create_user(self, username, email, first_name, last_name, password):
        self._maybe_fail()
        if username in self.users:
            raise PlatformError("Fake: există deja")
        self.last_password = password
        user = PlatformUser(username=username, email=email, display_name=f"{first_name} {last_name}".strip())
        self.users[username] = user
        return user

    def set_enabled(self, username, enabled):
        self._maybe_fail()
        self.users[username].enabled = enabled

    def delete_user(self, username):
        self._maybe_fail()
        self.get_user(username)
        del self.users[username]

    def reset_password(self, username, password):
        self._maybe_fail()
        self.get_user(username)
        self.last_password = password

    def list_groups(self, query=""):
        return self.groups

    def add_to_group(self, username, group_id):
        self._maybe_fail()
        if self.silent_group_add:
            return
        group = next(g for g in self.groups if g.id == group_id)
        self.users[username].groups.append(group)

    def remove_from_group(self, username, group_id):
        self._maybe_fail()
        user = self.users[username]
        user.groups = [g for g in user.groups if g.id != group_id]


@pytest.fixture
def app():
    app = create_app(TestConfig)
    registry = Registry()
    registry.register(FakeClient())
    app.extensions["platforms"] = registry
    with app.app_context():
        admin = Operator(username="admin", display_name="Admin", role=ROLE_ADMIN)
        admin.set_password("AdminPassword123!")
        op = Operator(username="op", display_name="Operator", role=ROLE_OPERATOR)
        op.set_password("OperatorPassword123!")
        db.session.add_all([admin, op])
        db.session.commit()
    # Yield outside the app context so every test request gets its own context and DB session,
    # exactly as in production.
    yield app
    with app.app_context():
        db.session.remove()
        db.drop_all()


@pytest.fixture
def fake(app) -> FakeClient:
    return app.extensions["platforms"].get("fake")


@pytest.fixture
def client(app):
    return app.test_client()


def login(client, username, password):
    return client.post("/login", data={"username": username, "password": password}, follow_redirects=True)


@pytest.fixture
def admin_client(client):
    login(client, "admin", "AdminPassword123!")
    return client


@pytest.fixture
def operator_client(client):
    login(client, "op", "OperatorPassword123!")
    return client
