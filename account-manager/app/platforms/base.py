"""Common interface implemented by every managed platform."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

import requests

log = logging.getLogger(__name__)


class PlatformError(Exception):
    """Raised for any failure talking to a platform. The message is safe to show to operators."""


class NotFound(PlatformError):
    pass


@dataclass
class PlatformUser:
    username: str
    email: str = ""
    display_name: str = ""
    enabled: bool = True
    id: str = ""  # platform-internal identifier when it differs from the username
    groups: list[Group] = field(default_factory=list)


@dataclass(frozen=True)
class Group:
    id: str
    name: str


class PlatformClient:
    key: str = ""
    label: str = ""
    # Which optional operations the platform supports; drives the UI.
    capabilities: frozenset[str] = frozenset({"disable", "delete", "reset_password"})
    # Whether a password is mandatory when creating a user.
    password_required: bool = True

    def __init__(self, base_url: str, timeout: int = 15, verify: bool = True):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.session = requests.Session()
        self.session.verify = verify
        self.session.headers["User-Agent"] = "account-manager/1.0"

    # -- HTTP -------------------------------------------------------------
    def _request(self, method: str, path: str, **kwargs) -> requests.Response:
        url = path if path.startswith("http") else f"{self.base_url}{path}"
        kwargs.setdefault("timeout", self.timeout)
        try:
            response = self.session.request(method, url, **kwargs)
        except requests.exceptions.SSLError as exc:
            raise PlatformError(f"{self.label}: eroare TLS la conectare.") from exc
        except requests.exceptions.ConnectionError as exc:
            raise PlatformError(f"{self.label}: nu s-a putut stabili conexiunea.") from exc
        except requests.exceptions.Timeout as exc:
            raise PlatformError(f"{self.label}: timpul de așteptare a expirat.") from exc
        except requests.RequestException as exc:
            raise PlatformError(f"{self.label}: eroare de comunicare.") from exc
        if response.status_code == 404:
            raise NotFound(f"{self.label}: resursa nu a fost găsită.")
        if response.status_code in (401, 403):
            log.error("%s rejected credentials for %s %s (%s)", self.label, method, path, response.status_code)
            raise PlatformError(f"{self.label}: acces refuzat de platformă. Verifică credențialele configurate.")
        if response.status_code >= 400:
            raise PlatformError(f"{self.label}: {self._error_message(response)}")
        return response

    def _error_message(self, response: requests.Response) -> str:
        """Best-effort extraction of a human-readable error; truncated so pages stay tidy."""
        text = ""
        try:
            data = response.json()
            if isinstance(data, dict):
                for key in ("errorMessages", "errorMessage", "error_description", "error", "message"):
                    value = data.get(key)
                    if value:
                        text = " ".join(value) if isinstance(value, list) else str(value)
                        break
                if not text and isinstance(data.get("errors"), dict):
                    text = "; ".join(f"{k}: {v}" for k, v in data["errors"].items())
        except ValueError:
            pass
        text = text or response.reason or "eroare necunoscută"
        return f"HTTP {response.status_code} - {text[:300]}"

    # -- Interface --------------------------------------------------------
    def health(self) -> None:
        raise NotImplementedError

    def search_users(self, query: str, limit: int = 50) -> list[PlatformUser]:
        raise NotImplementedError

    def get_user(self, username: str) -> PlatformUser:
        raise NotImplementedError

    def create_user(self, username: str, email: str, first_name: str, last_name: str, password: str | None) -> PlatformUser:
        raise NotImplementedError

    def set_enabled(self, username: str, enabled: bool) -> None:
        raise NotImplementedError

    def delete_user(self, username: str) -> None:
        raise NotImplementedError

    def reset_password(self, username: str, password: str) -> None:
        raise NotImplementedError

    def list_groups(self, query: str = "") -> list[Group]:
        raise NotImplementedError

    def add_to_group(self, username: str, group_id: str) -> None:
        raise NotImplementedError

    def remove_from_group(self, username: str, group_id: str) -> None:
        raise NotImplementedError
