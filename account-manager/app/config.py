"""Application configuration, read exclusively from environment variables.

Secrets (SECRET_KEY, platform credentials) are never written to disk by the
application and never rendered in any page or log.
"""
import os
from datetime import timedelta


def _bool(name: str, default: bool) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _int(name: str, default: int) -> int:
    value = os.environ.get(name)
    return int(value) if value else default


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY")

    SQLALCHEMY_DATABASE_URI = os.environ.get("DATABASE_URL", "sqlite:////data/app.db")
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Session hardening
    SESSION_COOKIE_NAME = "am_session"
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = _bool("SESSION_COOKIE_SECURE", True)
    PERMANENT_SESSION_LIFETIME = timedelta(minutes=_int("SESSION_MINUTES", 480))
    SESSION_REFRESH_EACH_REQUEST = True

    WTF_CSRF_ENABLED = True
    WTF_CSRF_TIME_LIMIT = None  # bound to the session lifetime instead
    MAX_CONTENT_LENGTH = 1024 * 1024  # enough for a CSV import

    # Reverse proxy / ingress
    PROXY_COUNT = _int("PROXY_COUNT", 1)

    # Login protection
    LOGIN_MAX_FAILURES = _int("LOGIN_MAX_FAILURES", 5)
    LOGIN_LOCKOUT_MINUTES = _int("LOGIN_LOCKOUT_MINUTES", 15)
    LOGIN_RATE_LIMIT_PER_MINUTE = _int("LOGIN_RATE_LIMIT_PER_MINUTE", 20)
    PASSWORD_MIN_LENGTH = _int("PASSWORD_MIN_LENGTH", 12)

    # Optional first-admin bootstrap. Only used when the operator table is empty.
    BOOTSTRAP_ADMIN_USERNAME = os.environ.get("BOOTSTRAP_ADMIN_USERNAME")
    BOOTSTRAP_ADMIN_PASSWORD = os.environ.get("BOOTSTRAP_ADMIN_PASSWORD")

    # Outbound HTTP to the managed platforms
    HTTP_TIMEOUT_SECONDS = _int("HTTP_TIMEOUT_SECONDS", 15)
    HTTP_VERIFY_TLS = _bool("HTTP_VERIFY_TLS", True)
    # Rate-limit friendliness: minimum gap between two calls to the same platform,
    # retries on HTTP 429/503 (honouring Retry-After) and group list caching.
    API_MIN_INTERVAL_MS = _int("API_MIN_INTERVAL_MS", 200)
    API_MAX_RETRIES = _int("API_MAX_RETRIES", 3)
    GROUP_CACHE_SECONDS = _int("GROUP_CACHE_SECONDS", 60)
    SEARCH_RESULT_LIMIT = _int("SEARCH_RESULT_LIMIT", 25)
    IMPORT_MAX_ROWS = _int("IMPORT_MAX_ROWS", 500)

    # Keycloak (Admin REST API, client credentials of a service account)
    KEYCLOAK_URL = os.environ.get("KEYCLOAK_URL")
    KEYCLOAK_REALM = os.environ.get("KEYCLOAK_REALM")
    KEYCLOAK_AUTH_REALM = os.environ.get("KEYCLOAK_AUTH_REALM")  # defaults to KEYCLOAK_REALM
    KEYCLOAK_CLIENT_ID = os.environ.get("KEYCLOAK_CLIENT_ID")
    KEYCLOAK_CLIENT_SECRET = os.environ.get("KEYCLOAK_CLIENT_SECRET")

    # Jira Data Center / Server (REST API v2, Personal Access Token)
    JIRA_URL = os.environ.get("JIRA_URL")
    JIRA_TOKEN = os.environ.get("JIRA_TOKEN")

    # Nextcloud (OCS Provisioning API, admin user + app password)
    NEXTCLOUD_URL = os.environ.get("NEXTCLOUD_URL")
    NEXTCLOUD_USER = os.environ.get("NEXTCLOUD_USER")
    NEXTCLOUD_APP_PASSWORD = os.environ.get("NEXTCLOUD_APP_PASSWORD")


class TestConfig(Config):
    TESTING = True
    SECRET_KEY = "test-secret-key-not-for-production"
    SQLALCHEMY_DATABASE_URI = "sqlite://"
    SESSION_COOKIE_SECURE = False
    WTF_CSRF_ENABLED = False
    BOOTSTRAP_ADMIN_USERNAME = None
    BOOTSTRAP_ADMIN_PASSWORD = None
    KEYCLOAK_URL = None
    JIRA_URL = None
    NEXTCLOUD_URL = None
