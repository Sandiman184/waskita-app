import os
import logging
import locale
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, session
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from flask_wtf.csrf import CSRFProtect
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from datetime import datetime
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv(override=True)  # Use override=True to ensure .env values take precedence

# Routes will be initialized using init_routes function
from models import db, User
from models_otp import RegistrationRequest, AdminNotification, OTPEmailLog
from otp_routes import otp_bp
from config import Config

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('waskita.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.config.from_object(Config)

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

# Create upload directory if it doesn't exist
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# Create database tables
with app.app_context():
    db.create_all()

# Initialize model variables
word2vec_model = None
naive_bayes_models = {}

# Function to load models within app context
def load_models():
    """Load Word2Vec dan Naive Bayes models"""
    global word2vec_model, naive_bayes_models
    with app.app_context():
        try:
            from utils import load_word2vec_model, load_naive_bayes_models
            
            # Load Word2Vec model
            word2vec_model = load_word2vec_model()
            if word2vec_model is None:
                app.logger.error("Failed to load Word2Vec model")
            else:
                app.logger.info("Word2Vec model loaded successfully")
            
            # Load Naive Bayes models
            naive_bayes_models = load_naive_bayes_models()
            if not naive_bayes_models:
                app.logger.error("Failed to load Naive Bayes models")
            else:
                app.logger.info(f"Loaded {len(naive_bayes_models)} Naive Bayes models")
                
            # Set models in app config for global access
            app.config['WORD2VEC_MODEL'] = word2vec_model
            app.config['NAIVE_BAYES_MODELS'] = naive_bayes_models
            
        except Exception as e:
            app.logger.error(f"Error loading models: {str(e)}")
            word2vec_model = None
            naive_bayes_models = {}

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

# Load models and initialize routes
load_models()
from routes import init_routes
init_routes(app, word2vec_model, naive_bayes_models)

# Register OTP blueprint
app.register_blueprint(otp_bp, url_prefix='/otp')

logger.info("OTP authentication blueprint registered with rate limiting")

if __name__ == '__main__':
    
    # Start automatic cleanup scheduler
    cleanup_scheduler.start_scheduler()
    logger.info("Automatic data cleanup scheduler started")
    
    try:
        # Use debug mode from environment variable
        debug_mode = os.environ.get('FLASK_DEBUG', 'False').lower() == 'true'
        app.run(debug=debug_mode, host='0.0.0.0', port=5000)
    except KeyboardInterrupt:
        logger.info("Shutting down application...")
        cleanup_scheduler.stop_scheduler()
        logger.info("Cleanup scheduler stopped")