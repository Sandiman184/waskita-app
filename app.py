import os
import logging
import locale
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, session
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from flask_wtf.csrf import CSRFProtect
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_cors import CORS
from datetime import datetime
from dotenv import load_dotenv

# Load environment variables from .env file FIRST, before importing config
# In Docker, set DOTENV_OVERRIDE=False to prefer Compose-provided env.
override_env = os.getenv('DOTENV_OVERRIDE', 'True').lower() == 'true'
load_dotenv(override=override_env)

# Routes will be initialized using init_routes function
from models import db, User
from models_otp import RegistrationRequest, AdminNotification, OTPEmailLog
from otp_routes import otp_bp
from config import config as config_map

# Setup logging
import os
from logging.handlers import RotatingFileHandler

# Create logs directory
os.makedirs('logs', exist_ok=True)

# Configure root logger
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler()
    ]
)

# Add rotating file handler for main application logs
file_handler = RotatingFileHandler(
    'logs/waskita.log',
    maxBytes=10*1024*1024,  # 10MB
    backupCount=5,
    encoding='utf-8'
)
file_handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
logging.getLogger().addHandler(file_handler)

# Get logger for this module
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Load environment-specific config class (development/testing/production/default)
# Fallback to 'default' which maps to DevelopmentConfig in config.py
config_name = os.getenv('FLASK_CONFIG', 'default')
try:
    app.config.from_object(config_map[config_name])
    # Call init_app if provided by the config class
    config_map[config_name].init_app(app)
    logger.info(f"Loaded configuration: {config_name}")
except KeyError:
    # If unknown config, fallback to default and log a warning
    app.config.from_object(config_map['default'])
    config_map['default'].init_app(app)
    logger.warning(f"Unknown FLASK_CONFIG '{config_name}', falling back to 'default'")

# Initialize CORS for API endpoints (origins from ENV, comma-separated)
cors_origins_env = os.getenv('CORS_ORIGINS', 'http://localhost:5000,http://127.0.0.1:5000')
cors_origins = [o.strip() for o in cors_origins_env.split(',') if o.strip()]
cors = CORS(app, resources={
    r"/api/*": {
        "origins": cors_origins,
        "supports_credentials": True,
        "allow_headers": ["Content-Type", "Authorization"],
        "methods": ["GET", "POST", "PUT", "DELETE", "OPTIONS"]
    }
})

# Configure JSON to handle Unicode properly
app.json.ensure_ascii = False
app.json.sort_keys = False

# Set Indonesian locale as default
try:
    locale.setlocale(locale.LC_ALL, 'id_ID.UTF-8')
except locale.Error:
    try:
        locale.setlocale(locale.LC_ALL, 'Indonesian_Indonesia.1252')
    except locale.Error:
        logger.warning('Could not set Indonesian locale, using default')
        pass

# Use PostgreSQL as the primary database
pass

# Initialize extensions
from models import db
from flask_migrate import Migrate
from scheduler import cleanup_scheduler
from security_middleware import SecurityMiddleware

db.init_app(app)
migrate = Migrate(app, db)

# Initialize security middleware
security_middleware = SecurityMiddleware(app)

# Initialize CSRF protection
csrf = CSRFProtect(app)

# Configure CSRF to handle first login scenarios
@app.before_request
def ensure_csrf_cookie():
    """Ensure CSRF cookie is set for first-time visitors to enable login"""
    # Generate CSRF token for all GET requests to ensure cookie is set
    if request.method == 'GET':
        # This ensures CSRF cookie is set for first-time visitors
        csrf._get_csrf_token()

# Initialize rate limiter
limiter = Limiter(
    app=app,
    key_func=get_remote_address,
    default_limits=["500 per day", "200 per hour"],
    storage_uri="memory://"
)

# Initialize scheduler
cleanup_scheduler.init_app(app)

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'
login_manager.login_message = 'Silakan login untuk mengakses halaman ini.'
login_manager.login_message_category = 'info'

# Inject asset version for cache-busting of static files
@app.context_processor
def inject_asset_version():
    return {"asset_version": os.getenv("ASSET_VERSION", "1")}

