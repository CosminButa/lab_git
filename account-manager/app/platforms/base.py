"""Common interface implemented by every managed platform."""
from __future__ import annotations

import logging
import threading
import time
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

    def __init__(
        self,
        base_url: str,
        timeout: int = 15,
        verify: bool = True,
        min_interval: float = 0.2,
        max_retries: int = 3,
        group_cache_seconds: int = 60,
    ):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.session = requests.Session()
        self.session.verify = verify
        self.session.headers["User-Agent"] = "account-manager/1.0"
        # Politeness towards the platform: never fire requests faster than `min_interval`
        # seconds apart, and back off when the platform answers 429/503.
        self.min_interval = min_interval
        self.max_retries = max_retries
        self._last_request = 0.0
        self._throttle_lock = threading.Lock()
        self.group_cache_seconds = group_cache_seconds
        self._group_cache: tuple[float, list[Group]] | None = None

    # -- HTTP -------------------------------------------------------------
    def _throttle(self) -> None:
        with self._throttle_lock:
            wait = self.min_interval - (time.monotonic() - self._last_request)
            if wait > 0:
                time.sleep(wait)
            self._last_request = time.monotonic()

    @staticmethod
    def _retry_delay(response: requests.Response, attempt: int) -> float:
        header = response.headers.get("Retry-After", "")
        if header.strip().isdigit():
            return min(float(header), 30.0)
        return min(0.5 * (2**attempt), 8.0)

    def _request(self, method: str, path: str, **kwargs) -> requests.Response:
        url = path if path.startswith("http") else f"{self.base_url}{path}"
        kwargs.setdefault("timeout", self.timeout)
        try:
            attempt = 0
            while True:
                self._throttle()
                response = self.session.request(method, url, **kwargs)
                if response.status_code in (429, 503) and attempt < self.max_retries:
                    delay = self._retry_delay(response, attempt)
                    log.warning("%s answered %s for %s %s; retrying in %.1fs", self.label, response.status_code, method, path, delay)
                    time.sleep(delay)
                    attempt += 1
                    continue
                break
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
        if response.status_code == 429:
            raise PlatformError(f"{self.label}: platforma limitează numărul de cereri (rate limit). Reîncearcă peste câteva momente.")
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

    # -- Helpers shared by all platforms ----------------------------------
    def user_exists(self, username: str) -> PlatformUser | None:
        """Return the user if it exists, None otherwise. Other errors propagate."""
        try:
            return self.get_user(username)
        except NotFound:
            return None

    def cached_groups(self) -> list[Group]:
        """Group list with a short cache, so repeated page loads do not hammer the platform."""
        now = time.monotonic()
        if self._group_cache and now - self._group_cache[0] < self.group_cache_seconds:
            return self._group_cache[1]
        groups = self.list_groups()
        self._group_cache = (now, groups)
        return groups

    def invalidate_group_cache(self) -> None:
        self._group_cache = None

    def find_group(self, group_id: str) -> Group | None:
        """Look the group up by id or name; refresh a possibly stale cache once before giving up."""
        for attempt in range(2):
            match = next((g for g in self.cached_groups() if group_id in (g.id, g.name)), None)
            if match or attempt:
                return match
            self.invalidate_group_cache()
        return None

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
