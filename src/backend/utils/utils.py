from functools import wraps
import re
import string
import secrets
import numpy as np
import pandas as pd
from datetime import datetime, date
import requests
from bs4 import BeautifulSoup
import json
import pickle
import os
import time
import pytz
from flask import flash, redirect, url_for
from flask_login import current_user

# Timezone constants
JAKARTA_TZ = pytz.timezone('Asia/Jakarta')

def flatten_dict(d, parent_key='', sep='_'):
    """
    Recursively flattens a nested dictionary.
    Example: {'a': {'b': 1}} -> {'a_b': 1}
    """
    items = []
    for k, v in d.items():
        new_key = f"{parent_key}{sep}{k}" if parent_key else k
        if isinstance(v, dict):
            items.extend(flatten_dict(v, new_key, sep=sep).items())
        else:
            items.append((new_key, v))
    return dict(items)

def get_jakarta_time():
    """Get current time in Jakarta timezone"""
    return datetime.now(JAKARTA_TZ)

def format_datetime(value, format='medium'):
    """Format datetime to Jakarta timezone string with WIB suffix"""
    if value is None:
        return ""
    
    # If naive, assume UTC (or server local) and convert to Jakarta
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value)
        except ValueError:
            return value

    if value.tzinfo is None:
        # If it's naive, we might need to assume it's UTC if stored as UTC in DB
        # But let's check if we can make it aware first
        # For now, let's assume naive means UTC as is common in DBs
        value = pytz.utc.localize(value)
    
    # Convert to Jakarta
    jakarta_time = value.astimezone(JAKARTA_TZ)
    
    if format == 'full':
        return jakarta_time.strftime('%d %B %Y %H:%M:%S WIB')
    elif format == 'medium':
        return jakarta_time.strftime('%d %b %Y %H:%M WIB')
    elif format == 'short':
        return jakarta_time.strftime('%d/%m/%Y %H:%M')
    elif format == 'date':
        return jakarta_time.strftime('%d %B %Y')
    elif format == 'time':
        return jakarta_time.strftime('%H:%M WIB')
    else:
        return jakarta_time.strftime(format)


class DateTimeEncoder(json.JSONEncoder):
    """
    Custom JSON encoder untuk menangani objek datetime
    """
    def default(self, obj):
        if isinstance(obj, datetime):
            return obj.strftime('%Y-%m-%d %H:%M:%S')
        elif isinstance(obj, date):
            return obj.strftime('%Y-%m-%d')
        return super().default(obj)

def generate_otp(length=6):
    """Generate random OTP code"""
    return ''.join(secrets.choice(string.digits) for _ in range(length))

# Load environment variables
try:
    from dotenv import load_dotenv
    import os
    
    # Load environment variables from .env file (development only)
    if os.getenv('FLASK_ENV') == 'development':
        load_dotenv()
except ImportError:
    pass

# Try to import ML libraries, but don't fail if they're not available
try:
    from gensim.models import Word2Vec
    GENSIM_AVAILABLE = True
except ImportError:
    GENSIM_AVAILABLE = False
    pass

try:
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.naive_bayes import MultinomialNB
    SKLEARN_AVAILABLE = True
except ImportError:
    SKLEARN_AVAILABLE = False
    pass

try:
    from Sastrawi.Stemmer.StemmerFactory import StemmerFactory
    SASTRAWI_AVAILABLE = True
except ImportError:
    SASTRAWI_AVAILABLE = False
    pass

# Authorization decorators
def admin_required(f):
    """
    Decorator untuk memastikan hanya admin yang dapat mengakses route tertentu
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            flash('Please login first.', 'error')
            return redirect(url_for('auth.login'))
        
        if not current_user.is_admin():
            flash('Access denied! Only admin can access this page.', 'error')
            return redirect(url_for('main.dashboard'))
        
        return f(*args, **kwargs)
    return decorated_function

def active_user_required(f):
    """
    Decorator untuk memastikan hanya user aktif yang dapat mengakses route tertentu
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            flash('Please login first.', 'error')
            return redirect(url_for('auth.login'))
        
        if not current_user.is_active:
            flash('Your account is inactive. Please contact administrator.', 'error')
            return redirect(url_for('auth.login'))
        
        return f(*args, **kwargs)
    return decorated_function

def check_dataset_permission(dataset, user):
    """
    Check if a user has permission to access/modify a dataset.
    Allowed if:
    1. User is Admin
    2. User is the uploader of the dataset
    3. User owns any RawData in the dataset
    4. User owns any RawDataScraper in the dataset
    """
    if not user or not user.is_authenticated:
        return False

    if user.is_admin():
        return True
        
    if dataset.uploaded_by == user.id:
        return True
        
    # Lazy import to avoid circular dependency
    from models.models import RawData, RawDataScraper
    
    # Check raw data ownership
    has_data = RawData.query.filter_by(dataset_id=dataset.id, uploaded_by=user.id).first()
    if has_data:
        return True
        
    # Check scraper data ownership
    has_scraper_data = RawDataScraper.query.filter_by(dataset_id=dataset.id, scraped_by=user.id).first()
    if has_scraper_data:
        return True
        
    return False

# Load resources for text processing
KAMUS_PATH = os.path.join(os.path.dirname(__file__), 'data', 'kamus.txt')
SLANG_PATH = os.path.join(os.path.dirname(__file__), 'data', 'slang.csv')

STOPWORDS = set()
STEMMER = None
LABEL_ENCODER = None

def load_text_processing_resources():
    global STOPWORDS, SLANG_DICT, STEMMER, LABEL_ENCODER
    try:
        # Load stopwords
        if os.path.exists(KAMUS_PATH):
            with open(KAMUS_PATH, 'r', encoding='utf-8') as f:
                STOPWORDS = set(line.strip().lower() for line in f if line.strip())
        
        # Load slang
        if os.path.exists(SLANG_PATH):
            # Try different encodings
            try:
                df_slang = pd.read_csv(SLANG_PATH, encoding='utf-8')
            except UnicodeDecodeError:
                df_slang = pd.read_csv(SLANG_PATH, encoding='latin-1')
                
            if 'slang' in df_slang.columns and 'formal' in df_slang.columns:
                SLANG_DICT = dict(zip(df_slang['slang'], df_slang['formal']))
        
        # Initialize Stemmer
        if SASTRAWI_AVAILABLE:
            try:
                factory = StemmerFactory()
                STEMMER = factory.create_stemmer()
            except Exception as e:
                print(f"Error initializing Sastrawi Stemmer: {e}")

        # Load Label Encoder
        from flask import current_app
        # We might not be in app context here, so we check env or default
        # But this function is called on import, so no current_app.
        # We'll load it lazily or try to find it.
        pass
            
    except Exception as e:
        print(f"Error loading text resources: {str(e)}")


# Load resources on module import
load_text_processing_resources()

def clean_text(text):
    """
    Membersihkan teks dari karakter yang tidak diinginkan dengan tahapan:
    1. Lowercase
    2. Hapus URL, mention, hashtag
    3. Hapus emoji
    4. Hapus angka & tanda baca
    5. Normalisasi slang
    6. Hapus stopwords
    """
    if not text or pd.isna(text):
        return ""
    
    # Convert to string
    text = str(text)
    
    # 1. Lowercase
    text = text.lower()
    
    # 2. Remove URLs
    text = re.sub(r'http\S+|www\S+|https\S+', '', text, flags=re.MULTILINE)
    
    # Remove mentions (@username)
    text = re.sub(r'@[A-Za-z0-9_]+', '', text)
    
    # Remove hashtags (#hashtag)
    text = re.sub(r'#[A-Za-z0-9_]+', '', text)
    
    # 3. Remove emojis
    # Expanded emoji range
    emoji_pattern = re.compile("["
                               u"\U0001F000-\U0001F9FF"  # Miscellaneous Symbols and Pictographs, Emoticons, etc.
                               u"\U00010000-\U0010FFFF"  # Supplementary Private Use Area-A & B (covers many emojis)
                               u"\U00002000-\U00002BFF"  # Various symbols including Dingbats
                               u"\U00002600-\U000026FF"  # Miscellaneous Symbols
                               u"\U00002700-\U000027BF"  # Dingbats
                               "]+", flags=re.UNICODE)
    text = emoji_pattern.sub(r'', text)
    
    # 4. Remove numbers
    text = re.sub(r'\d+', '', text)
    
    # Remove punctuation
    text = text.translate(str.maketrans('', '', string.punctuation))
    
    # Remove extra whitespace
    text = text.replace('\n', ' ').replace('\r', ' ').replace('\t', ' ')
    text = text.strip()
    text = re.sub(r'\s+', ' ', text)
    
    # Split into words for slang and stopwords
    words = text.split()
    processed_words = []
    
    for word in words:
        # 5. Normalisasi slang
        word = SLANG_DICT.get(word, word)
        
        # 6. Hapus stopwords
        if word not in STOPWORDS:
            processed_words.append(word)
    
    # Join back
    text = ' '.join(processed_words)
    
    return text