# Create upload directory if it doesn't exist
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# Attempt self-healing permissions for upload folder (helps on VPS/Docker bind mounts)
try:
    upload_dir = os.path.abspath(app.config['UPLOAD_FOLDER'])
    if not os.access(upload_dir, os.W_OK):
        logger.warning(f"Upload folder not writable: {upload_dir}. Attempting to fix permissions...")
        # Try chmod to 775
        try:
            os.chmod(upload_dir, 0o775)
        except Exception as e:
            logger.warning(f"Failed to chmod {upload_dir} to 775: {e}")
        # Try chown to current user/group (only relevant on Linux)
        if os.name != 'nt':
            try:
                uid = os.getuid()
                gid = os.getgid()
                os.chown(upload_dir, uid, gid)
            except Exception as e:
                logger.warning(f"Failed to chown {upload_dir} to current uid/gid: {e}")
        # Re-check write access
        if not os.access(upload_dir, os.W_OK):
            logger.error(
                "Upload folder still not writable after self-healing. "
                "Please ensure host directory permissions allow writes for container user."
            )
except Exception as e:
    logger.error(f"Error while validating/fixing upload folder permissions: {e}")

# Create database tables
with app.app_context():
    db.create_all()

# Initialize model variables
word2vec_model = None
naive_bayes_models = {}
models_loaded = False

# Load models on application startup - ensure this runs regardless of how app is started
def ensure_models_loaded():
    """Ensure models are loaded when application starts"""
    global word2vec_model, naive_bayes_models, models_loaded
    
    if models_loaded:
        return  # Models already loaded
    
    disable_model_loading = os.environ.get('DISABLE_MODEL_LOADING', 'False').lower() == 'true'
    if disable_model_loading:
        logger.info("Model loading is disabled via DISABLE_MODEL_LOADING environment variable")
        # Explicitly set models to None/empty in app config for route usage
        app.config['WORD2VEC_MODEL'] = None
        app.config['NAIVE_BAYES_MODELS'] = {}
        models_loaded = True
        return
    
    logger.info("Starting model loading on application startup...")
    load_models()

# Call model loading function during application initialization
# This will be called when app is imported by gunicorn
# We'll use a request hook to ensure models are loaded on first request
@app.before_request
def load_models_on_first_request():
    """Load models when the first request is received"""
    global models_loaded_first_request
    
    # Only load models once on first request
    if not hasattr(app, 'models_loaded_first_request'):
        ensure_models_loaded()
        app.models_loaded_first_request = True

# Function to load models within app context with memory optimization
def load_models():
    """Load Word2Vec dan Naive Bayes models dengan optimasi memori dan timeout handling"""
    global word2vec_model, naive_bayes_models, models_loaded
    
    if models_loaded:
        return  # Models already loaded, no need to reload
    
    with app.app_context():
        try:
            from utils import load_word2vec_model, load_naive_bayes_models
            import gc
            import signal
            from threading import Thread
            import time
            
            # Load Word2Vec model dengan optimasi memori dan timeout
            app.logger.info("Starting Word2Vec model loading with memory optimization...")
            
            # Function untuk load Word2Vec dengan timeout
            word2vec_result = [None]
            def load_word2vec_with_timeout():
                try:
                    word2vec_result[0] = load_word2vec_model(app)
                except Exception as e:
                    app.logger.error(f"Error in Word2Vec loading thread: {e}")
            
            # Start loading thread
            word2vec_thread = Thread(target=load_word2vec_with_timeout)
            word2vec_thread.daemon = True
            word2vec_thread.start()
            
            # Wait for thread with timeout (5 menit)
            word2vec_thread.join(timeout=300)
            
            if word2vec_thread.is_alive():
                app.logger.error("Word2Vec model loading timeout after 5 minutes")
                word2vec_model = None
            elif word2vec_result[0] is None:
                app.logger.error("Failed to load Word2Vec model")
                word2vec_model = None
            else:
                word2vec_model = word2vec_result[0]
                app.logger.info("Word2Vec model loaded successfully with memory mapping")
                # Optimize memory usage after loading large model
                if hasattr(word2vec_model, 'wv'):
                    try:
                        word2vec_model.wv.init_sims(replace=True)
                        app.logger.info("Word2Vec model memory optimized")
                    except Exception as e:
                        app.logger.warning(f"Could not optimize Word2Vec memory: {e}")
            
            # Force garbage collection after loading large model
            gc.collect()
            
            # Load Naive Bayes models
            app.logger.info("Starting Naive Bayes models loading...")
            naive_bayes_models = load_naive_bayes_models()
            if not naive_bayes_models:
                app.logger.error("Failed to load Naive Bayes models")
            else:
                app.logger.info(f"Loaded {len(naive_bayes_models)} Naive Bayes models")
                
            # Set models in app config for global access
            app.config['WORD2VEC_MODEL'] = word2vec_model
            app.config['NAIVE_BAYES_MODELS'] = naive_bayes_models
            
            # Mark models as loaded
            models_loaded = True
            
            # Final garbage collection
            gc.collect()
            app.logger.info("All models loaded and memory optimized")
            
        except MemoryError:
            app.logger.error("Memory error: Word2Vec model too large for available memory")
            word2vec_model = None
            naive_bayes_models = {}
        except Exception as e:
            app.logger.error(f"Error loading models: {str(e)}")
            word2vec_model = None
            naive_bayes_models = {}

