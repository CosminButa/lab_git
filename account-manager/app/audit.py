import logging

from flask_login import current_user

from .extensions import db
from .models import AuditLog

log = logging.getLogger("audit")


def record(platform: str, action: str, target: str = "", outcome: str = "ok", details: str = "") -> None:
    """Persist an audit entry and mirror it to the application log."""
    operator = current_user.username if getattr(current_user, "is_authenticated", False) else "-"
    entry = AuditLog(
        operator=operator,
        platform=platform,
        action=action,
        target=target[:255],
        outcome=outcome,
        details=details[:1000],
    )
    db.session.add(entry)
    db.session.commit()
    log.info("audit operator=%s platform=%s action=%s target=%s outcome=%s", operator, platform, action, target, outcome)