def check_content_duplicate(content, dataset_id=None):
    """
    Memeriksa apakah konten sudah ada dalam database untuk mencegah duplikasi
    """
    try:
        from models import RawData, RawDataScraper
        
        if not content or not str(content).strip():
            return False
        
        # Normalisasi konten untuk perbandingan yang lebih akurat
        normalized_content = str(content).strip()
        
        # Cek duplikasi di RawData berdasarkan konten yang sama persis
        if dataset_id:
            existing_upload = RawData.query.filter_by(
                dataset_id=dataset_id,
                content=normalized_content
            ).first()
            existing_scraper = RawDataScraper.query.filter_by(
                dataset_id=dataset_id,
                content=normalized_content
            ).first()
        else:
            existing_upload = RawData.query.filter_by(
                content=normalized_content
            ).first()
            existing_scraper = RawDataScraper.query.filter_by(
                content=normalized_content
            ).first()
        
        return existing_upload is not None or existing_scraper is not None
        
    except Exception as e:
        return False

def check_cleaned_content_duplicate(cleaned_content):
    """
    Memeriksa apakah konten yang sudah dibersihkan sudah ada dalam database
    untuk mencegah duplikasi di tabel clean data
    """
    try:
        from models import CleanDataUpload, CleanDataScraper
        
        if not cleaned_content:
            return False
        
        # Cek duplikasi di CleanDataUpload
        existing_clean_upload = CleanDataUpload.query.filter(
            CleanDataUpload.cleaned_content == cleaned_content
        ).first()
        
        # Cek duplikasi di CleanDataScraper
        existing_clean_scraper = CleanDataScraper.query.filter(
            CleanDataScraper.cleaned_content == cleaned_content
        ).first()
        
        return existing_clean_upload is not None or existing_clean_scraper is not None
        
    except Exception as e:
        return False

def check_cleaned_content_duplicate_by_dataset(cleaned_content, dataset_id):
    """
    Memeriksa apakah konten yang sudah dibersihkan sudah ada dalam database
    untuk dataset tertentu untuk mencegah duplikasi di tabel clean data
    """
    try:
        from models.models import CleanDataUpload, CleanDataScraper, RawDataScraper
        
        if not cleaned_content or not cleaned_content.strip():
            return False
        
        # Normalisasi konten untuk perbandingan yang lebih akurat
        normalized_content = cleaned_content.strip()
        
        # Cek duplikasi di CleanDataUpload untuk dataset tertentu
        existing_clean_upload = CleanDataUpload.query.filter_by(
            dataset_id=dataset_id,
            cleaned_content=normalized_content
        ).first()
        
        if existing_clean_upload:
            return True
        
        # Cek duplikasi di CleanDataScraper untuk dataset tertentu
        existing_clean_scraper = CleanDataScraper.query.join(
            RawDataScraper, CleanDataScraper.raw_data_scraper_id == RawDataScraper.id
        ).filter(
            RawDataScraper.dataset_id == dataset_id,
            CleanDataScraper.cleaned_content == normalized_content
        ).first()
        
        return existing_clean_scraper is not None
        
    except Exception as e:
        # Log error untuk debugging
        import logging
        logging.error(f"Error in check_cleaned_content_duplicate_by_dataset: {str(e)}")
        return False

def preprocess_for_model(text):
    """
    Preprocessing consistent with Training Notebook (3. Dataset Preprocessing.ipynb):
    1. Filter (Regex)
    2. Stopword Removal
    3. Stemming
    4. Slang Normalization (Corrected: Applied AFTER stemming as per notebook 3)
    """
    if not text or pd.isna(text):
        return ""
    
    # 1. Regex Filtering (Matching notebook's filtering_text)
    text = str(text).lower()
    text = re.sub(r'https?:\/\/\S+', '', text)
    text = ' '.join(re.sub(r"([@#][A-Za-z0-9]+)|(\w+:\/\/\S+)", " ", text).split())
    text = re.sub(r'(b\'{1,2})', "", text)
    text = re.sub('[^a-zA-Z]', ' ', text) # Only letters
    text = re.sub(r'\d+', '', text) # Digits
    text = text.translate(str.maketrans("", "", string.punctuation))
    text = re.sub(r'\s+', ' ', text).strip()
    
    # 2. Stopword Removal & 3. Stemming (Combined in notebook's stop_stem)
    # Note: In notebook, stopword removal is done BEFORE stemming.
    
    # Stopword Removal
    words = text.split()
    filtered_words = [word for word in words if word not in STOPWORDS]
    text = ' '.join(filtered_words)
    
    # Stemming
    if STEMMER:
        try:
            text = STEMMER.stem(text)
        except Exception:
            pass
            
    # 4. Slang Normalization (Applied on 'tweet_tokens' which is result of stop_stem)
    if SLANG_DICT:
        words = text.split()
        normalized_words = [SLANG_DICT.get(word, word) for word in words]
        text = ' '.join(normalized_words)
            
    return text

def preprocess_for_word2vec(text):
    """
    Preprocessing khusus untuk Word2Vec (Updated to match training)
    """
    # Use the model-specific preprocessing
    processed_text = preprocess_for_model(text)
    
    # Split into words
    words = processed_text.split()
    
    # Remove empty strings and single characters
    words = [word for word in words if len(word) > 1]
    
    return words

def vectorize_text(text, word2vec_model, vector_size=100):
    """
    Mengkonversi teks menjadi vektor menggunakan Word2Vec
    """
    if not text or not word2vec_model:
        return np.zeros(vector_size)
    
    words = preprocess_for_word2vec(text)
    
    if not words:
        return np.zeros(vector_size)
    
    # Get word vectors
    word_vectors = []
    for word in words:
        try:
            if hasattr(word2vec_model, 'wv'):
                kv = word2vec_model.wv
                if word in kv:
                    word_vectors.append(kv[word])
            else:
                # Assume KeyedVectors-like object
                if hasattr(word2vec_model, 'key_to_index'):
                    if word in word2vec_model.key_to_index:
                        word_vectors.append(word2vec_model[word])
                else:
                    # Fallback membership test
                    try:
                        if word in word2vec_model:
                            word_vectors.append(word2vec_model[word])
                    except Exception:
                        pass
        except Exception:
            continue
    
    if not word_vectors:
        return np.zeros(vector_size)
    
    # Average the word vectors
    text_vector = np.mean(word_vectors, axis=0)
    
    return text_vector

def classify_content(text_vector, model, text=None):
    """
    Klasifikasi konten menggunakan model klasifikasi (Naive Bayes, SVM, dll) atau IndoBERT
    
    Args:
        text_vector: Vector representation of text (for sklearn models)
        model: The model object
        text: Raw text (required for IndoBERT)
    """
    try:
        # Check for None values
        if model is None:
            return 'non-radikal', [0.0, 1.0]
            
        probabilities = None
        
        # Handle IndoBERT model specially
        from utils.indobert_utils import IndoBERTClassifier
        if isinstance(model, IndoBERTClassifier):
            if not text:
                return 'non-radikal', [0.0, 1.0]
            _, probabilities = model.predict(text)
            if probabilities is None:
                return 'non-radikal', [0.0, 1.0]
        else:
            # Standard sklearn models below
            if text_vector is None:
                return 'non-radikal', [0.0, 1.0]
            
            # Handle array comparison issue
            if hasattr(text_vector, 'size') and text_vector.size == 0:
                return 'non-radikal', [0.0, 1.0]
            
            # Handle zero vector (when no words found in vocabulary)
            if hasattr(text_vector, 'any') and not np.any(text_vector):
                return 'non-radikal', [0.0, 1.0]
            
            # Check if model has predict_proba method
            if not hasattr(model, 'predict_proba'):
                return 'non-radikal', [0.0, 1.0]
            
            # Reshape vector for prediction
            vector_reshaped = text_vector.reshape(1, -1)
            
            # Make prediction with probabilities
            probabilities = model.predict_proba(vector_reshaped)[0]
        
        # Get threshold from config
        from flask import current_app
        threshold = current_app.config.get('CLASSIFICATION_THRESHOLD', 0.5)
        
        # Determine index for 'Radikal'
        # Assume classes are sorted alphabetically or check model.classes_ if available
        radikal_index = 1 # Default assumption: ['Non-Radikal', 'Radikal'] or similar
        
        # For IndoBERT, we assume index 1 is Radikal based on its predict method logic
        if not isinstance(model, IndoBERTClassifier) and hasattr(model, 'classes_'):
            classes = list(model.classes_)
            # Find index of class that looks like 'Radikal'
            for i, cls in enumerate(classes):
                if str(cls).lower() == 'radikal':
                    radikal_index = i
                    break
        
        # Get probability of being Radikal
        prob_radikal = probabilities[radikal_index] if len(probabilities) > radikal_index else 0
        
        # Validation: If prob_radikal is very close to threshold, consider additional check or mark as uncertain
        # For now, we strictly follow the threshold
        
        # Apply threshold
        if prob_radikal >= threshold:
            prediction_label = 'radikal'
        else:
            prediction_label = 'non-radikal'
        
        return prediction_label, probabilities
        
    except Exception as e:
        # Log the error for debugging
        import traceback
        from flask import current_app
        current_app.logger.error(f"Error in classify_content: {str(e)}")
        current_app.logger.error(f"Traceback: {traceback.format_exc()}")
        return 'non-radikal', [0.0, 1.0]  # [prob_radikal, prob_non_radikal]

