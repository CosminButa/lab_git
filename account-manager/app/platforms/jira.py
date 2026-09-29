"""Jira Data Center / Server REST API v2 client authenticated with a Personal Access Token.

The token's owner needs the "Jira System Administrators" (or at least "Jira Administrators")
global permission. User deactivation via REST requires Jira 8.x+ and an internal user directory.
"""
from __future__ import annotations

from .base import Group, NotFound, PlatformClient, PlatformUser


class JiraClient(PlatformClient):
    key = "jira"
    label = "Jira"
    password_required = False  # without a password Jira e-mails an invitation (if outgoing mail is configured)

    def __init__(self, base_url, token, **kwargs):
        super().__init__(base_url, **kwargs)
        self.session.headers["Authorization"] = f"Bearer {token}"
        self.session.headers["Accept"] = "application/json"

    @staticmethod
    def _to_user(data: dict) -> PlatformUser:
        return PlatformUser(
            id=data.get("key", ""),
            username=data.get("name", ""),
            email=data.get("emailAddress") or "",
            display_name=data.get("displayName") or "",
            enabled=bool(data.get("active", True)),
        )

    def health(self) -> None:
        self._request("GET", "/rest/api/2/myself")

    def search_users(self, query: str, limit: int = 50) -> list[PlatformUser]:
        params = {"username": query or ".", "maxResults": limit, "includeInactive": "true"}
        return [self._to_user(u) for u in self._request("GET", "/rest/api/2/user/search", params=params).json()]

    def get_user(self, username: str) -> PlatformUser:
        try:
            data = self._request("GET", "/rest/api/2/user", params={"username": username, "expand": "groups"}).json()
        except NotFound:
            raise NotFound(f"Jira: utilizatorul '{username}' nu există.")
        user = self._to_user(data)
        items = (data.get("groups") or {}).get("items", [])
        user.groups = [Group(id=g["name"], name=g["name"]) for g in items]
        return user

    def create_user(self, username, email, first_name, last_name, password) -> PlatformUser:
        display = " ".join(p for p in (first_name, last_name) if p) or username
        payload = {"name": username, "emailAddress": email, "displayName": display, "notification": not password}
        if password:
            payload["password"] = password
        self._request("POST", "/rest/api/2/user", json=payload)
        return self.get_user(username)

    def set_enabled(self, username: str, enabled: bool) -> None:
        self._request("PUT", "/rest/api/2/user", params={"username": username}, json={"active": enabled})

    def delete_user(self, username: str) -> None:
        self._request("DELETE", "/rest/api/2/user", params={"username": username})

    def reset_password(self, username: str, password: str) -> None:
        self._request("PUT", "/rest/api/2/user/password", params={"username": username}, json={"password": password})

    def list_groups(self, query: str = "") -> list[Group]:
        params = {"maxResults": 200}
        if query:
            params["query"] = query
        data = self._request("GET", "/rest/api/2/groups/picker", params=params).json()
        return [Group(id=g["name"], name=g["name"]) for g in data.get("groups", [])]

    def add_to_group(self, username: str, group_id: str) -> None:
        self._request("POST", "/rest/api/2/group/user", params={"groupname": group_id}, json={"name": username})

    def remove_from_group(self, username: str, group_id: str) -> None:
        self._request("DELETE", "/rest/api/2/group/user", params={"groupname": group_id, "username": username})
