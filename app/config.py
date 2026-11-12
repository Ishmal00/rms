import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

BASE_DIR = os.path.abspath(os.path.dirname(os.path.dirname(__file__)))


class Config:
    """Base configuration settings."""
    SECRET_KEY = os.environ.get('SECRET_KEY', 'default-dev-secret-key-change-me')
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_RECORD_QUERIES = True

    # Database configuration
    # Default to MySQL XAMPP connection, fallback to SQLite if needed
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        'DATABASE_URL',
        'mysql+pymysql://root:@localhost:3306/restaurant_db'
    )
    SQLALCHEMY_ENGINE_OPTIONS = {
        'pool_pre_ping': True,
        'pool_recycle': 300,
    }

    # Redis configuration
    REDIS_URL = os.environ.get('REDIS_URL', 'redis://localhost:6379/0')

    # Security & Session
    WTF_CSRF_ENABLED = True
    REMEMBER_COOKIE_DURATION = 86400 * 7  # 7 days


class DevelopmentConfig(Config):
    """Development configuration."""
    DEBUG = True


class TestingConfig(Config):
    """Testing configuration."""
    TESTING = True
    SQLALCHEMY_DATABASE_URI = os.environ.get('TEST_DATABASE_URL')
    WTF_CSRF_ENABLED = False


class ProductionConfig(Config):
    """Production configuration."""
    DEBUG = False
    SESSION_COOKIE_SECURE = True
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    SQLALCHEMY_ENGINE_OPTIONS = {
        'pool_pre_ping': True,
        'pool_recycle': 280,
        'pool_size': 5,
        'max_overflow': 2,
    }

    @classmethod
    def from_environment(cls):
        """Build production settings and fail fast when required secrets are absent."""
        secret_key = os.environ.get('SECRET_KEY')
        database_url = os.environ.get('DATABASE_URL')
        missing = [
            name for name, value in (
                ('SECRET_KEY', secret_key),
                ('DATABASE_URL', database_url),
            )
            if not value or not value.strip()
        ]
        if missing:
            raise RuntimeError(
                'Missing required production environment variable(s): '
                + ', '.join(missing)
            )

        engine_options = dict(cls.SQLALCHEMY_ENGINE_OPTIONS)
        db_ssl_ca = os.environ.get('DB_SSL_CA')
        if db_ssl_ca:
            engine_options['connect_args'] = {'ssl': {'ca': db_ssl_ca}}

        return {
            'DEBUG': cls.DEBUG,
            'SECRET_KEY': secret_key,
            'SQLALCHEMY_DATABASE_URI': database_url,
            'SQLALCHEMY_ENGINE_OPTIONS': engine_options,
            'SESSION_COOKIE_SECURE': cls.SESSION_COOKIE_SECURE,
            'SESSION_COOKIE_HTTPONLY': cls.SESSION_COOKIE_HTTPONLY,
            'SESSION_COOKIE_SAMESITE': cls.SESSION_COOKIE_SAMESITE,
        }


config = {
    'development': DevelopmentConfig,
    'testing': TestingConfig,
    'production': ProductionConfig,
    'default': DevelopmentConfig
}