def load_word2vec_model(app=None):
    """
    Load Word2Vec model from configured path dengan optimasi memory mapping
    """
    if not GENSIM_AVAILABLE:
        if app:
            app.logger.error("Gensim not available - Word2Vec model cannot be loaded")
        else:
            print("Gensim not available - Word2Vec model cannot be loaded")
        return None
        
    try:
        import os
        
        # Get model path from config - either from provided app or current_app
        if app:
            model_path = app.config.get('WORD2VEC_MODEL_PATH')
        else:
            try:
                from flask import current_app
                model_path = current_app.config.get('WORD2VEC_MODEL_PATH')
            except RuntimeError:
                # No application context
                print("No application context for loading Word2Vec config")
                return None
        
        if not model_path:
            if app:
                app.logger.error("WORD2VEC_MODEL_PATH not configured")
            else:
                print("WORD2VEC_MODEL_PATH not configured")
            return None
            
        if not os.path.exists(model_path):
            if app:
                app.logger.error(f"File Word2Vec model tidak ditemukan: {model_path}")
            else:
                print(f"File Word2Vec model tidak ditemukan: {model_path}")
            return None
            
        from gensim.models import Word2Vec
        import joblib

        # Gunakan memory mapping untuk mengurangi beban memory
        if app:
            app.logger.info(f"Memuat Word2Vec model dari: {model_path}")

        ext = os.path.splitext(model_path)[1].lower()
        if ext == '.joblib':
            try:
                model = joblib.load(model_path)
            except Exception as e_joblib:
                if app:
                    app.logger.error(f"Joblib load gagal: {e_joblib}")
                return None
        else:
            try:
                model = Word2Vec.load(model_path, mmap='r')
            except Exception as e_gensim:
                if app:
                    app.logger.warning(f"Gensim load gagal ({e_gensim}), mencoba joblib...")
                try:
                    model = joblib.load(model_path)
                except Exception:
                    if app:
                        app.logger.error("Gagal memuat model Word2Vec dengan gensim maupun joblib")
                    return None
        
        if app:
            try:
                vocab_size = len(model.wv.key_to_index) if hasattr(model, 'wv') else len(getattr(model, 'key_to_index', {}))
            except Exception:
                vocab_size = 0
            app.logger.info(f"Word2Vec model berhasil dimuat. Vocabulary size: {vocab_size}")
        return model
        
    except Exception as e:
        if app:
            app.logger.error(f"Error loading Word2Vec model: {str(e)}")
            import traceback
            app.logger.error(f"Traceback: {traceback.format_exc()}")
        return None

from utils.indobert_utils import IndoBERTClassifier

def load_classification_models():
    """Load all 7 classification models including IndoBERT"""
    models = {}
    try:
        try:
            from flask import current_app
            config_source = current_app.config
            logger = current_app.logger
        except RuntimeError:
            # Fallback if no app context (e.g. during standalone testing)
            print("Warning: Running outside application context")
            # We need a way to get config. Assuming env vars or default config is enough?
            # Or we can pass config as argument?
            # For validate_pipeline.py, we might not have current_app.
            # Let's try to load from config.py directly if needed, or rely on caller to setup app context.
            # But validate_pipeline DOES setup app context.
            # The issue might be imports inside the function.
            return {}

        # Get model paths from config
        model_paths = {
            'naive_bayes': config_source.get('MODEL_NAIVE_BAYES_PATH'),
            'svm': config_source.get('MODEL_SVM_PATH'),
            'random_forest': config_source.get('MODEL_RANDOM_FOREST_PATH'),
            'logistic_regression': config_source.get('MODEL_LOGISTIC_REGRESSION_PATH'),
            'decision_tree': config_source.get('MODEL_DECISION_TREE_PATH'),
            'knn': config_source.get('MODEL_KNN_PATH')
        }
        
        # Load scikit-learn models
        for model_name, model_path in model_paths.items():
            if model_path and os.path.exists(model_path):
                try:
                    # Use joblib instead of pickle for better compatibility with sklearn models
                    import joblib
                    models[model_name] = joblib.load(model_path)
                    logger.info(f"Loaded model: {model_name}")
                except Exception as e:
                    logger.warning(f"Failed to load model {model_name}: {e}")
                    pass
            else:
                 logger.warning(f"Model path not found for {model_name}: {model_path}")
        
        # Load IndoBERT model
        indobert_path = config_source.get('MODEL_INDOBERT_PATH')
        if indobert_path:
            try:
                logger.info(f"Loading IndoBERT model from {indobert_path}...")
                indobert_model = IndoBERTClassifier(indobert_path)
                # Verify if loaded correctly (check if tokenizer/model are not None)
                if indobert_model.model and indobert_model.tokenizer:
                    models['indobert'] = indobert_model
                    logger.info("Loaded model: indobert")
                else:
                    logger.warning("IndoBERT model failed to initialize properly")
            except Exception as e:
                logger.warning(f"Failed to load IndoBERT model: {e}")
        
        # Load Label Encoder
        global LABEL_ENCODER
        try:
            import joblib
            le_path = config_source.get('LABEL_ENCODER_PATH')
            if le_path and os.path.exists(le_path):
                LABEL_ENCODER = joblib.load(le_path)
                logger.info(f"Loaded Label Encoder from {le_path}")
            else:
                logger.warning(f"Label Encoder path not found: {le_path}")
        except Exception as e:
            logger.warning(f"Failed to load Label Encoder: {e}")
        
        return models
    except Exception as e:
        print(f"Error loading classification models: {e}")
        return {}

# Function removed - replaced with scrape_with_apify for proper API integration
# def scrape_social_media(platform, keyword, scrape_date):
#     This function has been deprecated in favor of scrape_with_apify

