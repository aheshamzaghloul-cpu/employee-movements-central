import pytest

from employee_movements.config import ConfigError, load_config, normalize_database_url


@pytest.mark.parametrize(
    'url',
    [
        'postgres://u:p@h:5432/db',
        'postgresql://u:p@h:5432/db',
        'postgresql+psycopg://u:p@h:5432/db',
    ],
)
def test_postgres_urls_use_installed_driver(url):
    assert normalize_database_url(url) == 'postgresql+psycopg2://u:p@h:5432/db'


def test_sqlite_url_untouched():
    assert normalize_database_url('sqlite:///x.db') == 'sqlite:///x.db'


def test_production_rejects_missing_secret(monkeypatch):
    monkeypatch.setenv('APP_ENV', 'production')
    monkeypatch.delenv('SECRET_KEY', raising=False)
    with pytest.raises(ConfigError):
        load_config()


def test_production_rejects_placeholder_secret(monkeypatch):
    monkeypatch.setenv('APP_ENV', 'production')
    monkeypatch.setenv('SECRET_KEY', 'change-me-' + 'x' * 40)
    with pytest.raises(ConfigError):
        load_config()


def test_production_accepts_strong_secret(monkeypatch):
    monkeypatch.setenv('APP_ENV', 'production')
    monkeypatch.setenv('SECRET_KEY', 'a' * 48)
    assert load_config()['SECRET_KEY'] == 'a' * 48


def test_development_generates_ephemeral_secret(monkeypatch):
    monkeypatch.setenv('APP_ENV', 'development')
    monkeypatch.delenv('SECRET_KEY', raising=False)
    assert len(load_config()['SECRET_KEY']) >= 32
