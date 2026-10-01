"""Liveness/readiness probe used by Docker and load balancers."""

from flask import Blueprint, jsonify
from sqlalchemy import text

from ..extensions import db

bp = Blueprint('health', __name__)


@bp.get('/healthz')
def healthz():
    try:
        db.session.execute(text('SELECT 1'))
    except Exception:
        return jsonify(status='unavailable'), 503
    return jsonify(status='ok')