def generate_sample_data(platform, keyword):
    """
    Generate sample data untuk testing dan fallback dengan data yang lebih realistis
    """
    import random
    from datetime import datetime, timedelta
    
    # Template konten yang lebih beragam berdasarkan platform
    if platform.lower() == 'twitter':
        sample_contents = [
            f"Trending sekarang: {keyword} 🔥 #viral",
            f"Thread tentang {keyword} yang perlu kalian baca 🧵",
            f"Breaking: Update terbaru mengenai {keyword}",
            f"Pendapat unpopular tentang {keyword}... RT jika setuju",
            f"Analisis mendalam: Mengapa {keyword} penting untuk masa depan",
            f"Live tweet dari event {keyword} hari ini 📱",
            f"Fact check: Mitos dan fakta tentang {keyword}",
            f"Poll: Bagaimana pendapat kalian tentang {keyword}? 🗳️"
        ]
        usernames = ['tech_insider', 'news_update', 'analyst_pro', 'trending_topic', 'social_buzz', 'info_center', 'daily_news', 'viral_content']
        base_url = 'https://twitter.com/status'
        
    elif platform.lower() == 'facebook':
        sample_contents = [
            f"Sharing artikel menarik tentang {keyword}. Apa pendapat teman-teman?",
            f"Event {keyword} minggu depan, siapa yang mau ikut?",
            f"Foto-foto dari workshop {keyword} kemarin. Seru banget! 📸",
            f"Diskusi grup: Bagaimana {keyword} mempengaruhi kehidupan kita?",
            f"Video tutorial {keyword} untuk pemula. Check it out!",
            f"Update status: Baru selesai belajar tentang {keyword}",
            f"Sharing pengalaman pribadi dengan {keyword}",
            f"Rekomendasi buku/artikel tentang {keyword} yang bagus"
        ]
        usernames = ['community_hub', 'learning_group', 'tech_community', 'discussion_forum', 'knowledge_share', 'social_network', 'group_admin', 'content_creator']
        base_url = 'https://facebook.com/posts'
        
    elif platform.lower() == 'instagram':
        sample_contents = [
            f"Beautiful shot dari event {keyword} hari ini ✨ #photography",
            f"Behind the scenes: Proses pembuatan konten {keyword} 🎬",
            f"Swipe untuk lihat tips {keyword} yang berguna ➡️",
            f"Story time: Pengalaman pertama dengan {keyword} 📖",
            f"Collaboration post tentang {keyword} dengan @partner",
            f"IGTV: Tutorial {keyword} step by step 🎥",
            f"Reels: Quick tips {keyword} dalam 30 detik ⏰",
            f"Carousel post: 10 fakta menarik tentang {keyword} 📊"
        ]
        usernames = ['visual_creator', 'content_studio', 'creative_hub', 'photo_story', 'insta_tips', 'visual_diary', 'creative_mind', 'story_teller']
        base_url = 'https://instagram.com/p'
        
    elif platform.lower() == 'tiktok':
        sample_contents = [
            f"Viral dance challenge dengan tema {keyword} 💃 #challenge",
            f"Life hack {keyword} yang jarang orang tahu 🤯",
            f"Duet video: Reaksi terhadap trend {keyword} terbaru",
            f"Educational content: Belajar {keyword} dalam 60 detik 📚",
            f"Comedy skit tentang {keyword} yang relate banget 😂",
            f"Transformation video: Before vs after {keyword} ✨",
            f"POV: Ketika kamu pertama kali dengar tentang {keyword}",
            f"Trending sound + {keyword} content = viral combo 🎵"
        ]
        usernames = ['viral_creator', 'tiktok_star', 'content_king', 'trend_setter', 'creative_soul', 'video_maker', 'social_influencer', 'entertainment_hub']
        base_url = 'https://tiktok.com/@user/video'
        
    else:
        # Generic fallback
        sample_contents = [
            f"Diskusi menarik tentang {keyword} hari ini",
            f"Pendapat saya mengenai {keyword} adalah...",
            f"Berita terbaru tentang {keyword} sangat mengejutkan",
            f"Analisis mendalam tentang {keyword}",
            f"Update terkini mengenai {keyword}"
        ]
        usernames = ['user_1', 'user_2', 'user_3', 'user_4', 'user_5']
        base_url = f'https://{platform}.com/post'
    
    sample_data = []
    num_posts = random.randint(5, 12)  # Lebih banyak data sample
    
    for i in range(num_posts):
        # Generate random timestamp dalam 7 hari terakhir
        days_ago = random.randint(0, 7)
        hours_ago = random.randint(0, 23)
        minutes_ago = random.randint(0, 59)
        
        post_time = datetime.now() - timedelta(days=days_ago, hours=hours_ago, minutes=minutes_ago)
        
        # Generate engagement metrics yang realistis
        if platform.lower() == 'twitter':
            engagement = {
                'retweets': random.randint(0, 500),
                'likes': random.randint(0, 1000),
                'replies': random.randint(0, 100),
                'quotes': random.randint(0, 50)
            }
        elif platform.lower() == 'facebook':
            engagement = {
                'likes': random.randint(0, 200),
                'comments': random.randint(0, 50),
                'shares': random.randint(0, 30)
            }
        elif platform.lower() == 'instagram':
            engagement = {
                'likes': random.randint(0, 800),
                'comments': random.randint(0, 100),
                'saves': random.randint(0, 50)
            }
        elif platform.lower() == 'tiktok':
            engagement = {
                'likes': random.randint(0, 2000),
                'comments': random.randint(0, 200),
                'shares': random.randint(0, 100),
                'views': random.randint(1000, 50000)
            }
        else:
            engagement = {'likes': random.randint(0, 100)}
        
        post_data = {
            'username': random.choice(usernames),
            'content': random.choice(sample_contents),
            'url': f'{base_url}/{random.randint(100000, 999999)}',
            'created_at': post_time.strftime('%Y-%m-%d %H:%M:%S'),
            'platform': platform.lower(),
            **engagement  # Add engagement metrics
        }
        
        # Add platform-specific fields
        if platform.lower() == 'twitter':
            post_data.update({
                'tweet_id': str(random.randint(1000000000000000000, 9999999999999999999)),
                'language': random.choice(['id', 'en', 'ms']),
                'source': random.choice(['Twitter Web App', 'Twitter for Android', 'Twitter for iPhone'])
            })
        elif platform.lower() == 'instagram':
            post_data.update({
                'post_type': random.choice(['photo', 'video', 'carousel', 'reel']),
                'hashtags': [f'#{keyword}', '#trending', '#viral']
            })
        elif platform.lower() == 'tiktok':
            post_data.update({
                'video_duration': random.randint(15, 180),
                'music': f'Original sound - {post_data["username"]}'
            })
        
        sample_data.append(post_data)
    
    return sample_data

# Removed obsolete platform-specific scraping functions
# These functions have been replaced by the unified scrape_with_apify function
# which handles all platforms through proper Apify API integration


# Apify API Integration Functions
def get_apify_config():
    """
    Get Apify configuration from environment variables with validation
    """
    config = {
        'api_token': os.getenv('APIFY_API_TOKEN'),
        'base_url': os.getenv('APIFY_BASE_URL', 'https://api.apify.com/v2'),
        'actors': {
            'twitter': os.getenv('APIFY_TWITTER_ACTOR', 'kaitoeasyapi/twitter-x-data-tweet-scraper-pay-per-result-cheapest'),
            'facebook': os.getenv('APIFY_FACEBOOK_ACTOR', 'powerai/facebook-post-search-scraper'),
            'instagram': os.getenv('APIFY_INSTAGRAM_ACTOR', 'apify/instagram-scraper'),
            'tiktok': os.getenv('APIFY_TIKTOK_ACTOR', 'clockworks/free-tiktok-scraper')
        },
        'timeout': int(os.getenv('APIFY_TIMEOUT', '30')),  # Default 30 seconds
        'max_retries': int(os.getenv('APIFY_MAX_RETRIES', '3')),  # Default 3 retries
        'retry_delay': int(os.getenv('APIFY_RETRY_DELAY', '5'))  # Default 5 seconds delay
    }
    
    # Validate configuration
    if not config['api_token']:
        raise Exception("APIFY_API_TOKEN tidak dikonfigurasi. Silakan set environment variable APIFY_API_TOKEN.")
    
    return config


def start_apify_actor(platform, keyword, date_from=None, date_to=None, max_results=25, instagram_params=None, language='id'):
    """
    Start Apify actor for specific platform with improved error handling and retry mechanism
    """
    config = get_apify_config()
    
    actor_id = config['actors'].get(platform.lower())
    if not actor_id:
        raise Exception(f"Actor tidak dikonfigurasi untuk platform: {platform}. Silakan hubungi administrator untuk mengatur konfigurasi actor.")
    
    # Prepare input based on platform
    input_data = prepare_actor_input(platform, keyword, date_from, date_to, max_results, instagram_params, language)
    
    # Start actor run with retry mechanism
    url = f"{config['base_url']}/acts/{actor_id.replace('/', '~')}/runs"
    headers = {
        'Authorization': f"Bearer {config['api_token']}",
        'Content-Type': 'application/json'
    }
    
    last_error = None
    for attempt in range(config['max_retries']):
        try:
            response = requests.post(
                url, 
                json=input_data, 
                headers=headers, 
                timeout=config['timeout']
            )
            
            if response.status_code == 201:
                run_data = response.json()['data']
                return run_data['id'], run_data['status']
            else:
                error_text = response.text
                
                # Handle specific Apify errors with user-friendly messages
                if "actor-is-not-rented" in error_text.lower():
                    raise Exception("Apify Actor tidak tersedia. Free trial telah berakhir dan memerlukan subscription berbayar. Silakan hubungi administrator untuk mengaktifkan akun Apify berbayar.")
                elif "insufficient-credit" in error_text.lower() or "not enough credit" in error_text.lower():
                    raise Exception("Kredit Apify tidak mencukupi. Silakan hubungi administrator untuk menambah kredit Apify.")
                elif "invalid-token" in error_text.lower() or "unauthorized" in error_text.lower():
                    raise Exception("Token Apify tidak valid atau tidak memiliki akses. Silakan hubungi administrator untuk memeriksa konfigurasi API.")
                elif "actor-not-found" in error_text.lower():
                    raise Exception(f"Actor Apify untuk platform {platform} tidak ditemukan. Silakan hubungi administrator untuk memeriksa konfigurasi actor.")
                elif "rate limit" in error_text.lower():
                    if attempt < config['max_retries'] - 1:
                        time.sleep(config['retry_delay'] * (attempt + 1))  # Exponential backoff
                        continue
                    else:
                        raise Exception("Rate limit Apify tercapai. Silakan tunggu beberapa menit sebelum mencoba lagi.")
                else:
                    raise Exception(f"Gagal memulai scraping (HTTP {response.status_code}): {error_text}. Silakan coba lagi atau hubungi administrator jika masalah berlanjut.")
                    
        except requests.exceptions.Timeout:
            last_error = f"Timeout saat menghubungi Apify API (attempt {attempt + 1}/{config['max_retries']})"
            if attempt < config['max_retries'] - 1:
                time.sleep(config['retry_delay'])
                continue
        except requests.exceptions.ConnectionError:
            last_error = f"Gagal terhubung ke Apify API (attempt {attempt + 1}/{config['max_retries']})"
            if attempt < config['max_retries'] - 1:
                time.sleep(config['retry_delay'])
                continue
        except Exception as e:
            # Don't retry for configuration errors
            if "tidak dikonfigurasi" in str(e) or "tidak tersedia" in str(e) or "tidak mencukupi" in str(e):
                raise e
            last_error = str(e)
            if attempt < config['max_retries'] - 1:
                time.sleep(config['retry_delay'])
                continue
    
    # If we get here, all retries failed
    raise Exception(f"Gagal memulai scraping setelah {config['max_retries']} percobaan. Error terakhir: {last_error}")


