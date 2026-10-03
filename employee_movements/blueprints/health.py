"""Liveness/readiness probe used by Docker and load balancers."""

from flask import Blueprint, jsonify
from sqlalchemy import text

from ..extensions import db
from .. import __version__
from ..config import database_backend

bp = Blueprint('health', __name__)


@bp.get('/healthz')
def healthz():
    try:
        db.session.execute(text('SELECT 1'))
    except Exception:
        return jsonify(status='unavailable'), 503
    return jsonify(
        status='ok',
        version=__version__,
        app_env=db.get_app().config.get('APP_ENV'),
        database_backend=database_backend(db.get_app().config.get('SQLALCHEMY_DATABASE_URI')),
        database_url_configured=bool(db.get_app().config.get('DATABASE_URL_CONFIGURED')),
    )
