"""Keycloak Admin REST API client using a confidential client's service account.

Required realm-management roles on the service account: view-users, manage-users, query-groups.
"""
from __future__ import annotations

import time

from .base import Group, NotFound, PlatformClient, PlatformError, PlatformUser


class KeycloakClient(PlatformClient):
    key = "keycloak"
    label = "Keycloak"
    password_required = False  # Keycloak users can be created without credentials

    def __init__(self, base_url, realm, client_id, client_secret, auth_realm=None, **kwargs):
        super().__init__(base_url, **kwargs)
        self.realm = realm
        self.auth_realm = auth_realm or realm
        self.client_id = client_id
        self.client_secret = client_secret
        self._token: str | None = None
        self._token_expiry = 0.0

    # -- auth -------------------------------------------------------------
    def _ensure_token(self) -> None:
        if self._token and time.monotonic() < self._token_expiry:
            return
        url = f"{self.base_url}/realms/{self.auth_realm}/protocol/openid-connect/token"
        try:
            response = self.session.post(
                url,
                data={"grant_type": "client_credentials", "client_id": self.client_id, "client_secret": self.client_secret},
                timeout=self.timeout,
            )
        except Exception as exc:  # noqa: BLE001 - normalised below
            raise PlatformError("Keycloak: nu s-a putut obține token-ul de administrare.") from exc
        if response.status_code != 200:
            raise PlatformError("Keycloak: autentificarea clientului de serviciu a eșuat. Verifică client id/secret.")
        data = response.json()
        self._token = data["access_token"]
        self._token_expiry = time.monotonic() + max(int(data.get("expires_in", 60)) - 10, 5)

    def _admin(self, method: str, path: str, **kwargs):
        self._ensure_token()
        headers = kwargs.pop("headers", {})
        headers["Authorization"] = f"Bearer {self._token}"
        return self._request(method, f"/admin/realms/{self.realm}{path}", headers=headers, **kwargs)

    # -- helpers ----------------------------------------------------------
    @staticmethod
    def _to_user(data: dict) -> PlatformUser:
        name = " ".join(p for p in (data.get("firstName"), data.get("lastName")) if p)
        return PlatformUser(
            id=data.get("id", ""),
            username=data.get("username", ""),
            email=data.get("email") or "",
            display_name=name,
            enabled=bool(data.get("enabled", True)),
        )

    def _find(self, username: str) -> dict:
        response = self._admin("GET", "/users", params={"username": username, "exact": "true", "max": 2})
        for item in response.json():
            if item.get("username", "").lower() == username.lower():
                return item
        raise NotFound(f"Keycloak: utilizatorul '{username}' nu există.")

    @staticmethod
    def _flatten_groups(groups: list[dict], out: list[Group]) -> list[Group]:
        for g in groups:
            out.append(Group(id=g["id"], name=g.get("path") or g.get("name", "")))
            if g.get("subGroups"):
                KeycloakClient._flatten_groups(g["subGroups"], out)
        return out

    # -- interface --------------------------------------------------------
    def health(self) -> None:
        self._admin("GET", "/users/count")

    def search_users(self, query: str, limit: int = 50) -> list[PlatformUser]:
        params = {"max": limit, "briefRepresentation": "true"}
        if query:
            params["search"] = query
        return [self._to_user(u) for u in self._admin("GET", "/users", params=params).json()]

    def get_user(self, username: str) -> PlatformUser:
        raw = self._find(username)
        user = self._to_user(raw)
        groups = self._admin("GET", f"/users/{raw['id']}/groups", params={"briefRepresentation": "true"}).json()
        user.groups = [Group(id=g["id"], name=g.get("path") or g.get("name", "")) for g in groups]
        return user

    def create_user(self, username, email, first_name, last_name, password) -> PlatformUser:
        payload = {
            "username": username,
            "email": email or None,
            "firstName": first_name or None,
            "lastName": last_name or None,
            "enabled": True,
            "emailVerified": False,
        }
        if password:
            payload["credentials"] = [{"type": "password", "value": password, "temporary": True}]
        payload = {k: v for k, v in payload.items() if v is not None}
        self._admin("POST", "/users", json=payload)
        return self.get_user(username)

    def set_enabled(self, username: str, enabled: bool) -> None:
        raw = self._find(username)
        self._admin("PUT", f"/users/{raw['id']}", json={"enabled": enabled})

    def delete_user(self, username: str) -> None:
        raw = self._find(username)
        self._admin("DELETE", f"/users/{raw['id']}")

    def reset_password(self, username: str, password: str) -> None:
        raw = self._find(username)
        self._admin("PUT", f"/users/{raw['id']}/reset-password", json={"type": "password", "value": password, "temporary": True})

    def list_groups(self, query: str = "") -> list[Group]:
        params = {"max": 200}
        if query:
            params["search"] = query
        groups = self._admin("GET", "/groups", params=params).json()
        return self._flatten_groups(groups, [])

    def add_to_group(self, username: str, group_id: str) -> None:
        raw = self._find(username)
        self._admin("PUT", f"/users/{raw['id']}/groups/{group_id}")

    def remove_from_group(self, username: str, group_id: str) -> None:
        raw = self._find(username)
        self._admin("DELETE", f"/users/{raw['id']}/groups/{group_id}")
