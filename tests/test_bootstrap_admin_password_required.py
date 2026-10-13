import pytest

from employee_movements.bootstrap import ensure_admin_account
from employee_movements.config import ConfigError
from employee_movements.extensions import db
from employee_movements.models import User


def test_first_admin_bootstrap_requires_explicit_password_without_logging_a_credential(app, caplog):
    with app.app_context():
        username = "first-admin-no-password-test"
        app.config["ADMIN_USERNAME"] = username
        app.config["ADMIN_PASSWORD"] = ""

        with pytest.raises(ConfigError, match="ADMIN_PASSWORD مطلوب"):
            ensure_admin_account(app)

        assert User.query.filter_by(username=username).first() is None
        assert "كلمة مرور مؤقتة:" not in caplog.text