def prepare_actor_input(platform, keyword, date_from=None, date_to=None, max_results=25, instagram_params=None, language='id'):
    """
    Prepare input data for different platform actors
    Sesuaikan parameter dengan kebutuhan masing-masing actor Apify
    """
    
    if platform.lower() == 'twitter':
        # Format input untuk kaitoeasyapi/twitter-x-data-tweet-scraper-pay-per-result-cheapest
        # Berdasarkan template default yang diharapkan oleh actor
        search_terms = []
        
        # Format searchTerms dengan since/until sesuai template default
        # Enforce lang:in as per user requirement
        search_term = f"{keyword} lang:in"
        
        # We ignore the language parameter logic now and enforce 'in'
             
        if date_from and date_to:
            # Konversi format tanggal dari UI (YYYY-MM-DD) ke format yang diharapkan actor
            search_term += f" since:{date_from}_00:00:00_UTC until:{date_to}_23:59:59_UTC"
        
        search_terms.append(search_term)
        
        # Format tanggal untuk since dan until parameters
        since_date = date_from + "_00:00:00_UTC" if date_from else "2021-12-31_23:59:59_UTC"
        until_date = date_to + "_23:59:59_UTC" if date_to else "2024-12-31_23:59:59_UTC"
        
        input_data = {
            # Parameter filter lengkap sesuai template default
            "filter:blue_verified": False,
            "filter:consumer_video": False,
            "filter:has_engagement": False,
            "filter:hashtags": False,
            "filter:images": False,
            "filter:links": False,
            "filter:media": False,
            "filter:mentions": False,
            "filter:native_video": False,
            "filter:nativeretweets": False,
            "filter:news": False,
            "filter:pro_video": False,
            "filter:quote": False,
            "filter:replies": False,
            "filter:safe": False,
            "filter:spaces": False,
            "filter:twimg": False,
            "filter:videos": False,
            "filter:vine": False,
            # Parameter utama
            "lang": "in",  # Parameter utama
            "searchTerms": search_terms,
            "since": since_date,
            "until": until_date,
            "maxItems": max_results,  # Sesuaikan dengan input Maksimal Hasil dari UI
            # Parameter tambahan untuk kompatibilitas
            "include:nativeretweets": False
        }
        
        # We do not use dynamic language parameter anymore
        
        # CATATAN PENTING: Actor ini memiliki batasan untuk akun gratis
        # Akun gratis Apify akan mendapat data dummy/demo maksimal 100-1000 hasil
        # Untuk mendapatkan data real, perlu upgrade ke akun berbayar Apify
        # Alternatif: gunakan actor lain seperti apidojo/tweet-scraper yang mungkin lebih baik untuk akun gratis
        
        return input_data
        
    elif platform.lower() == 'facebook':
        # Facebook Scraper format - parameter yang benar
        return {
            "startUrls": [
                {"url": f"https://www.facebook.com/search/posts/?q={keyword}"}
            ],
            "resultsLimit": max_results,  # Sesuaikan dengan input Maksimal Hasil
            "scrapeComments": False,
            "scrapeReactions": True,
            "onlyPostsFromPages": False,
            "useApifyProxy": True,
            "apifyProxyGroups": ["RESIDENTIAL"],
            "maxRequestRetries": 3,
            "requestTimeoutSecs": 60
        }
        
    elif platform.lower() == 'instagram':
        # Instagram Scraper - parameter berdasarkan dokumentasi resmi Apify
        # Menggunakan search untuk hashtag atau keyword
        base_params = {
            "search": keyword,
            "searchType": "hashtag" if keyword.startswith('#') else "hashtag",
            "searchLimit": max_results,  # Sesuaikan dengan input Maksimal Hasil
            "resultsType": "posts",
            "resultsLimit": max_results  # Sesuaikan dengan input Maksimal Hasil
        }
        
        # Jika ada parameter Instagram khusus dari frontend, gunakan itu
        if instagram_params:
            # Update dengan parameter khusus jika ada
            if instagram_params.get('search'):
                base_params["search"] = instagram_params['search']
            if instagram_params.get('searchType'):
                base_params["searchType"] = instagram_params['searchType']
            if instagram_params.get('searchLimit'):
                base_params["searchLimit"] = instagram_params.get('searchLimit', max_results)
            if instagram_params.get('resultsLimit'):
                base_params["resultsLimit"] = instagram_params.get('resultsLimit', max_results)
            
        return base_params
        
    elif platform.lower() == 'tiktok':
        # TikTok Scraper - parameter berdasarkan dokumentasi resmi Apify
        # Menggunakan hashtags sebagai parameter utama
        base_params = {
            "hashtags": [keyword.replace('#', '')],
            "resultsPerPage": max_results,  # Sesuaikan dengan input Maksimal Hasil
            "proxyCountryCode": "US",  # Gunakan proxy US untuk stabilitas
            "shouldDownloadCovers": False,
            "shouldDownloadSlideshowImages": False,
            "shouldDownloadSubtitles": False,
            "shouldDownloadVideos": False
        }
        
        return base_params
        
    else:
        # Default fallback untuk platform yang tidak dikenal
        return {
            'searchTerms': [keyword],
            'max_results': max_results
        }


def check_apify_run_status(run_id):
    """
    Check the status of an Apify actor run with improved error handling
    """
    config = get_apify_config()
    
    url = f"{config['base_url']}/actor-runs/{run_id}"
    headers = {
        'Authorization': f"Bearer {config['api_token']}"
    }
    
    try:
        response = requests.get(url, headers=headers, timeout=config['timeout'])
        
        if response.status_code == 200:
            return response.json()['data']
        elif response.status_code == 404:
            raise Exception(f"Run ID {run_id} tidak ditemukan. Mungkin run telah dihapus atau ID tidak valid.")
        else:
            raise Exception(f"Gagal mendapatkan status run (HTTP {response.status_code}): {response.text}")
            
    except requests.exceptions.Timeout:
        raise Exception("Timeout saat mengecek status Apify run. Silakan coba lagi.")
    except requests.exceptions.ConnectionError:
        raise Exception("Gagal terhubung ke Apify API untuk mengecek status. Periksa koneksi internet Anda.")


def get_apify_run_results(run_id):
    """
    Get results from completed Apify actor run with improved error handling
    """
    config = get_apify_config()
    
    url = f"{config['base_url']}/actor-runs/{run_id}/dataset/items"
    headers = {
        'Authorization': f"Bearer {config['api_token']}"
    }
    
    try:
        response = requests.get(url, headers=headers, timeout=config['timeout'] * 2)  # Longer timeout for results
        
        if response.status_code == 200:
            results = response.json()
            if not results:
                raise Exception("Tidak ada data yang berhasil di-scrape. Coba dengan keyword atau parameter yang berbeda.")
            return results
        elif response.status_code == 404:
            raise Exception(f"Data hasil scraping untuk run ID {run_id} tidak ditemukan.")
        else:
            raise Exception(f"Gagal mendapatkan hasil scraping (HTTP {response.status_code}): {response.text}")
            
    except requests.exceptions.Timeout:
        raise Exception("Timeout saat mengambil hasil scraping. Data mungkin terlalu besar, silakan coba dengan max_results yang lebih kecil.")
    except requests.exceptions.ConnectionError:
        raise Exception("Gagal terhubung ke Apify API untuk mengambil hasil. Periksa koneksi internet Anda.")


def wait_for_apify_completion(run_id, max_wait_time=300, check_interval=10):
    """
    Wait for Apify actor run to complete with better progress tracking
    """
    start_time = time.time()
    last_status = None
    
    while time.time() - start_time < max_wait_time:
        try:
            status_data = check_apify_run_status(run_id)
            status = status_data['status']
            
            # Log status changes
            if status != last_status:
                last_status = status
            
            if status == 'SUCCEEDED':
                return True, 'completed'
            elif status == 'FAILED':
                # Get failure reason if available
                failure_reason = status_data.get('statusMessage', 'Unknown error')
                return False, f'failed: {failure_reason}'
            elif status in ['ABORTED', 'TIMED-OUT']:
                return False, status.lower()
            
            time.sleep(check_interval)
            
        except Exception as e:
            # If we can't check status, wait a bit and try again
            time.sleep(check_interval)
    
    return False, 'timeout'


