"""نظام إدارة حركات الموظفين — Employee Movements Central."""

import logging
import time

from sqlalchemy.exc import OperationalError

from flask import Flask

__version__ = '61.2.1'


def create_app(overrides=None):
    """Application factory.

    ``overrides`` lets tests inject configuration (for example an in-memory
    SQLite URI and ``INIT_DATABASE=False``).
    """
    from .bootstrap import init_database
    from .config import load_config
    from .errors import register_error_handlers
    from .extensions import db
    from .hooks import register_hooks
    from .blueprints import register_blueprints

    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(name)s: %(message)s')
    app = Flask(__name__)
    app.config.update(load_config(overrides))
    db.init_app(app)
    register_hooks(app)
    register_blueprints(app)
    register_error_handlers(app)
    if app.config['INIT_DATABASE']:
        _initialize_database_with_retry(app, init_database)
    return app


def _initialize_database_with_retry(app, init_database):
    """Initialize the schema while tolerating a briefly unavailable PostgreSQL service.

    Blitz/cloud databases can become reachable a few seconds after the web
    container starts. Without a retry window, Gunicorn's preload step turns
    that transient condition into a restart loop. A persistent failure is
    still raised after the bounded retry window so deployment does not appear
    healthy when its database is genuinely unavailable.
    """
    retries = app.config.get('DB_INIT_RETRIES', 8)
    delay = app.config.get('DB_INIT_RETRY_DELAY', 3.0)
    for attempt in range(1, retries + 1):
        try:
            with app.app_context():
                init_database(app)
            return
        except OperationalError as exc:
            if attempt >= retries:
                raise
            # Drop any failed scoped session/transaction before the next attempt.
            from .extensions import db
            db.session.remove()
            app.logger.warning(
                'قاعدة PostgreSQL غير متاحة مؤقتًا أثناء الإقلاع (محاولة %s/%s): %s. إعادة المحاولة بعد %.1f ثانية.',
                attempt, retries, exc, delay,
            )
            time.sleep(delay)
            delay = min(delay * 2, 30.0)
