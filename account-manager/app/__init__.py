import logging
import os

from flask import Flask, redirect, render_template, request, url_for
from flask_login import current_user
from sqlalchemy.exc import IntegrityError
from werkzeug.middleware.proxy_fix import ProxyFix

from .config import Config
from .extensions import csrf, db, login_manager
from .security import apply_security_headers


def create_app(config_object=Config) -> Flask:
    app = Flask(__name__, instance_relative_config=False)
    app.config.from_object(config_object)

    if not app.config.get("SECRET_KEY"):
        raise RuntimeError("SECRET_KEY is not set. Refusing to start without a session signing key.")

    logging.basicConfig(
        level=os.environ.get("LOG_LEVEL", "INFO"),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    proxies = app.config.get("PROXY_COUNT", 0)
    if proxies:
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=proxies, x_proto=proxies, x_host=proxies, x_prefix=proxies)

    db.init_app(app)
    login_manager.init_app(app)
    csrf.init_app(app)

    from .models import Operator

    @login_manager.user_loader
    def load_user(session_id: str):
        try:
            raw_id, token = session_id.split(":", 1)
            operator = db.session.get(Operator, int(raw_id))
        except (ValueError, TypeError):
            return None
        if operator is None or not operator.active or operator.session_token != token:
            return None
        return operator

    from .platforms import build_registry

    app.extensions["platforms"] = build_registry(app.config)

    from .auth.routes import bp as auth_bp
    from .admin.routes import bp as admin_bp
    from .platforms.routes import bp as platforms_bp
    from .cli import register_cli

    app.register_blueprint(auth_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(platforms_bp)
    register_cli(app)

    app.after_request(apply_security_headers)

    @app.before_request
    def enforce_password_change():
        """A freshly created or reset operator can only change their password until they do."""
        if not current_user.is_authenticated or not current_user.must_change_password:
            return None
        allowed = {"auth.change_password", "auth.logout", "static", "healthz"}
        if request.endpoint not in allowed:
            return redirect(url_for("auth.change_password"))
        return None

    @app.get("/healthz")
    def healthz():
        return {"status": "ok"}

    @app.get("/")
    def index():
        if not current_user.is_authenticated:
            return redirect(url_for("auth.login"))
        registry = app.extensions["platforms"]
        return render_template("dashboard.html", platforms=registry.all(), unconfigured=registry.unconfigured)

    @app.errorhandler(403)
    def forbidden(_):
        return render_template("error.html", code=403, message="Nu ai dreptul să accesezi această pagină."), 403

    @app.errorhandler(404)
    def not_found(_):
        return render_template("error.html", code=404, message="Pagina nu există."), 404

    @app.errorhandler(413)
    def too_large(_):
        return render_template("error.html", code=413, message="Cerere prea mare."), 413

    @app.context_processor
    def inject_platforms():
        return {"nav_platforms": app.extensions["platforms"].all()}

    with app.app_context():
        db.create_all()
        _bootstrap_admin(app)

    return app


def _bootstrap_admin(app: Flask) -> None:
    """Create the very first admin from env vars, only when no operator exists yet."""
    from .models import ROLE_ADMIN, Operator

    username = app.config.get("BOOTSTRAP_ADMIN_USERNAME")
    password = app.config.get("BOOTSTRAP_ADMIN_PASSWORD")
    if not username or not password:
        return
    if db.session.query(Operator.id).first() is not None:
        return
    admin = Operator(username=username, display_name=username, role=ROLE_ADMIN, must_change_password=True)
    admin.set_password(password)
    db.session.add(admin)
    try:
        db.session.commit()
    except IntegrityError:
        # Several gunicorn workers start at once; another one won the race. Nothing to do.
        db.session.rollback()
        return
    app.logger.warning("Bootstrap admin '%s' created; the password must be changed at first login.", username)
