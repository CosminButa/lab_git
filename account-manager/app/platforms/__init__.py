"""Registry of configured platform clients, built once from the application config."""
from __future__ import annotations

from .base import Group, NotFound, PlatformClient, PlatformError, PlatformUser
from .jira import JiraClient
from .keycloak import KeycloakClient
from .nextcloud import NextcloudClient

__all__ = ["Group", "NotFound", "PlatformClient", "PlatformError", "PlatformUser", "Registry", "build_registry"]


class Registry:
    def __init__(self):
        self._clients: dict[str, PlatformClient] = {}
        # Platforms known to the app but left unconfigured; still shown (greyed out) in the UI.
        self.unconfigured: dict[str, str] = {}

    def register(self, client: PlatformClient) -> None:
        self._clients[client.key] = client

    def get(self, key: str) -> PlatformClient | None:
        return self._clients.get(key)

    def all(self) -> list[PlatformClient]:
        return list(self._clients.values())


def build_registry(config) -> Registry:
    registry = Registry()
    http = {
        "timeout": config.get("HTTP_TIMEOUT_SECONDS", 15),
        "verify": config.get("HTTP_VERIFY_TLS", True),
        "min_interval": config.get("API_MIN_INTERVAL_MS", 200) / 1000,
        "max_retries": config.get("API_MAX_RETRIES", 3),
        "group_cache_seconds": config.get("GROUP_CACHE_SECONDS", 60),
    }

    if config.get("KEYCLOAK_URL") and config.get("KEYCLOAK_REALM") and config.get("KEYCLOAK_CLIENT_ID") and config.get("KEYCLOAK_CLIENT_SECRET"):
        registry.register(
            KeycloakClient(
                config["KEYCLOAK_URL"],
                realm=config["KEYCLOAK_REALM"],
                client_id=config["KEYCLOAK_CLIENT_ID"],
                client_secret=config["KEYCLOAK_CLIENT_SECRET"],
                auth_realm=config.get("KEYCLOAK_AUTH_REALM"),
                **http,
            )
        )
    else:
        registry.unconfigured["keycloak"] = "Keycloak"

    if config.get("JIRA_URL") and config.get("JIRA_TOKEN"):
        registry.register(JiraClient(config["JIRA_URL"], token=config["JIRA_TOKEN"], **http))
    else:
        registry.unconfigured["jira"] = "Jira"

    if config.get("NEXTCLOUD_URL") and config.get("NEXTCLOUD_USER") and config.get("NEXTCLOUD_APP_PASSWORD"):
        registry.register(
            NextcloudClient(
                config["NEXTCLOUD_URL"], username=config["NEXTCLOUD_USER"], app_password=config["NEXTCLOUD_APP_PASSWORD"], **http
            )
        )
    else:
        registry.unconfigured["nextcloud"] = "Nextcloud"

    return registry