def get_apify_run_progress(run_id):
    """
    Get detailed progress information from Apify actor run
    Returns progress percentage, status, and other metrics
    """
    try:
        config = get_apify_config()
        
        # Get run status
        status_url = f"{config['base_url']}/actor-runs/{run_id}"
        headers = {'Authorization': f"Bearer {config['api_token']}"}
        
        response = requests.get(status_url, headers=headers)
        
        if response.status_code == 200:
            run_data = response.json()['data']
            
            # Calculate progress based on status and timing
            status = run_data['status']
            started_at = run_data.get('startedAt')
            finished_at = run_data.get('finishedAt')
            
            progress_info = {
                'run_id': run_id,
                'status': status,
                'progress_percentage': 0,
                'estimated_time_remaining': None,
                'items_processed': 0,
                'total_items_estimate': None,
                'started_at': started_at,
                'finished_at': finished_at
            }
            
            if status == 'RUNNING' and started_at:
                # Calculate progress based on elapsed time
                start_time = datetime.fromisoformat(started_at.replace('Z', '+00:00'))
                current_time = datetime.now(pytz.UTC)
                elapsed_seconds = (current_time - start_time).total_seconds()
                
                # Estimate progress (rough estimation)
                # Most scraping jobs take 30-120 seconds
                estimated_total_time = 90  # seconds
                progress_percentage = min(95, (elapsed_seconds / estimated_total_time) * 100)
                
                remaining_time = max(0, estimated_total_time - elapsed_seconds)
                
                progress_info.update({
                    'progress_percentage': progress_percentage,
                    'estimated_time_remaining': remaining_time,
                    'elapsed_time': elapsed_seconds
                })
                
            elif status == 'SUCCEEDED':
                progress_info['progress_percentage'] = 100
                
                # Try to get actual results count
                try:
                    results_url = f"{config['base_url']}/actor-runs/{run_id}/dataset/items"
                    results_response = requests.get(results_url, headers=headers)
                    if results_response.status_code == 200:
                        results = results_response.json()
                        progress_info['items_processed'] = len(results)
                        progress_info['total_items_estimate'] = len(results)
                except:
                    pass
                    
            elif status in ['FAILED', 'ABORTED', 'TIMED-OUT']:
                progress_info['progress_percentage'] = 0
                
            return progress_info
            
        else:
            raise Exception(f"Failed to get run progress: {response.text}")
            
    except Exception as e:
        return {
            'run_id': run_id,
            'status': 'ERROR',
            'progress_percentage': 0,
            'error': str(e)
        }

def abort_apify_run(run_id):
    """
    Abort a running Apify actor run
    Returns True if abort request was accepted
    """
    try:
        config = get_apify_config()
        abort_url = f"{config['base_url']}/actor-runs/{run_id}/abort"
        headers = {'Authorization': f"Bearer {config['api_token']}"}
        resp = requests.post(abort_url, headers=headers)
        return resp.status_code in (200, 202)
    except Exception:
        return False


def scrape_with_apify(platform, keyword, date_from=None, date_to=None, max_results=25, instagram_params=None, language='id'):
    """
    Main function to scrape data using Apify API with comprehensive error handling
    """
    try:
        # Start the actor
        run_id, initial_status = start_apify_actor(platform, keyword, date_from, date_to, max_results, instagram_params, language)
        
        # Wait for completion
        success, final_status = wait_for_apify_completion(run_id)
        
        if success:
            # Get results
            raw_results = get_apify_run_results(run_id)
            
            if raw_results and len(raw_results) > 0:
                # Process results based on platform
                processed_results = process_apify_results(raw_results, platform, max_results)
                
                return processed_results, run_id
            else:
                raise Exception("Tidak ada data yang berhasil di-scrape. Coba dengan keyword yang berbeda atau periksa konfigurasi Apify.")
        else:
            # Provide specific error messages based on failure type
            if "failed:" in final_status:
                raise Exception(f"Scraping gagal: {final_status.replace('failed:', '').strip()}")
            elif final_status == 'timeout':
                raise Exception("Scraping timeout. Proses memakan waktu terlalu lama. Coba dengan max_results yang lebih kecil atau keyword yang lebih spesifik.")
            elif final_status == 'aborted':
                raise Exception("Scraping dibatalkan oleh sistem Apify. Silakan coba lagi.")
            else:
                raise Exception(f"Scraping gagal dengan status: {final_status}")
            
    except Exception as e:
        # Enhanced error handling with specific Apify error messages
        error_message = str(e)
        
        # Check for specific Apify errors and provide user-friendly messages
        if "tidak dikonfigurasi" in error_message.lower():
            raise Exception("Konfigurasi Apify belum lengkap. Silakan hubungi administrator untuk mengatur konfigurasi Apify.")
        elif "actor-is-not-rented" in error_message.lower():
            raise Exception("Apify Actor tidak tersedia. Free trial telah berakhir dan memerlukan subscription berbayar. Silakan hubungi administrator untuk mengaktifkan akun Apify berbayar.")
        elif "insufficient-credit" in error_message.lower() or "not enough credit" in error_message.lower():
            raise Exception("Kredit Apify tidak mencukupi. Silakan hubungi administrator untuk menambah kredit Apify.")
        elif "invalid-token" in error_message.lower() or "unauthorized" in error_message.lower():
            raise Exception("Token Apify tidak valid atau tidak memiliki akses. Silakan hubungi administrator untuk memeriksa konfigurasi API.")
        elif "actor not configured" in error_message.lower():
            raise Exception(f"Platform {platform} belum dikonfigurasi untuk scraping. Silakan hubungi administrator.")
        elif "timeout" in error_message.lower():
            raise Exception("Koneksi ke Apify API timeout. Periksa koneksi internet Anda atau coba lagi nanti.")
        elif "connection" in error_message.lower():
            raise Exception("Gagal terhubung ke Apify API. Periksa koneksi internet Anda.")
        else:
            # Provide more user-friendly error message
            raise Exception(f"Terjadi kesalahan saat scraping: {error_message}")


