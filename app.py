"""Compatibility WSGI entry point for hosts configured as ``gunicorn app:app``."""

from employee_movements import create_app

app = create_app()
