"""Environment-driven configuration with fail-fast validation for production."""

import logging
import os
import secrets

logger = logging.getLogger(__name__)

PLACEHOLDER_PREFIXES = ('غيّر', 'change', 'replace', 'your_', 'todo')
MIN_SECRET_KEY_LENGTH = 32
DEV_DATABASE_URL = 'sqlite:///local.db'


class ConfigError(RuntimeError):
    """Raised when the environment is unsafe or incomplete for the selected mode."""


def normalize_database_url(url):
    """Force the installed ``psycopg2`` driver for every PostgreSQL URL spelling.

    Accepts ``postgres://``, ``postgresql://`` and ``postgresql+psycopg://`` so a
    URL copied from a hosting provider (or an older compose file) always works.
    """
    for prefix in ('postgres://', 'postgresql://', 'postgresql+psycopg://'):
        if url.startswith(prefix):
            return 'postgresql+psycopg2://' + url[len(prefix):]
    return url


def is_placeholder(value):
    value = (value or '').strip().lower()
    return not value or value.startswith(PLACEHOLDER_PREFIXES)


def load_config(overrides=None):
    """Build the Flask config mapping from environment variables.

    ``APP_ENV`` selects the mode: ``production`` (default), ``development`` or
    ``testing``. Only production refuses to start with an unsafe configuration.
    """
    env = os.getenv('APP_ENV', 'production').strip().lower()
    cfg = {
        'APP_ENV': env,
        'SQLALCHEMY_DATABASE_URI': normalize_database_url(os.getenv('DATABASE_URL') or DEV_DATABASE_URL),
        'DATABASE_URL_CONFIGURED': bool(os.getenv('DATABASE_URL', '').strip()),
        'SQLALCHEMY_TRACK_MODIFICATIONS': False,
        'SQLALCHEMY_ENGINE_OPTIONS': {
            'pool_pre_ping': True,
            'pool_recycle': int(os.getenv('DB_POOL_RECYCLE', '1800')),
            'connect_args': {'connect_timeout': int(os.getenv('DB_CONNECT_TIMEOUT', '10'))},
        },
        'SESSION_COOKIE_HTTPONLY': True,
        'SESSION_COOKIE_SAMESITE': 'Lax',
        'SESSION_COOKIE_SECURE': os.getenv('COOKIE_SECURE', '0') == '1',
        'MAX_CONTENT_LENGTH': 2 * 1024 * 1024,
        'SECRET_KEY': os.getenv('SECRET_KEY', '').strip(),
        'ADMIN_USERNAME': os.getenv('ADMIN_USERNAME', 'admin').strip() or 'admin',
        'ADMIN_PASSWORD': os.getenv('ADMIN_PASSWORD', ''),
        'ADMIN_EMAIL': os.getenv('ADMIN_EMAIL', '').strip(),
        'GEMINI_API_KEY': os.getenv('GEMINI_API_KEY', '').strip(),
        'GEMINI_MODEL': (os.getenv('GEMINI_MODEL', '').strip() or 'gemini-3.8-flash'),
        'GEMINI_TIMEOUT': int(os.getenv('GEMINI_TIMEOUT', '8')),
        'ASSISTANT_RATE_LIMIT': int(os.getenv('ASSISTANT_RATE_LIMIT', '30')),
        'ASSISTANT_TIMEOUT_SECONDS': int(os.getenv('ASSISTANT_TIMEOUT_SECONDS', '8')),
        'LOGIN_RATE_LIMIT': int(os.getenv('LOGIN_RATE_LIMIT', '10')),
        # Temporary full-review access. Disabled unless explicitly enabled in production.
        'REVIEW_ACCESS_ENABLED': os.getenv('REVIEW_ACCESS_ENABLED', '0') == '1',
        'REVIEW_ACCESS_TOKEN': os.getenv('REVIEW_ACCESS_TOKEN', '').strip(),
        'REVIEW_USERNAME': os.getenv('REVIEW_USERNAME', 'full_review_test').strip() or 'full_review_test',
        'INIT_DATABASE': os.getenv('INIT_DATABASE', '1') == '1',
        'DB_INIT_RETRIES': max(1, int(os.getenv('DB_INIT_RETRIES', '8'))),
        'DB_INIT_RETRY_DELAY': max(1, float(os.getenv('DB_INIT_RETRY_DELAY', '3'))),
        'TESTING': env == 'testing',
    }
    if overrides:
        cfg.update(overrides)
    validate_config(cfg)
    return cfg


def database_backend(uri):
    """Return a non-sensitive database backend label for diagnostics."""
    uri = (uri or '').lower()
    if uri.startswith(('postgresql://', 'postgres://', 'postgresql+')):
        return 'postgresql'
    if uri.startswith('sqlite'):
        return 'sqlite'
    if uri.startswith('mysql'):
        return 'mysql'
    return 'other'


def validate_config(cfg):
    production = cfg['APP_ENV'] == 'production'
    if is_placeholder(cfg['SECRET_KEY']) or len(cfg['SECRET_KEY']) < MIN_SECRET_KEY_LENGTH:
        if production:
            raise ConfigError(
                'SECRET_KEY مفقود أو ضعيف. اضبط SECRET_KEY عشوائيًا بطول %d حرفًا على الأقل '
                '(مثال: python -c "import secrets; print(secrets.token_urlsafe(48))").'
                % MIN_SECRET_KEY_LENGTH
            )
        cfg['SECRET_KEY'] = secrets.token_urlsafe(48)
        logger.warning('SECRET_KEY غير مضبوط: استُخدم مفتاح مؤقت للتطوير فقط (تنتهي الجلسات عند إعادة التشغيل).')
    if production and not cfg['SESSION_COOKIE_SECURE']:
        logger.warning('COOKIE_SECURE=0 في وضع الإنتاج: فعّله (COOKIE_SECURE=1) عند التشغيل عبر HTTPS.')
    if production and not cfg.get('DATABASE_URL_CONFIGURED'):
        raise ConfigError('DATABASE_URL مطلوب في الإنتاج لمنع فقدان قاعدة البيانات والحسابات عند إعادة النشر. استخدم PostgreSQL ثابتة.')
    backend = database_backend(cfg['SQLALCHEMY_DATABASE_URI'])
    if production and backend != 'postgresql':
        raise ConfigError('لا يُسمح إلا بقاعدة PostgreSQL في الإنتاج. اضبط DATABASE_URL على قاعدة PostgreSQL ثابتة.')
    logger.info(
        'تهيئة قاعدة البيانات: backend=%s, DATABASE_URL=%s, APP_ENV=%s',
        backend,
        'configured' if cfg.get('DATABASE_URL_CONFIGURED') else 'missing',
        cfg['APP_ENV'],
    )