def process_apify_results(raw_results, platform, max_results=None):
    """
    Process raw Apify results - tampilkan semua data untuk manual mapping
    User akan melakukan manual mapping untuk username, content text, dan URL
    """
    processed_data = []
    
    # Batasi jumlah hasil jika max_results diberikan
    if max_results and len(raw_results) > max_results:
        raw_results = raw_results[:max_results]
    
    for item in raw_results:
        try:
            # Tampilkan semua data yang dikembalikan dari Apify
            # User akan melakukan manual mapping nanti
            processed_item = {
                'platform': platform,
                'raw_data': item,  # Simpan semua data mentah
                # Coba ekstrak field umum yang mungkin ada
                'possible_username_fields': [],
                'possible_content_fields': [],
                'possible_url_fields': [],
                'possible_date_fields': []
            }
            
            # Platform-specific field mapping berdasarkan struktur Apify
            if platform.lower() == 'twitter':
                # Twitter fields berdasarkan dashboard Apify:
                # Tweet ID: id, Tweet URL: url, Content: text, Created At: createdAt
                # profilePicture: author.profilePicture, Retweets: retweetCount, dll.
                
                # Core Twitter fields
                processed_item['tweet_id'] = item.get('id', '')
                processed_item['tweet_url'] = item.get('url', '')
                processed_item['content'] = item.get('text', '')
                processed_item['created_at'] = item.get('createdAt', '')
                
                # Author information
                if 'author' in item and isinstance(item['author'], dict):
                    author = item['author']
                    processed_item['username'] = author.get('userName', author.get('name', ''))
                    processed_item['profile_picture'] = author.get('profilePicture', '')
                    processed_item['possible_username_fields'].append(f"author.userName: {author.get('userName', '')}")
                    processed_item['possible_username_fields'].append(f"author.name: {author.get('name', '')}")
                else:
                    # Fallback untuk username
                    twitter_username_keys = ['userName', 'user', 'screen_name', 'name']
                    for key in twitter_username_keys:
                        if key in item and item[key]:
                            processed_item['username'] = item[key]
                            processed_item['possible_username_fields'].append(f"{key}: {item[key]}")
                            break
                
                # Content fields untuk Twitter
                if processed_item['content']:
                    content_preview = str(processed_item['content'])[:100] + '...' if len(str(processed_item['content'])) > 100 else str(processed_item['content'])
                    processed_item['possible_content_fields'].append(f"text: {content_preview}")
                
                # URL fields untuk Twitter
                if processed_item['tweet_url']:
                    processed_item['url'] = processed_item['tweet_url']
                    processed_item['possible_url_fields'].append(f"url: {processed_item['tweet_url']}")
                elif processed_item['tweet_id']:
                    # Construct Twitter URL from ID if direct URL not available
                    twitter_url = f"https://twitter.com/i/web/status/{processed_item['tweet_id']}"
                    processed_item['url'] = twitter_url
                    processed_item['possible_url_fields'].append(f"constructed_url: {twitter_url}")
                
                # Date fields untuk Twitter
                if processed_item['created_at']:
                    processed_item['possible_date_fields'].append(f"createdAt: {processed_item['created_at']}")
                
                # Engagement metrics
                engagement_fields = {
                    'retweetCount': 'retweets',
                    'replyCount': 'replies', 
                    'likeCount': 'likes',
                    'quoteCount': 'quotes',
                    'viewCount': 'views',
                    'bookmarkCount': 'bookmarks'
                }
                for api_field, display_field in engagement_fields.items():
                    if api_field in item and item[api_field] is not None:
                        processed_item[api_field] = item[api_field]
                        processed_item[display_field] = item[api_field]
                
                # Twitter metadata
                metadata_fields = ['source', 'lang', 'isReply', 'isQuote', 'isPinned']
                for field in metadata_fields:
                    if field in item and item[field] is not None:
                        processed_item[field] = item[field]
                
                # Set language display
                if 'lang' in processed_item:
                    processed_item['language'] = processed_item['lang']
                        
            elif platform.lower() == 'facebook':
                # Facebook-specific field mapping
                # Facebook Scraper biasanya mengembalikan: text, url, time, authorName, etc.
                
                # Core Facebook fields
                processed_item['content'] = item.get('text', item.get('message', ''))
                processed_item['url'] = item.get('url', item.get('link', ''))
                processed_item['created_at'] = item.get('time', item.get('timestamp', ''))
                
                # Author information
                processed_item['username'] = item.get('authorName', item.get('author', item.get('user', '')))
                
                # Content fields untuk Facebook
                if processed_item['content']:
                    content_preview = str(processed_item['content'])[:100] + '...' if len(str(processed_item['content'])) > 100 else str(processed_item['content'])
                    processed_item['possible_content_fields'].append(f"text: {content_preview}")
                
                # URL fields untuk Facebook
                if processed_item['url']:
                    processed_item['possible_url_fields'].append(f"url: {processed_item['url']}")
                
                # Username fields untuk Facebook
                if processed_item['username']:
                    processed_item['possible_username_fields'].append(f"authorName: {processed_item['username']}")
                
                # Date fields untuk Facebook
                if processed_item['created_at']:
                    processed_item['possible_date_fields'].append(f"time: {processed_item['created_at']}")
                
                # Engagement metrics untuk Facebook
                engagement_fields = {
                    'likes': 'likes',
                    'comments': 'comments',
                    'shares': 'shares',
                    'reactions': 'reactions'
                }
                for api_field, display_field in engagement_fields.items():
                    if api_field in item and item[api_field] is not None:
                        processed_item[api_field] = item[api_field]
                        processed_item[display_field] = item[api_field]
                        
            elif platform.lower() == 'instagram':
                # Instagram-specific field mapping
                # Instagram Scraper biasanya mengembalikan: caption, url, timestamp, ownerUsername, etc.
                
                # Core Instagram fields
                processed_item['content'] = item.get('caption', item.get('text', item.get('description', '')))
                processed_item['url'] = item.get('url', item.get('shortcode', item.get('permalink', '')))
                processed_item['created_at'] = item.get('timestamp', item.get('taken_at_timestamp', item.get('date', '')))
                
                # Author information - Instagram biasanya menggunakan ownerUsername
                processed_item['username'] = item.get('ownerUsername', item.get('username', item.get('owner', '')))
                
                # Content fields untuk Instagram
                if processed_item['content']:
                    content_preview = str(processed_item['content'])[:100] + '...' if len(str(processed_item['content'])) > 100 else str(processed_item['content'])
                    processed_item['possible_content_fields'].append(f"caption: {content_preview}")
                
                # URL fields untuk Instagram
                if processed_item['url']:
                    processed_item['possible_url_fields'].append(f"url: {processed_item['url']}")
                
                # Username fields untuk Instagram
                if processed_item['username']:
                    processed_item['possible_username_fields'].append(f"ownerUsername: {processed_item['username']}")
                
                # Date fields untuk Instagram
                if processed_item['created_at']:
                    processed_item['possible_date_fields'].append(f"timestamp: {processed_item['created_at']}")
                
                # Engagement metrics untuk Instagram
                engagement_fields = {
                    'likesCount': 'likes',
                    'commentsCount': 'comments',
                    'videoViewCount': 'views'
                }
                for api_field, display_field in engagement_fields.items():
                    if api_field in item and item[api_field] is not None:
                        processed_item[api_field] = item[api_field]
                        processed_item[display_field] = item[api_field]
                        
            elif platform.lower() == 'tiktok':
                # TikTok-specific field mapping
                # TikTok Scraper biasanya mengembalikan: text, webVideoUrl, createTime, authorMeta, etc.
                
                # Core TikTok fields
                processed_item['content'] = item.get('text', item.get('desc', item.get('description', '')))
                processed_item['url'] = item.get('webVideoUrl', item.get('videoUrl', item.get('url', '')))
                processed_item['created_at'] = item.get('createTime', item.get('createTimeISO', item.get('timestamp', '')))
                
                # Author information - TikTok biasanya menggunakan authorMeta
                if 'authorMeta' in item and isinstance(item['authorMeta'], dict):
                    author_meta = item['authorMeta']
                    processed_item['username'] = author_meta.get('name', author_meta.get('uniqueId', ''))
                    processed_item['possible_username_fields'].append(f"authorMeta.name: {author_meta.get('name', '')}")
                    processed_item['possible_username_fields'].append(f"authorMeta.uniqueId: {author_meta.get('uniqueId', '')}")
                else:
                    # Fallback untuk username
                    processed_item['username'] = item.get('author', item.get('username', item.get('uniqueId', '')))
                
                # Content fields untuk TikTok
                if processed_item['content']:
                    content_preview = str(processed_item['content'])[:100] + '...' if len(str(processed_item['content'])) > 100 else str(processed_item['content'])
                    processed_item['possible_content_fields'].append(f"text: {content_preview}")
                
                # URL fields untuk TikTok
                if processed_item['url']:
                    processed_item['possible_url_fields'].append(f"webVideoUrl: {processed_item['url']}")
                
                # Username fields untuk TikTok
                if processed_item['username']:
                    processed_item['possible_username_fields'].append(f"authorMeta.name: {processed_item['username']}")
                
                # Date fields untuk TikTok
                if processed_item['created_at']:
                    processed_item['possible_date_fields'].append(f"createTime: {processed_item['created_at']}")
                
                # Engagement metrics untuk TikTok
                engagement_fields = {
                    'diggCount': 'likes',
                    'shareCount': 'shares',
                    'commentCount': 'comments',
                    'playCount': 'views'
                }
                for api_field, display_field in engagement_fields.items():
                    if api_field in item and item[api_field] is not None:
                        processed_item[api_field] = item[api_field]
                        processed_item[display_field] = item[api_field]
                
            else:
                # Generic field identification untuk platform lain
                username_keys = ['username', 'user', 'author', 'userName', 'ownerUsername', 'authorMeta', 'screen_name', 'name']
                for key in username_keys:
                    if key in item and item[key]:
                        if isinstance(item[key], dict):
                            # Jika nested object, cari di dalamnya
                            for nested_key in ['userName', 'name', 'username']:
                                if nested_key in item[key] and item[key][nested_key]:
                                    processed_item['possible_username_fields'].append(f"{key}.{nested_key}: {item[key][nested_key]}")
                        else:
                            processed_item['possible_username_fields'].append(f"{key}: {item[key]}")
                
                # Identifikasi field yang mungkin berisi content/text
                content_keys = ['text', 'content', 'caption', 'full_text', 'description', 'message', 'body']
                for key in content_keys:
                    if key in item and item[key]:
                        content_preview = str(item[key])[:100] + '...' if len(str(item[key])) > 100 else str(item[key])
                        processed_item['possible_content_fields'].append(f"{key}: {content_preview}")
                
                # Identifikasi field yang mungkin berisi URL
                url_keys = ['url', 'link', 'permalink', 'webVideoUrl', 'shortcode', 'post_url']
                for key in url_keys:
                    if key in item and item[key]:
                        processed_item['possible_url_fields'].append(f"{key}: {item[key]}")
                
                # Identifikasi field yang mungkin berisi tanggal
                date_keys = ['created_at', 'timestamp', 'time', 'createTime', 'date', 'published_at']
                for key in date_keys:
                    if key in item and item[key]:
                        processed_item['possible_date_fields'].append(f"{key}: {item[key]}")
            
            # Tambahkan field standar untuk kompatibilitas dengan sistem yang ada
            # Gunakan field pertama yang ditemukan sebagai default
            processed_item['username'] = ''
            processed_item['content'] = ''
            processed_item['url'] = ''
            processed_item['created_at'] = ''
            
            # Coba set default values dari field yang teridentifikasi
            if processed_item['possible_username_fields']:
                first_username = processed_item['possible_username_fields'][0].split(': ', 1)[1]
                processed_item['username'] = first_username
            
            if processed_item['possible_content_fields']:
                first_content = processed_item['possible_content_fields'][0].split(': ', 1)[1]
                processed_item['content'] = first_content.replace('...', '')  # Hapus truncation
                # Ambil content penuh dari raw data
                content_key = processed_item['possible_content_fields'][0].split(': ', 1)[0]
                if content_key in item:
                    processed_item['content'] = str(item[content_key])
            
            if processed_item['possible_url_fields']:
                first_url = processed_item['possible_url_fields'][0].split(': ', 1)[1]
                processed_item['url'] = first_url
            
            if processed_item['possible_date_fields']:
                first_date = processed_item['possible_date_fields'][0].split(': ', 1)[1]
                processed_item['created_at'] = first_date
            
            processed_data.append(processed_item)
            
        except Exception as e:
            pass
            # Tetap simpan item meskipun ada error
            processed_data.append({
                'platform': platform,
                'raw_data': item,
                'error': str(e),
                'username': '',
                'content': '',
                'url': '',
                'created_at': ''
            })
            continue
    
    return processed_data


