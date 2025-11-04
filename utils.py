from functools import wraps
import re
import string
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

# Load environment variables
try:
    from dotenv import load_dotenv
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

# Authorization decorators
def admin_required(f):
    """
    Decorator untuk memastikan hanya admin yang dapat mengakses route tertentu
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            flash('Silakan login terlebih dahulu.', 'error')
            return redirect(url_for('login'))
        
        if not current_user.is_admin():
            flash('Akses ditolak! Hanya admin yang dapat mengakses halaman ini.', 'error')
            return redirect(url_for('dashboard'))
        
        return f(*args, **kwargs)
    return decorated_function

def active_user_required(f):
    """
    Decorator untuk memastikan hanya user aktif yang dapat mengakses route tertentu
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            flash('Silakan login terlebih dahulu.', 'error')
            return redirect(url_for('login'))
        
        if not current_user.is_active:
            flash('Akun Anda tidak aktif. Silakan hubungi administrator.', 'error')
            return redirect(url_for('login'))
        
        return f(*args, **kwargs)
    return decorated_function

def clean_text(text):
    """
    Membersihkan teks dari karakter yang tidak diinginkan
    """
    if not text or pd.isna(text):
        return ""
    
    # Convert to string
    text = str(text)
    
    # Remove URLs
    text = re.sub(r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\(\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+', '', text)
    
    # Remove mentions (@username)
    text = re.sub(r'@[A-Za-z0-9_]+', '', text)
    
    # Remove hashtags (#hashtag)
    text = re.sub(r'#[A-Za-z0-9_]+', '', text)
    
    # Remove emojis
    emoji_pattern = re.compile("["
                               u"\U0001F600-\U0001F64F"  # emoticons
                               u"\U0001F300-\U0001F5FF"  # symbols & pictographs
                               u"\U0001F680-\U0001F6FF"  # transport & map symbols
                               u"\U0001F1E0-\U0001F1FF"  # flags (iOS)
                               u"\U00002702-\U000027B0"
                               u"\U000024C2-\U0001F251"
                               "]+", flags=re.UNICODE)
    text = emoji_pattern.sub(r'', text)
    
    # Remove extra whitespace
    text = re.sub(r'\s+', ' ', text)
    
    # Remove punctuation
    text = text.translate(str.maketrans('', '', string.punctuation))
    
    # Convert to lowercase
    text = text.lower().strip()
    
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
        from models import CleanDataUpload, CleanDataScraper, RawDataScraper
        
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

def preprocess_for_word2vec(text):
    """
    Preprocessing khusus untuk Word2Vec
    """
    cleaned_text = clean_text(text)
    
    # Split into words
    words = cleaned_text.split()
    
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
            if word in word2vec_model.wv:
                word_vectors.append(word2vec_model.wv[word])
        except KeyError:
            continue
    
    if not word_vectors:
        return np.zeros(vector_size)
    
    # Average the word vectors
    text_vector = np.mean(word_vectors, axis=0)
    
    return text_vector

def classify_content(text_vector, naive_bayes_model):
    """
    Klasifikasi konten menggunakan model Naive Bayes
    """
    try:
        # Check for None values
        if text_vector is None or naive_bayes_model is None:
            return 'non-radikal', [0.0, 1.0]  # [prob_radikal, prob_non_radikal]
        
        # Handle array comparison issue
        if hasattr(text_vector, 'size') and text_vector.size == 0:
            return 'non-radikal', [0.0, 1.0]  # [prob_radikal, prob_non_radikal]
        
        # Handle zero vector (when no words found in vocabulary)
        if hasattr(text_vector, 'any') and not np.any(text_vector):
            return 'non-radikal', [0.0, 1.0]  # [prob_radikal, prob_non_radikal]
        
        # Check if model has predict_proba method
        if not hasattr(naive_bayes_model, 'predict_proba'):
            return 'non-radikal', [0.0, 1.0]  # [prob_radikal, prob_non_radikal]
        
        # Reshape vector for prediction
        vector_reshaped = text_vector.reshape(1, -1)
        
        # Make prediction
        prediction = naive_bayes_model.predict(vector_reshaped)[0]
        probabilities = naive_bayes_model.predict_proba(vector_reshaped)[0]
        
        # Convert prediction to readable format
        # Model returns 'Non-Radikal' or 'Radikal' directly
        prediction_str = str(prediction)
        if prediction_str == 'Radikal':
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

def load_word2vec_model():
    """
    Load Word2Vec model from configured path
    """
    if not GENSIM_AVAILABLE:
        return None
        
    try:
        from flask import current_app
        import os
        
        # Get model path from config
        model_path = current_app.config.get('WORD2VEC_MODEL_PATH')
        
        if not model_path:
            return None
            
        if not os.path.exists(model_path):
            return None
            
        from gensim.models import Word2Vec
        model = Word2Vec.load(model_path)
        return model
        
    except Exception as e:
        return None

def load_naive_bayes_models():
    """Load all three Naive Bayes models"""
    models = {}
    try:
        from flask import current_app
        
        # Get model paths from config
        model_paths = {
            'model1': current_app.config.get('NAIVE_BAYES_MODEL1_PATH'),
            'model2': current_app.config.get('NAIVE_BAYES_MODEL2_PATH'),
            'model3': current_app.config.get('NAIVE_BAYES_MODEL3_PATH')
        }
        
        # Load each model
        for model_name, model_path in model_paths.items():
            if model_path and os.path.exists(model_path):
                try:
                    with open(model_path, 'rb') as f:
                        models[model_name] = pickle.load(f)
                except Exception as e:
                    pass
            
        return models
    except Exception as e:
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
            'facebook': os.getenv('APIFY_FACEBOOK_ACTOR', 'apify/facebook-scraper'),
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


def start_apify_actor(platform, keyword, date_from=None, date_to=None, max_results=25, instagram_params=None):
    """
    Start Apify actor for specific platform with improved error handling and retry mechanism
    """
    config = get_apify_config()
    
    actor_id = config['actors'].get(platform.lower())
    if not actor_id:
        raise Exception(f"Actor tidak dikonfigurasi untuk platform: {platform}. Silakan hubungi administrator untuk mengatur konfigurasi actor.")
    
    # Prepare input based on platform
    input_data = prepare_actor_input(platform, keyword, date_from, date_to, max_results, instagram_params)
    
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


def prepare_actor_input(platform, keyword, date_from=None, date_to=None, max_results=25, instagram_params=None):
    """
    Prepare input data for different platform actors
    Sesuaikan parameter dengan kebutuhan masing-masing actor Apify
    """
    
    if platform.lower() == 'twitter':
        # Format input untuk kaitoeasyapi/twitter-x-data-tweet-scraper-pay-per-result-cheapest
        # Berdasarkan dokumentasi resmi Apify, gunakan searchTerms dengan format yang benar
        search_query = keyword
        
        # Tambahkan filter tanggal ke dalam search query jika disediakan
        if date_from and date_to:
            # Format: "keyword since:YYYY-MM-DD until:YYYY-MM-DD"
            search_query = f"{keyword} since:{date_from} until:{date_to}"
        elif date_from:
            search_query = f"{keyword} since:{date_from}"
        elif date_to:
            search_query = f"{keyword} until:{date_to}"
            
        input_data = {
            "searchTerms": [search_query],
            "lang": "in",  # Bahasa Indonesia (sesuai dengan nilai yang diizinkan Apify)
            "sort": "Latest",  # Urutkan berdasarkan terbaru
            "maxItems": max_results,  # Sesuaikan dengan input Maksimal Hasil dari UI
            "includeSearchTerms": False,  # Jangan sertakan search terms dalam hasil
            "onlyImage": False,  # Tidak hanya gambar
            "onlyQuote": False,  # Tidak hanya quote tweets
            "onlyTwitterBlue": False,  # Tidak hanya Twitter Blue users
            "onlyVerifiedUsers": False,  # Tidak hanya verified users
            "onlyVideo": False,  # Tidak hanya video
            "tweetLanguage": "in"  # Bahasa Indonesia untuk tweet
        }
        
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
                print(f"Apify run {run_id} status: {status}")
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
            print(f"Error checking status: {e}")
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


def scrape_with_apify(platform, keyword, date_from=None, date_to=None, max_results=25, instagram_params=None):
    """
    Main function to scrape data using Apify API with comprehensive error handling
    """
    try:
        print(f"Starting Apify scraping for {platform} with keyword: {keyword}")
        
        # Start the actor
        run_id, initial_status = start_apify_actor(platform, keyword, date_from, date_to, max_results, instagram_params)
        print(f"Apify actor started with run ID: {run_id}, initial status: {initial_status}")
        
        # Wait for completion
        print("Waiting for scraping to complete...")
        success, final_status = wait_for_apify_completion(run_id)
        print(f"Scraping completed with status: {final_status}")
        
        if success:
            # Get results
            print("Retrieving scraping results...")
            raw_results = get_apify_run_results(run_id)
            print(f"Retrieved {len(raw_results)} raw results")
            
            if raw_results and len(raw_results) > 0:
                print("Processing results...")
                # Process results based on platform
                processed_results = process_apify_results(raw_results, platform, max_results)
                print(f"Processed {len(processed_results)} results")
                
                return processed_results, run_id
            else:
                raise Exception("Tidak ada data yang berhasil di-scrape. Coba dengan keyword yang berbeda atau periksa konfigurasi Apify.")
        else:
            print(f"Scraping failed: {final_status}")
            
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
        print(f"Scraping error: {e}")
        
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
                'Tanggal': result['created_at'].strftime('%Y-%m-%d %H:%M:%S') if result['created_at'] else '-'
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
    from models import UserActivity, db
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