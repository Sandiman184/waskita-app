from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy()

class User(UserMixin, db.Model):
    __tablename__ = 'users'
    
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    full_name = db.Column(db.String(255), nullable=True)
    bio = db.Column(db.Text, nullable=True)
    preferences = db.Column(db.JSON, nullable=True)  # Store user preferences as JSON
    role = db.Column(db.String(20), default='user')  # 'admin' or 'user'
    is_active = db.Column(db.Boolean, default=True)
    last_login = db.Column(db.DateTime, nullable=True)
    first_login = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
    
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)
    
    def is_admin(self):
        return self.role == 'admin'
    
    def get_preferences(self):
        """Get user preferences with default values"""
        default_preferences = {
            'language': 'id',
            'timezone': 'Asia/Jakarta',
            'items_per_page': 25,
            'email_notifications': True,
            'auto_refresh': False,
            'dark_mode': False,
            'compact_view': False
        }
        if self.preferences:
            default_preferences.update(self.preferences)
        return default_preferences
    
    def set_preferences(self, preferences_dict):
        """Update user preferences"""
        current_prefs = self.get_preferences()
        current_prefs.update(preferences_dict)
        self.preferences = current_prefs
    
    def __repr__(self):
        return f'<User {self.username}>'

class Dataset(db.Model):
    __tablename__ = 'datasets'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), nullable=False)
    description = db.Column(db.Text)
    uploaded_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    total_records = db.Column(db.Integer, default=0)
    cleaned_records = db.Column(db.Integer, default=0)
    classified_records = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    user = db.relationship('User', backref=db.backref('datasets', lazy=True))
    
    def __repr__(self):
        return f'<Dataset {self.name}>'

class RawData(db.Model):
    __tablename__ = 'raw_data'
    
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(255), nullable=False)
    content = db.Column(db.Text, nullable=False)
    url = db.Column(db.Text, nullable=True)
    platform = db.Column(db.String(50), nullable=False)  # twitter, tiktok, facebook
    source_type = db.Column(db.String(20), default='upload')  # upload or scraping
    status = db.Column(db.String(20), default='raw')  # raw, cleaned
    file_size = db.Column(db.BigInteger, nullable=True)  # File size in bytes
    original_filename = db.Column(db.String(255), nullable=True)  # Original uploaded filename
    dataset_id = db.Column(db.Integer, db.ForeignKey('datasets.id'), nullable=True)
    dataset_name = db.Column(db.String(255), nullable=True)  # For backward compatibility
    uploaded_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    
    user = db.relationship('User', backref=db.backref('raw_data', lazy=True))
    dataset = db.relationship('Dataset', backref=db.backref('raw_data', lazy=True))
    
    def __repr__(self):
        return f'<RawData {self.id} - {self.platform}>'

class RawDataScraper(db.Model):
    __tablename__ = 'raw_data_scraper'
    
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(255), nullable=False)
    content = db.Column(db.Text, nullable=False)
    url = db.Column(db.Text, nullable=True)
    platform = db.Column(db.String(50), nullable=False)  # twitter, tiktok, facebook
    keyword = db.Column(db.String(255), nullable=False)
    scrape_date = db.Column(db.Date, nullable=False)
    status = db.Column(db.String(20), default='raw')  # raw, cleaned
    dataset_id = db.Column(db.Integer, db.ForeignKey('datasets.id'), nullable=True)
    dataset_name = db.Column(db.String(255), nullable=True)  # For backward compatibility
    scraped_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    # Engagement fields for social media data
    likes = db.Column(db.Integer, nullable=True, default=0)
    retweets = db.Column(db.Integer, nullable=True, default=0)  # Twitter
    replies = db.Column(db.Integer, nullable=True, default=0)   # Twitter
    comments = db.Column(db.Integer, nullable=True, default=0)  # Facebook, Instagram, TikTok
    shares = db.Column(db.Integer, nullable=True, default=0)    # Facebook, Instagram, TikTok
    views = db.Column(db.Integer, nullable=True, default=0)     # TikTok, Instagram
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    user = db.relationship('User', backref=db.backref('scraped_data', lazy=True))
    dataset = db.relationship('Dataset', backref=db.backref('scraped_data', lazy=True))
    
    def __repr__(self):
        return f'<RawDataScraper {self.id} - {self.platform}>'

