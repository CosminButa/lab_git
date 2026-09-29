import secrets
from datetime import datetime, timedelta, timezone

from flask_login import UserMixin
from werkzeug.security import check_password_hash, generate_password_hash

from .extensions import db

ROLE_ADMIN = "admin"
ROLE_OPERATOR = "operator"
ROLES = (ROLE_ADMIN, ROLE_OPERATOR)


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Operator(UserMixin, db.Model):
    """A person allowed to log in to this application and manage platform accounts."""

    __tablename__ = "operators"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, nullable=False, index=True)
    display_name = db.Column(db.String(128), nullable=False, default="")
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(16), nullable=False, default=ROLE_OPERATOR)
    active = db.Column(db.Boolean, nullable=False, default=True)
    must_change_password = db.Column(db.Boolean, nullable=False, default=False)
    failed_logins = db.Column(db.Integer, nullable=False, default=0)
    locked_until = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    last_login_at = db.Column(db.DateTime, nullable=True)
    # Changing this value invalidates every existing session of the operator.
    session_token = db.Column(db.String(32), nullable=False, default="")

    @property
    def is_active(self) -> bool:  # used by Flask-Login
        return self.active

    @property
    def is_admin(self) -> bool:
        return self.role == ROLE_ADMIN

    def get_id(self) -> str:  # Flask-Login session identifier
        return f"{self.id}:{self.session_token}"

    def set_password(self, password: str) -> None:
        self.password_hash = generate_password_hash(password, method="scrypt")
        self.rotate_session_token()

    def check_password(self, password: str) -> bool:
        return check_password_hash(self.password_hash, password)

    def rotate_session_token(self) -> None:
        self.session_token = secrets.token_hex(16)

    @property
    def is_locked(self) -> bool:
        return self.locked_until is not None and self.locked_until > utcnow()

    def register_failure(self, max_failures: int, lockout_minutes: int) -> None:
        self.failed_logins += 1
        if self.failed_logins >= max_failures:
            self.locked_until = utcnow() + timedelta(minutes=lockout_minutes)
            self.failed_logins = 0

    def register_success(self) -> None:
        self.failed_logins = 0
        self.locked_until = None
        self.last_login_at = utcnow()


class AuditLog(db.Model):
    """Every state-changing action, who did it and whether it worked. Never holds secrets."""

    __tablename__ = "audit_log"

    id = db.Column(db.Integer, primary_key=True)
    ts = db.Column(db.DateTime, nullable=False, default=utcnow, index=True)
    operator = db.Column(db.String(64), nullable=False, index=True)
    platform = db.Column(db.String(32), nullable=False, index=True)
    action = db.Column(db.String(64), nullable=False)
    target = db.Column(db.String(255), nullable=False, default="")
    outcome = db.Column(db.String(8), nullable=False)  # "ok" | "error"
    details = db.Column(db.String(1000), nullable=False, default="")
