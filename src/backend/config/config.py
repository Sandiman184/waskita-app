import os
from datetime import timedelta

"""
Waskita Application Configuration
---------------------------------

MODEL PATH CONFIGURATION:
The application supports both local development (Windows/Linux) and Docker environments.

1. Local Development:
   - Paths are resolved relative to the project root.
   - Default: ../../../models/embeddings/word2vec_model.joblib
   - To override, set WORD2VEC_MODEL_PATH environment variable.

2. Docker Environment:
   - Paths are typically absolute (e.g., /app/models/...).
   - The Dockerfile sets WORD2VEC_MODEL_PATH=/app/models/embeddings/word2vec_model.joblib.
   - Ensure volumes are mounted correctly in docker-compose.yml:
     - ./models:/app/models

TROUBLESHOOTING [Errno 22] Invalid Argument:
- This error often occurs on Windows when accessing memory-mapped files (mmap).
- It can be caused by:
  1. 0-byte model files.
  2. File locking by another process.
  3. Invalid path characters.
- The application now includes robust fallback mechanisms:
  - Validates file size > 0.
  - Retries loading without mmap if mmap fails.
  - Uses rename-then-delete strategy for model updates to handle file locks.
"""

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
    # Enable pool pre-ping to handle database restarts/disconnects gracefully
    SQLALCHEMY_ENGINE_OPTIONS = {
        'pool_pre_ping': True,
        'pool_recycle': 300,
    }
    # File upload directory: prefer ENV, fallback to project uploads/ path
    UPLOAD_FOLDER = os.environ.get(
        'UPLOAD_FOLDER',
        os.path.join(os.path.dirname(os.path.abspath(__file__)), 'uploads')
    )
    # Max upload size from ENV (bytes), default 10GB for IndoBERT/Word2Vec support
    MAX_CONTENT_LENGTH = int(os.environ.get('MAX_CONTENT_LENGTH', str(10 * 1024 * 1024 * 1024)))
    
    # Session configuration (centralized to ENV with sensible defaults)
    PERMANENT_SESSION_LIFETIME = timedelta(hours=24)
    SESSION_COOKIE_SECURE = os.environ.get('SESSION_COOKIE_SECURE', 'True').lower() == 'true'
    SESSION_COOKIE_HTTPONLY = os.environ.get('SESSION_COOKIE_HTTPONLY', 'True').lower() == 'true'
    SESSION_COOKIE_SAMESITE = os.environ.get('SESSION_COOKIE_SAMESITE', 'Lax')
    _session_domain = os.environ.get('SESSION_COOKIE_DOMAIN', '').strip()
    SESSION_COOKIE_DOMAIN = None if _session_domain.lower() in {'', 'none', 'null'} else _session_domain
    
    # File upload settings
    ALLOWED_EXTENSIONS = {'csv', 'xlsx', 'xls'}

    # OTP Settings
    OTP_ENABLED = os.environ.get('OTP_ENABLED', 'True').lower() == 'true'
    OTP_LENGTH = int(os.environ.get('OTP_LENGTH', '6'))
    OTP_EXPIRY_MINUTES = int(os.environ.get('OTP_EXPIRY_MINUTES', '30'))
    MAX_OTP_ATTEMPTS = int(os.environ.get('MAX_OTP_ATTEMPTS', '3'))
    
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
    
    # Model base path - pointing to root/models
    # Use os.path.normpath to resolve '..' and handle slashes correctly for both Windows and Linux
    _model_base_path = os.path.abspath(os.path.normpath(os.path.join(os.path.dirname(__file__), '..', '..', '..', 'models')))

    # Model paths - relative to app directory for containerization compatibility
    # Environment variables take precedence (useful for Docker where paths are fixed like /app/models/...)
    # Default fallback uses local development structure
    WORD2VEC_MODEL_PATH = os.getenv('WORD2VEC_MODEL_PATH', 
        os.path.join(_model_base_path, 'embeddings', 'word2vec_model.joblib'))
    
    # Classification Model Paths (7 Models)
    MODEL_NAIVE_BAYES_PATH = os.getenv('MODEL_NAIVE_BAYES_PATH', 
        os.path.join(_model_base_path, 'classifiers', 'Naive Bayes_classifier_model.joblib'))
    MODEL_SVM_PATH = os.getenv('MODEL_SVM_PATH', 
        os.path.join(_model_base_path, 'classifiers', 'SVM_classifier_model.joblib'))
    MODEL_RANDOM_FOREST_PATH = os.getenv('MODEL_RANDOM_FOREST_PATH', 
        os.path.join(_model_base_path, 'classifiers', 'Random Forest_classifier_model.joblib'))
    MODEL_LOGISTIC_REGRESSION_PATH = os.getenv('MODEL_LOGISTIC_REGRESSION_PATH', 
        os.path.join(_model_base_path, 'classifiers', 'Logistic Regression_classifier_model.joblib'))
    MODEL_DECISION_TREE_PATH = os.getenv('MODEL_DECISION_TREE_PATH', 
        os.path.join(_model_base_path, 'classifiers', 'Decision Tree_classifier_model.joblib'))
    MODEL_KNN_PATH = os.getenv('MODEL_KNN_PATH', 
        os.path.join(_model_base_path, 'classifiers', 'KNN_classifier_model.joblib'))
    
    # IndoBERT Model Path
    MODEL_INDOBERT_PATH = os.getenv('MODEL_INDOBERT_PATH', 
        os.path.join(_model_base_path, 'indobert'))
    
    # Label Encoder Path
    LABEL_ENCODER_PATH = os.getenv('LABEL_ENCODER_PATH',
        os.path.join(_model_base_path, 'label_encoder', 'label_encoder.joblib'))
    
    # Email Configuration
    MAIL_SERVER = os.environ.get('MAIL_SERVER', 'smtp.gmail.com')
    MAIL_PORT = int(os.environ.get('MAIL_PORT', '587'))
    MAIL_USE_TLS = os.environ.get('MAIL_USE_TLS', 'True').lower() == 'true'
    MAIL_USE_SSL = os.environ.get('MAIL_USE_SSL', 'False').lower() == 'true'
    MAIL_USERNAME = os.environ.get('MAIL_USERNAME')
    MAIL_PASSWORD = os.environ.get('MAIL_PASSWORD')
    MAIL_DEFAULT_SENDER = os.environ.get('MAIL_DEFAULT_SENDER')
    ADMIN_EMAIL = os.environ.get('ADMIN_EMAIL')

    # Apify Configuration
    APIFY_API_TOKEN = os.environ.get('APIFY_API_TOKEN')
    APIFY_TWITTER_ACTOR = os.environ.get('APIFY_TWITTER_ACTOR', 'kaitoeasyapi/twitter-x-data-tweet-scraper-pay-per-result-cheapest')
    APIFY_FACEBOOK_ACTOR = os.environ.get('APIFY_FACEBOOK_ACTOR', 'powerai/facebook-post-search-scraper')
    APIFY_TIKTOK_ACTOR = os.environ.get('APIFY_TIKTOK_ACTOR', 'clockworks/free-tiktok-scraper')
    
    @staticmethod
    def init_app(app):
        # Load persistent system settings
        try:
            # Import here to avoid circular imports
            import sys
            import os
            
            # Add backend to path if not already
            backend_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
            if backend_path not in sys.path:
                sys.path.append(backend_path)
                
            from utils.settings_utils import load_system_settings
            load_system_settings(app)
        except Exception as e:
            print(f"Failed to load system settings: {e}")

class DevelopmentConfig(Config):
    DEBUG = True
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL')
    if not SQLALCHEMY_DATABASE_URI:
        raise ValueError("DATABASE_URL environment variable is required")
    
    # Session configuration for local development (can be overridden via ENV)
    SESSION_COOKIE_SECURE = os.environ.get('SESSION_COOKIE_SECURE', 'False').lower() == 'true'
    SESSION_COOKIE_HTTPONLY = os.environ.get('SESSION_COOKIE_HTTPONLY', 'True').lower() == 'true'
    SESSION_COOKIE_SAMESITE = os.environ.get('SESSION_COOKIE_SAMESITE', 'Lax')
    _dev_session_domain = os.environ.get('SESSION_COOKIE_DOMAIN', '').strip()
    SESSION_COOKIE_DOMAIN = None if _dev_session_domain.lower() in {'', 'none', 'null'} else _dev_session_domain

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