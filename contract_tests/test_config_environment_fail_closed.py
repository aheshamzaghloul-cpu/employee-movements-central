"""Static regression guard for fail-closed application environment parsing."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_application_environment_is_allowlisted_after_overrides():
    source = (ROOT / "employee_movements" / "config.py").read_text(encoding="utf-8")
    assert "VALID_APP_ENVS = frozenset({'production', 'development', 'testing'})" in source
    assert "cfg['APP_ENV'] = str(cfg.get('APP_ENV', '')).strip().lower()" in source
    assert "if cfg['APP_ENV'] not in VALID_APP_ENVS:" in source
    assert "if not overrides or 'TESTING' not in overrides:" in source
    assert "cfg['TESTING'] = cfg['APP_ENV'] == 'testing'" in source
    assert "cfg['SQLALCHEMY_DATABASE_URI'] = normalize_database_url(" in source
    assert source.index("if overrides:") < source.index("cfg['SQLALCHEMY_DATABASE_URI'] = normalize_database_url(")
