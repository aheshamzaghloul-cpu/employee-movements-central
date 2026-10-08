from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AUTH = (ROOT / 'employee_movements' / 'blueprints' / 'auth.py').read_text(encoding='utf-8')
CONFIG = (ROOT / 'employee_movements' / 'config.py').read_text(encoding='utf-8')


def test_review_access_is_disabled_by_default_and_token_gated():
    assert "'REVIEW_ACCESS_ENABLED': os.getenv('REVIEW_ACCESS_ENABLED', '0') == '1'" in CONFIG
    assert "if not current_app.config.get('REVIEW_ACCESS_ENABLED'):" in AUTH
    assert "len(expected) < 32" in AUTH
    assert 'hmac.compare_digest(token, expected)' in AUTH


def test_review_access_targets_only_configured_review_user():
    assert "username = current_app.config.get('REVIEW_USERNAME', 'full_review_test')" in AUTH
    assert "User.query.filter_by(username=username).first()" in AUTH
    assert "session['uid'] = user.id" in AUTH


def test_review_access_does_not_remove_normal_login():
    assert "@bp.route('/login', methods=['GET', 'POST'])" in AUTH
    assert "check_password_hash(user.password_hash" in AUTH
