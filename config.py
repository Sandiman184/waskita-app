import os
from datetime import timedelta

class Config:
    # Security - SECRET_KEY is required
    SECRET_KEY = os.environ.get('SECRET_KEY')
    if not SECRET_KEY:
        raise ValueError("SECRET_KEY environment variable is required")
    
    # Database configuration
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL')
    if not SQLALCHEMY_DATABASE_URI:
        raise ValueError("DATABASE_URL environment variable is required")
    
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'uploads')
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16MB max file size
    
    # Session configuration
    PERMANENT_SESSION_LIFETIME = timedelta(hours=24)
    SESSION_COOKIE_SECURE = True
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    
    # File upload settings
    ALLOWED_EXTENSIONS = {'csv', 'xlsx', 'xls'}
    
    # Pagination
    POSTS_PER_PAGE = 20
    
    # Localization
    LANGUAGES = {'id': 'Bahasa Indonesia', 'en': 'English'}
    DEFAULT_LANGUAGE = 'id'
    BABEL_DEFAULT_LOCALE = 'id'
    BABEL_DEFAULT_TIMEZONE = 'Asia/Jakarta'
    
    # CSRF Protection
    WTF_CSRF_ENABLED = os.environ.get('WTF_CSRF_ENABLED', 'True').lower() == 'true'
    WTF_CSRF_TIME_LIMIT = int(os.environ.get('WTF_CSRF_TIME_LIMIT', '3600'))
    
    # Model paths - relative to app directory for containerization compatibility
    WORD2VEC_MODEL_PATH = os.getenv('WORD2VEC_MODEL_PATH', 
        os.path.join(os.path.dirname(__file__), 'models', 'embeddings', 'wiki_word2vec_csv_updated.model'))
    NAIVE_BAYES_MODEL1_PATH = os.getenv('NAIVE_BAYES_MODEL1_PATH', 
        os.path.join(os.path.dirname(__file__), 'models', 'navesbayes', 'naive_bayes_model1.pkl'))
    NAIVE_BAYES_MODEL2_PATH = os.getenv('NAIVE_BAYES_MODEL2_PATH', 
        os.path.join(os.path.dirname(__file__), 'models', 'navesbayes', 'naive_bayes_model2.pkl'))
    NAIVE_BAYES_MODEL3_PATH = os.getenv('NAIVE_BAYES_MODEL3_PATH', 
        os.path.join(os.path.dirname(__file__), 'models', 'navesbayes', 'naive_bayes_model3.pkl'))
    
    @staticmethod
    def init_app(app):
        pass

class DevelopmentConfig(Config):
    DEBUG = True
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL')
    if not SQLALCHEMY_DATABASE_URI:
        raise ValueError("DATABASE_URL environment variable is required")
    
    # Session configuration for local development
    SESSION_COOKIE_SECURE = False
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    SESSION_COOKIE_DOMAIN = None

class TestingConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = os.environ.get('TEST_DATABASE_URL', 'sqlite:///:memory:')
    WTF_CSRF_ENABLED = False
    SESSION_COOKIE_SECURE = False

class ProductionConfig(Config):
    DEBUG = False
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL')
    if not SQLALCHEMY_DATABASE_URI:
        raise ValueError("DATABASE_URL environment variable is required for production")
    
    # Production security settings
    SESSION_COOKIE_SECURE = True
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Strict'
    
    @classmethod
    def init_app(cls, app):
        Config.init_app(app)
        
        # Log to syslog
        import logging
        from logging.handlers import SysLogHandler
        syslog_handler = SysLogHandler()
        syslog_handler.setLevel(logging.WARNING)
        app.logger.addHandler(syslog_handler)

config = {
    'development': DevelopmentConfig,
    'testing': TestingConfig,
    'production': ProductionConfig,
    'default': DevelopmentConfig
}