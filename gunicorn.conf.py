"""Gunicorn worker hooks for safe SQLAlchemy pooling with --preload."""


def post_worker_init(worker):
    """Drop inherited pool state after a preloaded worker initializes the Flask app.

    The master process performs schema bootstrap before forking. Each child must
    create its own DBAPI connections instead of reusing inherited socket handles.
    close=False prevents the child from closing connections still owned by the master.
    """
    app = getattr(worker, "wsgi", None)
    if app is None or not hasattr(app, "app_context"):
        worker.log.error("Cannot reset SQLAlchemy pool: Flask WSGI app is unavailable")
        return
    from employee_movements.extensions import db

    with app.app_context():
        db.engine.dispose(close=False)
