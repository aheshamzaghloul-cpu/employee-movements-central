"""Runtime regression checks for config parsing without importing Flask."""
from __future__ import annotations

import importlib.util
import os
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
_CONFIG_PATH = ROOT / "employee_movements" / "config.py"
_SPEC = importlib.util.spec_from_file_location("employee_movements_config_isolated", _CONFIG_PATH)
assert _SPEC and _SPEC.loader
_CONFIG = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_CONFIG)


@pytest.mark.parametrize("app_env", ["prod", "Production-like", "", "staging", "prod "])
def test_unknown_environment_values_fail_closed(monkeypatch, app_env):
    monkeypatch.setenv("APP_ENV", app_env)
    monkeypatch.delenv("SECRET_KEY", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)

    with pytest.raises(_CONFIG.ConfigError, match="APP_ENV غير صالح"):
        _CONFIG.load_config()


def test_override_environment_updates_testing_flag_and_normalizes_driver(monkeypatch):
    monkeypatch.setenv("APP_ENV", "development")
    config = _CONFIG.load_config({
        "APP_ENV": "testing",
        "SECRET_KEY": "k" * 48,
        "SQLALCHEMY_DATABASE_URI": "postgresql+psycopg://user:pass@db.example.invalid:5432/test",
        "INIT_DATABASE": False,
    })

    assert config["APP_ENV"] == "testing"
    assert config["TESTING"] is True
    assert config["SQLALCHEMY_DATABASE_URI"] == "postgresql+psycopg2://user:pass@db.example.invalid:5432/test"
    assert config["SQLALCHEMY_ENGINE_OPTIONS"]["connect_args"]["connect_timeout"] > 0
