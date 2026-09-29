"""Nextcloud OCS Provisioning API client (admin account + app password over Basic auth).

Create the app password in Nextcloud under Settings > Security > Devices & sessions.
"""
from __future__ import annotations

from .base import Group, NotFound, PlatformClient, PlatformError, PlatformUser


class NextcloudClient(PlatformClient):
    key = "nextcloud"
    label = "Nextcloud"
    password_required = True

    def __init__(self, base_url, username, app_password, **kwargs):
        super().__init__(base_url, **kwargs)
        self.session.auth = (username, app_password)
        self.session.headers["OCS-APIRequest"] = "true"
        self.session.headers["Accept"] = "application/json"

    def _ocs(self, method: str, path: str, **kwargs) -> dict:
        params = kwargs.pop("params", {})
        params["format"] = "json"
        response = self._request(method, f"/ocs/v1.php/cloud{path}", params=params, **kwargs)
        try:
            body = response.json()["ocs"]
        except (ValueError, KeyError) as exc:
            raise PlatformError("Nextcloud: răspuns neașteptat de la server.") from exc
        meta = body.get("meta", {})
        code = int(meta.get("statuscode", 0))
        if code == 100:
            return body.get("data") or {}
        if code in (404, 998):
            raise NotFound(f"Nextcloud: {meta.get('message') or 'resursa nu a fost găsită.'}")
        if code == 997:
            raise PlatformError("Nextcloud: acces refuzat de platformă. Verifică utilizatorul și app password-ul.")
        raise PlatformError(f"Nextcloud: {meta.get('message') or 'eroare'} (cod {code})")

    @staticmethod
    def _to_user(data: dict) -> PlatformUser:
        return PlatformUser(
            id=data.get("id", ""),
            username=data.get("id", ""),
            email=data.get("email") or "",
            display_name=data.get("displayname") or data.get("display-name") or "",
            enabled=bool(data.get("enabled", True)),
            groups=[Group(id=g, name=g) for g in data.get("groups") or []],
        )

    def health(self) -> None:
        self._ocs("GET", "/users", params={"limit": 1})

    def search_users(self, query: str, limit: int = 50) -> list[PlatformUser]:
        params = {"limit": limit}
        if query:
            params["search"] = query
        ids = self._ocs("GET", "/users", params=params).get("users", [])
        # The list endpoint returns only ids; fetch details for a bounded number of them.
        return [self.get_user(uid) for uid in ids[:limit]]

    def get_user(self, username: str) -> PlatformUser:
        try:
            return self._to_user(self._ocs("GET", f"/users/{username}"))
        except NotFound:
            raise NotFound(f"Nextcloud: utilizatorul '{username}' nu există.")

    def create_user(self, username, email, first_name, last_name, password) -> PlatformUser:
        display = " ".join(p for p in (first_name, last_name) if p)
        payload = {"userid": username, "password": password}
        if email:
            payload["email"] = email
        if display:
            payload["displayName"] = display
        self._ocs("POST", "/users", data=payload)
        return self.get_user(username)

    def set_enabled(self, username: str, enabled: bool) -> None:
        self._ocs("PUT", f"/users/{username}/{'enable' if enabled else 'disable'}")

    def delete_user(self, username: str) -> None:
        self._ocs("DELETE", f"/users/{username}")

    def reset_password(self, username: str, password: str) -> None:
        self._ocs("PUT", f"/users/{username}", data={"key": "password", "value": password})

    def list_groups(self, query: str = "") -> list[Group]:
        params = {"limit": 200}
        if query:
            params["search"] = query
        return [Group(id=g, name=g) for g in self._ocs("GET", "/groups", params=params).get("groups", [])]

    def add_to_group(self, username: str, group_id: str) -> None:
        self._ocs("POST", f"/users/{username}/groups", data={"groupid": group_id})

    def remove_from_group(self, username: str, group_id: str) -> None:
        self._ocs("DELETE", f"/users/{username}/groups", data={"groupid": group_id})
