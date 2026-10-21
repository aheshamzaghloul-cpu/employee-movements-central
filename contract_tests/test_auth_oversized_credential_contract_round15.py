"""Source-only guard for bounded login credential work in round 15.

This contract is intentionally not run as part of the static-only review.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _source(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def test_login_caps_credentials_before_database_lookup_and_hash_verification():
    source = _source("employee_movements/blueprints/auth.py")
    login = source.split("def login():", 1)[1].split("@bp.post('/logout')", 1)[0]
    assert "len(raw_username) > 80" in login
    assert "len(password) > MAX_PASSWORD_LENGTH" in login
    assert login.index("if oversized_credentials or not username or not password:") < login.index("User.query.filter_by(username=username).first()")
    assert login.index("if oversized_credentials or not username or not password:") < login.index("check_password_hash(user.password_hash, password)")
    assert "[oversized-credentials]" in login


def test_user_facing_password_changes_and_admin_bootstrap_share_a_bounded_policy():
    source = _source("employee_movements/validation.py")
    assert "MAX_PASSWORD_LENGTH" in source
    constants = _source("employee_movements/constants.py")
    assert "MAX_PASSWORD_LENGTH = 4096" in constants
    block = source.split("def valid_password(p):", 1)[1].split("def record_movement_history", 1)[0]
    assert "isinstance(p, str)" in block
    assert "8 <= len(p) <= MAX_PASSWORD_LENGTH" in block
    config = _source("employee_movements/config.py")
    assert "ADMIN_PASSWORD" in config and "MAX_PASSWORD_LENGTH" in config