class CleanDataUpload(db.Model):
    __tablename__ = 'clean_data_upload'
    
    id = db.Column(db.Integer, primary_key=True)
    raw_data_id = db.Column(db.Integer, db.ForeignKey('raw_data.id'), nullable=False)
    username = db.Column(db.String(255), nullable=False)
    content = db.Column(db.Text, nullable=False)
    cleaned_content = db.Column(db.Text, nullable=False)
    url = db.Column(db.Text, nullable=True)
    platform = db.Column(db.String(50), nullable=False)
    dataset_id = db.Column(db.Integer, db.ForeignKey('datasets.id'), nullable=True)
    cleaned_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    raw_data = db.relationship('RawData', backref=db.backref('clean_upload_data', lazy=True))
    dataset = db.relationship('Dataset', backref=db.backref('clean_upload_data', lazy=True))
    user = db.relationship('User', backref=db.backref('cleaned_upload_data', lazy=True))
    
    def __repr__(self):
        return f'<CleanDataUpload {self.id}>'

class CleanDataScraper(db.Model):
    __tablename__ = 'clean_data_scraper'
    
    id = db.Column(db.Integer, primary_key=True)
    raw_data_scraper_id = db.Column(db.Integer, db.ForeignKey('raw_data_scraper.id'), nullable=False)
    username = db.Column(db.String(255), nullable=False)
    content = db.Column(db.Text, nullable=False)
    cleaned_content = db.Column(db.Text, nullable=False)
    url = db.Column(db.Text, nullable=True)
    platform = db.Column(db.String(50), nullable=False)
    keyword = db.Column(db.String(255), nullable=False)
    dataset_id = db.Column(db.Integer, db.ForeignKey('datasets.id'), nullable=True)
    cleaned_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    raw_data_scraper = db.relationship('RawDataScraper')
    dataset = db.relationship('Dataset', backref=db.backref('clean_scraper_data', lazy=True))
    user = db.relationship('User')
    
    def __repr__(self):
        return f'<CleanDataScraper {self.id}>'

class ClassificationResult(db.Model):
    __tablename__ = 'classification_results'
    
    id = db.Column(db.Integer, primary_key=True)
    data_type = db.Column(db.String(20), nullable=False)  # 'upload' or 'scraper'
    data_id = db.Column(db.Integer, nullable=False)  # ID from clean_data_upload or clean_data_scraper
    model_name = db.Column(db.String(20), nullable=False)  # model1, model2, model3
    prediction = db.Column(db.String(20), nullable=False)  # radikal, non-radikal
    probability_radikal = db.Column(db.Float, nullable=False)
    probability_non_radikal = db.Column(db.Float, nullable=False)
    classified_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    # Manual correction fields
    is_corrected = db.Column(db.Boolean, default=False)  # Whether the result has been manually corrected
    corrected_prediction = db.Column(db.String(20), nullable=True)  # Manual correction: radikal, non-radikal
    corrected_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)  # Who made the correction
    corrected_at = db.Column(db.DateTime, nullable=True)  # When the correction was made
    
    user = db.relationship('User', foreign_keys=[classified_by], backref=db.backref('classifications', lazy=True))
    corrector = db.relationship('User', foreign_keys=[corrected_by], backref=db.backref('corrections', lazy=True))
    
    def __repr__(self):
        return f'<ClassificationResult {self.id} - {self.model_name}>'
    
    def get_final_prediction(self):
        """Get the final prediction (corrected if available, otherwise original)"""
        return self.corrected_prediction if self.is_corrected else self.prediction

class UserActivity(db.Model):
    __tablename__ = 'user_activities'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    action = db.Column(db.String(100), nullable=False)  # upload, scraping, cleaning, classification
    description = db.Column(db.Text, nullable=False)
    details = db.Column(db.Text, nullable=True)  # Additional details in JSON format
    icon = db.Column(db.String(50), default='fa-info-circle')
    color = db.Column(db.String(20), default='blue')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    user = db.relationship('User', backref=db.backref('activities', lazy=True, order_by='UserActivity.created_at.desc()'))
    
    def __repr__(self):
        return f'<UserActivity {self.id} - {self.action}>'
    
    def to_dict(self):
        return {
            'id': self.id,
            'action': self.action,
            'description': self.description,
            'details': self.details,
            'icon': self.icon,
            'color': self.color,
            'created_at': self.created_at,
            'user': self.user.username if self.user else None
        }

class DatasetStatistics(db.Model):
    __tablename__ = 'dataset_statistics'
    
    id = db.Column(db.Integer, primary_key=True)
    total_raw_upload = db.Column(db.Integer, default=0)
    total_raw_scraper = db.Column(db.Integer, default=0)
    total_clean_upload = db.Column(db.Integer, default=0)
    total_clean_scraper = db.Column(db.Integer, default=0)
    total_classified = db.Column(db.Integer, default=0)
    total_radikal = db.Column(db.Integer, default=0)
    total_non_radikal = db.Column(db.Integer, default=0)
    last_updated = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def __repr__(self):
        return f'<DatasetStatistics {self.id}>'