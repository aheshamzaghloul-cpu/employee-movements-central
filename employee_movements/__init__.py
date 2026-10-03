"""نظام إدارة حركات الموظفين — Employee Movements Central."""

import logging

from flask import Flask

__version__ = '58.0.0'


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
        with app.app_context():
            init_database(app)
    return app
