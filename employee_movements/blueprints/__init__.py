"""Feature blueprints. Each module owns one functional area of the application."""

from importlib import import_module

BLUEPRINT_MODULES = (
    'auth',
    'dashboard',
    'structure',
    'catalog',
    'users',
    'employees',
    'excel_import',
    'movements',
    'missions',
    'delegations',
    'reports',
    'health',
    'assistant',
    'notifications',
)


def register_blueprints(app):
    for name in BLUEPRINT_MODULES:
        app.register_blueprint(import_module(f'{__name__}.{name}').bp)