# Function to force reload models (for admin use)
def force_reload_models():
    """Force reload semua model machine learning"""
    global word2vec_model, naive_bayes_models, models_loaded
    
    app.logger.info("Force reloading all ML models...")
    
    # Reset loaded status
    models_loaded = False
    
    # Clear existing models from memory
    word2vec_model = None
    naive_bayes_models = {}
    
    # Force garbage collection
    import gc
    gc.collect()
    
    # Load models again
    load_models()
    
    return {
        'success': models_loaded,
        'word2vec_loaded': word2vec_model is not None,
        'naive_bayes_loaded': len(naive_bayes_models) > 0,
        'message': 'Models reloaded successfully' if models_loaded else 'Failed to reload models'
    }



# Models already imported above

# Register template filters with error handling
try:
    from utils import format_datetime
    app.jinja_env.filters['format_datetime'] = format_datetime
    logger.info("Template filter 'format_datetime' registered successfully")
except ImportError as e:
    logger.error(f"Failed to import format_datetime: {e}")
    # Fallback filter
    def fallback_format_datetime(dt, format_type='default'):
        try:
            if not dt:
                return '-'
            return str(dt)
        except:
            return '-'
    app.jinja_env.filters['format_datetime'] = fallback_format_datetime
    logger.info("Fallback format_datetime filter registered")
except Exception as e:
    logger.error(f"Error registering format_datetime filter: {e}")

# Add global error handler for template rendering
@app.errorhandler(500)
def internal_error(error):
    logger.error(f"Internal server error: {error}")
    return render_template('errors/500.html'), 500

@app.errorhandler(415)
def unsupported_media_type(error):
    logger.error(f"Unsupported Media Type error: {error}")
    return render_template('errors/404.html'), 415

@app.errorhandler(404)
def not_found_error(error):
    logger.error(f"Page not found: {error}")
    return render_template('errors/404.html'), 404

@login_manager.user_loader
def load_user(user_id):
    from models import User
    return User.query.get(int(user_id))

# Initialize routes
from routes import init_routes
init_routes(app, word2vec_model, naive_bayes_models)

# Register OTP blueprint
app.register_blueprint(otp_bp, url_prefix='/otp')

logger.info("OTP authentication blueprint registered with rate limiting")

if __name__ == '__main__':
    
    # Load models only once when application starts (not during reloads)
    disable_model_loading = os.environ.get('DISABLE_MODEL_LOADING', 'False').lower() == 'true'
    if disable_model_loading:
        logger.info("Model loading is disabled via DISABLE_MODEL_LOADING environment variable")
        # Explicitly set models to None/empty in app config for route usage
        app.config['WORD2VEC_MODEL'] = None
        app.config['NAIVE_BAYES_MODELS'] = {}
    else:
        load_models()
    
    # Start automatic cleanup scheduler
    cleanup_scheduler.start_scheduler()
    logger.info("Automatic data cleanup scheduler started")
    
    try:
        # Use debug mode from environment variable
        debug_mode = os.environ.get('FLASK_DEBUG', 'False').lower() == 'true'
        
        # Untuk development, gunakan reloader yang lebih stabil
        # use_reloader=False akan menonaktifkan restart otomatis
        # atau gunakan reloader type yang lebih baik
        app.run(
            debug=debug_mode, 
            host='0.0.0.0', 
            port=5000,
            use_reloader=debug_mode,  # Hanya aktifkan reloader jika debug mode
            reloader_type='stat' if debug_mode else 'auto'  # Gunakan stat untuk lebih stabil
        )
    except KeyboardInterrupt:
        logger.info("Shutting down application...")
        cleanup_scheduler.stop_scheduler()
        logger.info("Cleanup scheduler stopped")