# Fungsi scraper lama telah diganti dengan implementasi yang lebih baik di atas



def export_classification_results(results, format='csv'):
    """
    Export hasil klasifikasi ke file sesuai dengan tampilan UI
    """
    try:
        # Convert results to DataFrame sesuai dengan struktur UI
        data = []
        for result in results:
            row = {
                'ID': result['data_id'],
                'Username': result['username'],
                'Konten': result['content'][:100] + '...' if len(result['content']) > 100 else result['content'],
                'URL': result['url'],
                'Tipe Data': result['data_type'].title(),
                'Tanggal': result['created_at'].strftime('%d/%m/%Y %H:%M') if result['created_at'] else '-'
            }
            
            # Add model predictions
            for i in range(1, 4):
                model_key = f'model{i}'
                if model_key in result['models']:
                    model_data = result['models'][model_key]
                    row[f'Model {i} - Prediksi'] = model_data['prediction'].title()
                    row[f'Model {i} - Probabilitas Radikal (%)'] = f"{model_data['probability_radikal'] * 100:.1f}%"
                    row[f'Model {i} - Probabilitas Non-Radikal (%)'] = f"{model_data['probability_non_radikal'] * 100:.1f}%"
                else:
                    row[f'Model {i} - Prediksi'] = '-'
                    row[f'Model {i} - Probabilitas Radikal (%)'] = '-'
                    row[f'Model {i} - Probabilitas Non-Radikal (%)'] = '-'
            
            data.append(row)
        
        df = pd.DataFrame(data)
        
        # Generate filename
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        
        if format == 'csv':
            filename = f'hasil_klasifikasi_{timestamp}.csv'
            df.to_csv(filename, index=False, encoding='utf-8-sig')
        elif format == 'excel':
            filename = f'hasil_klasifikasi_{timestamp}.xlsx'
            df.to_excel(filename, index=False)
        
        return filename
        
    except Exception as e:
        pass
        return None



def format_datetime(dt, format_type='default'):
    """
    Format datetime untuk tampilan dengan konsistensi timezone WIB
    format_type: 'default', 'date_only', 'datetime', 'iso'
    """
    try:
        if not dt:
            return '-'
        
        if isinstance(dt, str):
            return dt
        
        # Setup timezone WIB
        wib_tz = pytz.timezone('Asia/Jakarta')
        
        formats = {
            'default': '%d-%m-%Y %H:%M WIB',
            'date': '%d-%m-%Y',
            'time': '%H:%M WIB',
            'date_only': '%d-%m-%Y', 
            'datetime': '%d-%m-%Y %H:%M WIB',
            'short': '%d/%m/%Y %H:%M WIB',
            'iso': '%Y-%m-%d %H:%M WIB',
            'display': '%d %b %Y %H:%M WIB',
            'display_date': '%d %b %Y'
        }
        
        format_str = formats.get(format_type, formats['default'])
        
        if isinstance(dt, datetime):
            # Jika datetime naive (tanpa timezone), anggap sebagai UTC
            if dt.tzinfo is None:
                dt = pytz.utc.localize(dt)
            
            # Konversi ke WIB
            dt_wib = dt.astimezone(wib_tz)
            return dt_wib.strftime(format_str)
        elif isinstance(dt, date):
            # Untuk date only, gunakan format tanpa waktu
            if format_type in ['default', 'datetime', 'iso']:
                format_str = format_str.split(' ')[0]  # Ambil bagian tanggal saja
            return dt.strftime(format_str)
        else:
            return str(dt)
    except Exception as e:
        pass
        return str(dt) if dt else '-'

def generate_activity_log(action, description, user_id, details=None, icon='fa-info-circle', color='blue'):
    """
    Generate log aktivitas pengguna dan simpan ke database
    """
    from models.models import UserActivity, db
    import json
    
    try:
        # Buat entry aktivitas baru
        activity = UserActivity(
            user_id=user_id,
            action=action,
            description=description,
            details=json.dumps(details) if details else None,
            icon=icon,
            color=color
        )
        
        db.session.add(activity)
        db.session.commit()
        
        pass
        
        return activity.to_dict()
        
    except Exception as e:
        pass
        db.session.rollback()
        
        # Fallback ke log sederhana
        log_entry = {
            'timestamp': datetime.now(),
            'user_id': user_id,
            'action': action,
            'description': description
        }
        
        pass
        return log_entry

def log_user_activity(user_id, action, description, details=None, icon='fa-info-circle', color='blue'):
    """
    Wrapper function untuk generate_activity_log dengan nama yang lebih sederhana
    """
    return generate_activity_log(action, description, user_id, details, icon, color)


def get_role_based_feedback(user, action_type, resource_owner_id=None, resource_name=None):
    """
    Fungsi helper untuk memberikan feedback yang konsisten berdasarkan role user
    
    Args:
        user: User object (current_user)
        action_type: Jenis aksi yang dilakukan (view, edit, delete, create, access)
        resource_owner_id: ID pemilik resource (opsional)
        resource_name: Nama resource yang diakses (opsional)
    
    Returns:
        Tuple (message, category, http_status)
    """
    
    # Check language preference - Disabled to enforce standard language
    # lang = 'id'
    # try:
    #     if user and user.is_authenticated:
    #         lang = user.get_preferences().get('language', 'id')
    # except:
    #     pass

    # Standardize to English for feedback messages as requested
    action_messages = {
        'view': 'view',
        'edit': 'edit',
        'delete': 'delete',
        'create': 'create',
        'access': 'access'
    }
    action_text = action_messages.get(action_type, 'access')
    resource_text = f' {resource_name}' if resource_name else ''
    
    if user.is_admin():
        if action_type == 'access':
            return ('Access granted as administrator', 'info', 200)
        else:
            return (f'Successfully {action_text} {resource_text}', 'success', 200)
    
    elif resource_owner_id and user.id != resource_owner_id:
        if action_type == 'view':
            message = f'You do not have permission to {action_text} this data. Only admin or owner can {action_text} data.'
        else:
            message = f'Access denied! You do not have permission to {action_text} this data.'
        return (message, 'error', 403)
    
    else:
        if action_type == 'access':
            return ('Access granted', 'info', 200)
        else:
            return (f'Successfully {action_text} {resource_text}', 'success', 200)


def api_role_based_response(user, action_type, resource_owner_id=None, resource_name=None):
    """
    Fungsi helper untuk memberikan response API yang konsisten berdasarkan role user
    
    Args:
        user: User object (current_user)
        action_type: Jenis aksi yang dilakukan
        resource_owner_id: ID pemilik resource
        resource_name: Nama resource yang diakses
    
    Returns:
        Tuple (success, message, http_status)
    """
    
    message, category, http_status = get_role_based_feedback(user, action_type, resource_owner_id, resource_name)
    
    if category == 'error':
        return False, message, http_status
    else:
        return True, message, http_status


def check_permission_with_feedback(user, resource_owner_id, action_type, resource_name=None):
    """
    Fungsi untuk mengecek permission dan memberikan feedback yang sesuai
    
    Returns:
        Tuple (has_permission, message, http_status)
    """
    
    if user.is_admin():
        # Admin memiliki akses penuh
        return True, None, 200
    
    elif user.id == resource_owner_id:
        # User adalah pemilik resource
        return True, None, 200
    
    else:
        # User tidak memiliki akses
        message, category, http_status = get_role_based_feedback(user, action_type, resource_owner_id, resource_name)
        return False, message, http_status
