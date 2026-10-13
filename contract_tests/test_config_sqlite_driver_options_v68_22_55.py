"""Regression contract for driver-specific SQLAlchemy connection options."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def test_connect_timeout_is_applied_only_after_final_driver_is_known():
    source = (ROOT / "employee_movements" / "config.py").read_text(encoding="utf-8")
    assert "'connect_args': {'connect_timeout'" not in source
    assert "if database_backend(cfg.get('SQLALCHEMY_DATABASE_URI')) == 'postgresql':" in source
    assert "connect_args.setdefault('connect_timeout'" in source
    assert source.index("if overrides:") < source.index("if database_backend(cfg.get('SQLALCHEMY_DATABASE_URI')) == 'postgresql':")
