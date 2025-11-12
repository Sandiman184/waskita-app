from flask import render_template, request, redirect, url_for, flash, session, jsonify, send_file, abort, current_app
from flask_login import login_user, login_required, logout_user, current_user
from flask_wtf import FlaskForm
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash
import os
import pandas as pd
import numpy as np
from datetime import datetime, date, timedelta
import pytz
import re
import json
import pickle
import uuid
import tempfile

# Conditional imports for ML libraries
try:
    from gensim.models import Word2Vec
    GENSIM_AVAILABLE = True
except ImportError:
    GENSIM_AVAILABLE = False

try:
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.naive_bayes import MultinomialNB
    SKLEARN_AVAILABLE = True
except ImportError:
    SKLEARN_AVAILABLE = False

try:
    import openpyxl
    OPENPYXL_AVAILABLE = True
except ImportError:
    OPENPYXL_AVAILABLE = False
from sqlalchemy import func, desc, text
from models import db, User, RawData, RawDataScraper, CleanDataUpload, CleanDataScraper, ClassificationResult, DatasetStatistics, Dataset
from utils import clean_text, vectorize_text, classify_content, scrape_with_apify, admin_required, active_user_required, format_datetime, check_content_duplicate, check_cleaned_content_duplicate, check_cleaned_content_duplicate_by_dataset, generate_activity_log, check_permission_with_feedback
from security_utils import SecurityValidator, generate_secure_filename, log_security_event, add_security_headers

def init_routes(app, word2vec_model_param, naive_bayes_models_param):
    # Store models in app config for global access
    app.config['WORD2VEC_MODEL'] = word2vec_model_param
    app.config['NAIVE_BAYES_MODELS'] = naive_bayes_models_param

    @app.route('/api/models-status')
    def models_status():
        word2vec_model = current_app.config.get('WORD2VEC_MODEL')
        naive_bayes_models = current_app.config.get('NAIVE_BAYES_MODELS', {})
        return jsonify({
            'word2vec_loaded': bool(word2vec_model),
            'naive_bayes_count': len([m for m in naive_bayes_models.values() if m is not None])
        })
    
    # Get CSRF instance from app
    from flask_wtf.csrf import CSRFProtect
    csrf = app.extensions.get('csrf', None)
    if not csrf:
        csrf = CSRFProtect(app)
    
    # Import limiter from app module
    from app import limiter
    
    @app.route('/')
    def index():
        if current_user.is_authenticated:
            return redirect(url_for('dashboard'))
        return redirect(url_for('login'))
    
    @app.route('/favicon.ico')
    def favicon():
        return send_file('static/images/favicon.ico', mimetype='image/vnd.microsoft.icon')
    
    @app.route('/login', methods=['GET', 'POST'])
    def login():
        if current_user.is_authenticated:
            return redirect(url_for('dashboard'))
        
        # Create form once for CSRF protection
        from flask_wtf import FlaskForm
        from wtforms import StringField, PasswordField, BooleanField
        from wtforms.validators import DataRequired
        
        class LoginForm(FlaskForm):
            username = StringField('Username', validators=[DataRequired()])
            password = PasswordField('Password', validators=[DataRequired()])
            remember = BooleanField('Remember Me')
        
        form = LoginForm()
        
        if request.method == 'POST':
            # Use form validation instead of manual validation
            if form.validate_on_submit():
                username = SecurityValidator.sanitize_input(
                    form.username.data, max_length=50
                ).strip()
                password = form.password.data
                remember = form.remember.data
                
                user = User.query.filter_by(username=username).first()
                
                if user and user.check_password(password) and user.is_active:
                    # Opsional: kontrol global OTP via ENV config
                    otp_enabled = str(current_app.config.get('OTP_ENABLED', True)).lower() in ['true', '1', 'yes']

                    # Jika login pertama dan OTP diaktifkan, jalankan alur OTP
                    if otp_enabled and user.first_login:
                        # Siapkan sesi untuk alur OTP pertama kali
                        session['first_login_user_id'] = user.id
                        session['first_login_remember'] = remember
                        session['first_login_next'] = request.args.get('next')

                        # Generate OTP untuk login pertama
                        from otp_routes import generate_otp
                        otp_code = generate_otp()
                        session['first_login_otp'] = otp_code
                        session['first_login_otp_expires'] = (datetime.utcnow() + timedelta(minutes=current_app.config['OTP_EXPIRY_MINUTES'])).isoformat()

                        # Kirim email OTP
                        from email_service import email_service
                        success, error_message = email_service.send_first_login_otp(user, otp_code)

                        if success:
                            flash('Ini adalah login pertama Anda. Silakan cek email untuk instruksi lebih lanjut.', 'info')
                            return redirect(url_for('otp.verify_first_login_otp'))
                        else:
                            # Gagal kirim OTP pada login pertama
                            current_app.logger.error(f"Failed to send first login OTP email: {error_message}")
                            flash('Gagal mengirim email OTP. Silakan hubungi administrator atau coba lagi nanti.', 'error')
                            # Bersihkan sesi OTP
                            session.pop('first_login_user_id', None)
                            session.pop('first_login_otp', None)
                            session.pop('first_login_otp_expires', None)
                            session.pop('first_login_remember', None)
                            session.pop('first_login_next', None)
                            return redirect(url_for('login'))

                    # Bukan login pertama (atau OTP dimatikan) -> lanjutkan login normal
                    user.last_login = datetime.utcnow()
                    db.session.commit()

                    login_user(user, remember=remember)

                    # Log successful login
                    log_security_event(
                        "LOGIN_SUCCESS", 
                        f"Successful login for user: {user.username}",
                        user_id=user.id,
                        ip_address=request.remote_addr
                    )

                    # Log activity
                    generate_activity_log(
                        action='login',
                        description=f'Login berhasil untuk pengguna: {user.username}',
                        user_id=user.id,
                        icon='fas fa-sign-in-alt',
                        color='success'
                    )

                    next_page = request.args.get('next')
                    flash('Login berhasil!', 'success')
                    return redirect(next_page) if next_page else redirect(url_for('dashboard'))
                
                # Jika validasi form gagal atau kredensial tidak cocok,
                # jalankan penanganan gagal di bawah.
                else:
                    # Log failed login attempt
                    log_security_event(
                        "LOGIN_FAILED", 
                        f"Failed login attempt for username: {form.username.data if form.username.data else 'unknown'}",
                        ip_address=request.remote_addr
                    )
                    flash('Username atau password salah!', 'error')
        else:
            # Form validation failed (CSRF token invalid or other validation errors)
            if form.errors:
                app.logger.warning(f"Form validation errors: {form.errors}")
                flash('Terdapat kesalahan dalam form. Silakan coba lagi.', 'error')
        
        return render_template('auth/login.html', form=form)
    
    @app.route('/register', methods=['GET', 'POST'])
    def register():
        """
        Redirect registrasi ke sistem OTP yang baru
        """
        if current_user.is_authenticated:
            return redirect(url_for('dashboard'))
        
        # Redirect ke sistem OTP registrasi
        return redirect(url_for('otp.register_request'))
    
    @app.route('/logout')
    @login_required
    def logout():
        # Log activity before logout
        generate_activity_log(
            action='logout',
            description=f'Logout untuk pengguna: {current_user.username}',
            user_id=current_user.id,
            icon='fas fa-sign-out-alt',
            color='warning'
        )
        
        logout_user()
        flash('Logout berhasil!', 'info')
        return redirect(url_for('login'))
    
    @app.route('/dashboard/stats')
    @login_required
    def dashboard_stats():
        try:
            # Get statistics with timeout protection
            stats = DatasetStatistics.query.first()
            if not stats:
                stats = DatasetStatistics()
                db.session.add(stats)
                db.session.commit()
            
            # Safeguard against None values to prevent TypeError
            total_raw_upload = stats.total_raw_upload or 0
            total_raw_scraper = stats.total_raw_scraper or 0
            total_clean_upload = stats.total_clean_upload or 0
            total_clean_scraper = stats.total_clean_scraper or 0
            total_classified = stats.total_classified or 0
            total_radikal = stats.total_radikal or 0
            total_non_radikal = stats.total_non_radikal or 0

            # Get platform statistics with simplified queries to avoid database locks
            platform_stats = {}
            
            # Use cached statistics if available during heavy operations
            from datetime import datetime, timedelta
            cache_timeout = timedelta(seconds=30)  # Cache for 30 seconds
            
            # Check if we should use cached data (during classification operations)
            use_cached = False
            
            if not use_cached:
                # Get fresh statistics with role-based filtering
                if current_user.is_admin():
                    # Admin dapat melihat semua data
                    platform_stats = {
                        'twitter_upload': RawData.query.filter_by(platform='twitter').filter(RawData.dataset_id.isnot(None)).count(),
                        'tiktok_upload': RawData.query.filter_by(platform='tiktok').filter(RawData.dataset_id.isnot(None)).count(),
                        'facebook_upload': RawData.query.filter_by(platform='facebook').filter(RawData.dataset_id.isnot(None)).count(),
                        'instagram_upload': RawData.query.filter_by(platform='instagram').filter(RawData.dataset_id.isnot(None)).count(),
                        'twitter_scraper': RawDataScraper.query.filter_by(platform='twitter').filter(RawDataScraper.dataset_id.isnot(None)).count(),
                        'tiktok_scraper': RawDataScraper.query.filter_by(platform='tiktok').filter(RawDataScraper.dataset_id.isnot(None)).count(),
                        'facebook_scraper': RawDataScraper.query.filter_by(platform='facebook').filter(RawDataScraper.dataset_id.isnot(None)).count(),
                        'instagram_scraper': RawDataScraper.query.filter_by(platform='instagram').filter(RawDataScraper.dataset_id.isnot(None)).count(),
                    }
                else:
                    # Regular user hanya dapat melihat data mereka sendiri
                    platform_stats = {
                        'twitter_upload': RawData.query.filter_by(platform='twitter', uploaded_by=current_user.id).filter(RawData.dataset_id.isnot(None)).count(),
                        'tiktok_upload': RawData.query.filter_by(platform='tiktok', uploaded_by=current_user.id).filter(RawData.dataset_id.isnot(None)).count(),
                        'facebook_upload': RawData.query.filter_by(platform='facebook', uploaded_by=current_user.id).filter(RawData.dataset_id.isnot(None)).count(),
                        'instagram_upload': RawData.query.filter_by(platform='instagram', uploaded_by=current_user.id).filter(RawData.dataset_id.isnot(None)).count(),
                        'twitter_scraper': RawDataScraper.query.filter_by(platform='twitter', scraped_by=current_user.id).filter(RawDataScraper.dataset_id.isnot(None)).count(),
                        'tiktok_scraper': RawDataScraper.query.filter_by(platform='tiktok', scraped_by=current_user.id).filter(RawDataScraper.dataset_id.isnot(None)).count(),
                        'facebook_scraper': RawDataScraper.query.filter_by(platform='facebook', scraped_by=current_user.id).filter(RawDataScraper.dataset_id.isnot(None)).count(),
                        'instagram_scraper': RawDataScraper.query.filter_by(platform='instagram', scraped_by=current_user.id).filter(RawDataScraper.dataset_id.isnot(None)).count(),
                    }
            else:
                # Use basic statistics without detailed platform breakdown during heavy operations
                platform_stats = {
                    'twitter_upload': 0,
                    'tiktok_upload': 0,
                    'facebook_upload': 0,
                    'instagram_upload': 0,
                    'twitter_scraper': 0,
                    'tiktok_scraper': 0,
                    'facebook_scraper': 0,
                    'instagram_scraper': 0,
                }
            
            # Calculate percentages
            radikal_percentage = 0
            non_radikal_percentage = 0
            if total_classified > 0:
                radikal_percentage = (total_radikal / total_classified) * 100
                non_radikal_percentage = (total_non_radikal / total_classified) * 100
            
            # Get model status
            word2vec_model = current_app.config.get('WORD2VEC_MODEL')
            naive_bayes_models = current_app.config.get('NAIVE_BAYES_MODELS', {})
            model_status = {
                'word2vec': 'Loaded' if word2vec_model else 'Error',
                'naive_bayes_count': len([m for m in naive_bayes_models.values() if m is not None]),
                'database': 'Connected'
            }
            
            return jsonify({
                'success': True,
                'total_raw_upload': total_raw_upload,
                'total_raw_scraper': total_raw_scraper,
                'total_clean_upload': total_clean_upload,
                'total_clean_scraper': total_clean_scraper,
                'total_classified': total_classified,
                'total_radikal': total_radikal,
                'total_non_radikal': total_non_radikal,
                'radikal_percentage': radikal_percentage,
                'non_radikal_percentage': non_radikal_percentage,
                'model_status': model_status,
                **platform_stats
            })
            
        except Exception as e:
            app.logger.error(f"Error in dashboard stats: {str(e)}")
            return jsonify({
                'success': False,
                'message': 'Gagal mengambil statistik dashboard',
                'error': str(e)
            }), 500

    @app.route('/api/admin/reload-models')
    @login_required
    @admin_required
    def admin_reload_models():
        """API endpoint untuk memaksa reload semua model machine learning (admin only)"""
        try:
            # Import fungsi force_reload_models dari app
            from app import force_reload_models
            
            # Paksa reload models
            result = force_reload_models()
            
            app.logger.info(f"Force reload models result: {result}")
            
            return jsonify({
                'success': result['success'],
                'message': result['message'],
                'word2vec_loaded': result['word2vec_loaded'],
                'naive_bayes_loaded': result['naive_bayes_loaded'],
                'timestamp': datetime.utcnow().isoformat()
            })
            
        except Exception as e:
            app.logger.error(f"Error in admin_reload_models: {str(e)}")
            return jsonify({
                'success': False,
                'message': f'Gagal memuat ulang model: {str(e)}',
                'error': str(e)
            }), 500

    @app.route('/dashboard')
    @login_required
    def dashboard():
        # Get statistics
        stats = DatasetStatistics.query.first()
        if not stats:
            stats = DatasetStatistics()
            db.session.add(stats)
            db.session.commit()
        
        # Get platform statistics - only count data that belongs to existing datasets
        if current_user.is_admin():
            # Admin dapat melihat semua data
            platform_stats = {
                'twitter_upload': RawData.query.filter_by(platform='twitter').filter(RawData.dataset_id.isnot(None)).count(),
                'tiktok_upload': RawData.query.filter_by(platform='tiktok').filter(RawData.dataset_id.isnot(None)).count(),
                'facebook_upload': RawData.query.filter_by(platform='facebook').filter(RawData.dataset_id.isnot(None)).count(),
                'instagram_upload': RawData.query.filter_by(platform='instagram').filter(RawData.dataset_id.isnot(None)).count(),
                'twitter_scraper': RawDataScraper.query.filter_by(platform='twitter').filter(RawDataScraper.dataset_id.isnot(None)).count(),
                'tiktok_scraper': RawDataScraper.query.filter_by(platform='tiktok').filter(RawDataScraper.dataset_id.isnot(None)).count(),
                'facebook_scraper': RawDataScraper.query.filter_by(platform='facebook').filter(RawDataScraper.dataset_id.isnot(None)).count(),
                'instagram_scraper': RawDataScraper.query.filter_by(platform='instagram').filter(RawDataScraper.dataset_id.isnot(None)).count(),
            }
        else:
            # Regular user hanya dapat melihat data mereka sendiri
            platform_stats = {
                'twitter_upload': RawData.query.filter_by(platform='twitter', uploaded_by=current_user.id).filter(RawData.dataset_id.isnot(None)).count(),
                'tiktok_upload': RawData.query.filter_by(platform='tiktok', uploaded_by=current_user.id).filter(RawData.dataset_id.isnot(None)).count(),
                'facebook_upload': RawData.query.filter_by(platform='facebook', uploaded_by=current_user.id).filter(RawData.dataset_id.isnot(None)).count(),
                'instagram_upload': RawData.query.filter_by(platform='instagram', uploaded_by=current_user.id).filter(RawData.dataset_id.isnot(None)).count(),
                'twitter_scraper': RawDataScraper.query.filter_by(platform='twitter', scraped_by=current_user.id).filter(RawDataScraper.dataset_id.isnot(None)).count(),
                'tiktok_scraper': RawDataScraper.query.filter_by(platform='tiktok', scraped_by=current_user.id).filter(RawDataScraper.dataset_id.isnot(None)).count(),
                'facebook_scraper': RawDataScraper.query.filter_by(platform='facebook', scraped_by=current_user.id).filter(RawDataScraper.dataset_id.isnot(None)).count(),
                'instagram_scraper': RawDataScraper.query.filter_by(platform='instagram', scraped_by=current_user.id).filter(RawDataScraper.dataset_id.isnot(None)).count(),
            }
        
        # Get model status
        word2vec_model = current_app.config.get('WORD2VEC_MODEL')
        naive_bayes_models = current_app.config.get('NAIVE_BAYES_MODELS', {})
        model_status = {
            'word2vec': 'Loaded' if word2vec_model else 'Error',
            'naive_bayes_count': len([m for m in naive_bayes_models.values() if m is not None]),
            'database': 'Connected'
        }
        
        # Get recent activities from database
        from models import UserActivity
        if current_user.is_admin():
            # Admin dapat melihat semua aktivitas
            recent_activities_query = UserActivity.query.order_by(UserActivity.created_at.desc()).limit(4).all()
        else:
            # Regular user hanya dapat melihat aktivitas mereka sendiri
            recent_activities_query = UserActivity.query.filter_by(user_id=current_user.id).order_by(UserActivity.created_at.desc()).limit(4).all()
        
        recent_activities = []
        for activity in recent_activities_query:
            recent_activities.append({
                'date': format_datetime(activity.created_at, 'date'),
                'time': format_datetime(activity.created_at, 'time'),
                'title': activity.action.title(),
                'description': activity.description,
                'icon': activity.icon,
                'color': activity.color
            })
        
        # Add default activity if no activities found
        if not recent_activities:
            recent_activities = [
                {
                    'date': format_datetime(datetime.now(), 'date'),
                    'time': '',
                    'title': 'Sistem dimulai',
                    'description': 'Aplikasi Waskita berhasil dimulai',
                    'icon': 'fa-power-off',
                    'color': 'success'
                }
            ]
        
        return render_template('dashboard.html', 
                             stats=stats, 
                             platform_stats=platform_stats,
                             model_status=model_status,
                             recent_activities=recent_activities)
    
    @app.route('/data/upload', methods=['GET', 'POST'])
    @login_required
    def data_upload():
        if request.method == 'POST':
            if 'file' not in request.files:
                flash('Tidak ada file yang dipilih!', 'error')
                return redirect(request.url)
            
            file = request.files['file']
            
            if file.filename == '':
                flash('Tidak ada file yang dipilih!', 'error')
                return redirect(request.url)
            
            # Use new security validation
            is_valid, message, file_info = SecurityValidator.validate_file_upload(file)
            if not is_valid:
                flash(f'Error validasi file: {message}', 'error')
                log_security_event(
                    "FILE_UPLOAD_REJECTED", 
                    f"File upload rejected: {message} | File: {file.filename}",
                    user_id=current_user.id,
                    ip_address=request.remote_addr
                )
                return redirect(request.url)
            
            try:
                # Generate secure filename and path
                filepath, unique_filename = generate_secure_filename(
                    file.filename, 
                    app.config['UPLOAD_FOLDER']
                )
                
                # Create upload directory if not exists
                os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
                file.save(filepath)
                
                # Log successful upload
                log_security_event(
                    "FILE_UPLOAD_SUCCESS", 
                    f"File uploaded successfully: {file.filename} -> {unique_filename}",
                    user_id=current_user.id,
                    ip_address=request.remote_addr
                )
                
                mime_type = file_info.get('mime_type', '')
                detected_format = file_info.get('detected_format')
                filename_lower = file.filename.lower()
                is_csv = (
                    detected_format == 'csv' or
                    filename_lower.endswith('.csv') or
                    mime_type in ['text/csv', 'text/plain', 'application/csv', 'application/vnd.ms-excel']
                )

                if is_csv:
                    encodings_to_try = ['utf-8', 'utf-8-sig', 'latin1', 'cp1252', 'iso-8859-1']
                    df = None
                    last_error = None

                    for encoding in encodings_to_try:
                        try:
                            df = pd.read_csv(filepath, encoding=encoding)
                            app.logger.info(f"Successfully read CSV with encoding: {encoding}")
                            break
                        except (UnicodeDecodeError, UnicodeError) as e:
                            last_error = e
                            continue
                        except Exception as e:
                            try:
                                df = pd.read_csv(filepath, encoding=encoding, on_bad_lines='skip')
                                app.logger.info(f"Successfully read CSV with encoding {encoding} (skipping bad lines)")
                                break
                            except Exception as e2:
                                last_error = e2
                                continue

                    if df is None:
                        raise Exception(f"Could not read CSV file with any encoding. Last error: {str(last_error)}")
                else:
                    try:
                        df = pd.read_excel(filepath)
                    except Exception:
                        try:
                            df = pd.read_csv(filepath)
                            app.logger.info("Fallback to CSV after Excel read failure")
                        except Exception as e2:
                            raise e2
                
                # Process and save data with input sanitization
                success_count = 0
                for _, row in df.iterrows():
                    # Auto-detect platform from URL or use default
                    detected_platform = 'manual'  # Default for manual uploads
                    url = row.get('url', '')
                    
                    # Sanitize inputs
                    username = SecurityValidator.sanitize_input(str(row.get('username', '')), max_length=100)
                    content = SecurityValidator.sanitize_input(str(row.get('content', '')), max_length=5000)
                    url = SecurityValidator.sanitize_input(str(url), max_length=500)
                    
                    if url:
                        if 'twitter.com' in url or 'x.com' in url:
                            detected_platform = 'twitter'
                        elif 'facebook.com' in url:
                            detected_platform = 'facebook'
                        elif 'tiktok.com' in url:
                            detected_platform = 'tiktok'
                        elif 'instagram.com' in url:
                            detected_platform = 'instagram'
                    
                    raw_data = RawData(
                        username=username,
                        content=content,
                        url=url,
                        platform=detected_platform,
                        uploaded_by=current_user.id,
                        file_size=file_info['file_size'],
                        original_filename=file_info['original_filename']
                    )
                    db.session.add(raw_data)
                    success_count += 1
                
                db.session.commit()
                
                # Update statistics
                update_statistics()
                
                # Log aktivitas upload
                from utils import generate_activity_log
                generate_activity_log(
                    action='upload',
                    description=f'Berhasil mengupload {success_count} data dari file {file.filename}',
                    user_id=current_user.id,
                    details={
                        'filename': file.filename,
                        'success_count': success_count,
                        'platform_detected': detected_platform,
                        'file_size': file_info['file_size'],
                        'mime_type': file_info['mime_type']
                    },
                    icon='fa-upload',
                    color='success'
                )
                
                flash(f'Berhasil mengupload {success_count} data!', 'success')
                
            except Exception as e:
                db.session.rollback()
                error_msg = f'Error memproses file: {str(e)}'
                flash(error_msg, 'error')
                
                # Log error
                log_security_event(
                    "FILE_UPLOAD_ERROR", 
                    f"File processing error: {error_msg} | File: {file.filename}",
                    user_id=current_user.id,
                    ip_address=request.remote_addr
                )
            finally:
                # Clean up uploaded file
                if 'filepath' in locals() and os.path.exists(filepath):
                    os.remove(filepath)
        
        return render_template('data/upload.html')
    
    @app.route('/data/scraping', methods=['GET', 'POST'])
    @login_required
    def data_scraping():
        if request.method == 'POST':
            # Sanitize and validate inputs
            platform = SecurityValidator.sanitize_input(
                request.form.get('platform', ''), max_length=50
            ).strip()
            keyword = SecurityValidator.sanitize_input(
                request.form.get('keyword', ''), max_length=200
            ).strip()
            date_from = SecurityValidator.sanitize_input(
                request.form.get('date_from', ''), max_length=20
            ).strip()
            date_to = SecurityValidator.sanitize_input(
                request.form.get('date_to', ''), max_length=20
            ).strip()
            
            # Validate max_results input
            try:
                max_results = int(request.form.get('max_results', 25))
                if max_results < 1 or max_results > 1000:  # Set reasonable limits
                    max_results = 25
            except (ValueError, TypeError):
                max_results = 25
            
            # Validate required fields
            if not platform or not keyword:
                log_security_event(
                    "SCRAPING_INVALID_INPUT", 
                    f"Scraping attempt with invalid input - platform: {platform}, keyword: {keyword}",
                    user_id=current_user.id,
                    ip_address=request.remote_addr
                )
                flash('Platform dan keyword harus diisi!', 'error')
                return render_template('data/scraping.html')
            
            # Log scraping attempt
            log_security_event(
                "SCRAPING_ATTEMPT", 
                f"Scraping attempt - platform: {platform}, keyword: {keyword}, max_results: {max_results}",
                user_id=current_user.id,
                ip_address=request.remote_addr
            )
            try:
                # Create new dataset automatically based on keyword
                dataset_name = f"Scraper Data {platform.title()} - {keyword}"
                dataset = Dataset(
                    name=dataset_name,
                    description=f"Data hasil scraping dari {platform} dengan kata kunci '{keyword}' periode {date_from} sampai {date_to}",
                    uploaded_by=current_user.id
                )
                db.session.add(dataset)
                db.session.flush()  # Get the ID
                
                # Use Apify API for scraping - get raw results for column mapping
                scraped_data, run_id = scrape_with_apify(
                    platform=platform,
                    keyword=keyword,
                    date_from=date_from,
                    date_to=date_to,
                    max_results=max_results
                )
                
                # Store scraping info in session for column mapping
                session['scraping_platform'] = platform
                session['scraping_keyword'] = keyword
                session['scraping_date_from'] = date_from
                session['scraping_date_to'] = date_to
                session['scraping_max_results'] = max_results
                session['scraping_dataset_id'] = dataset.id
                session['scraping_dataset_name'] = dataset.name
                session['scraping_run_id'] = run_id
                session['scraping_raw_data'] = scraped_data
                
                # Get available columns from first item
                if scraped_data:
                    first_item = scraped_data[0]
                    available_columns = list(first_item.keys())
                    
                    # Get sample data for preview (first 5 items)
                    sample_data = scraped_data[:5]
                    
                    return jsonify({
                        'success': True,
                        'show_mapping': True,
                        'columns': available_columns,
                        'sample_data': sample_data,
                        'platform': platform,
                        'total_items': len(scraped_data),
                        'run_id': run_id
                    })
                else:
                    flash('Tidak ada data yang ditemukan untuk scraping ini', 'warning')
                    return redirect(url_for('scraping_page'))
                
            except Exception as e:
                db.session.rollback()
                flash(f'Error scraping data: {str(e)}', 'error')
        
        return render_template('data/scraping.html')
    
    @app.route('/api/scraping/map-data', methods=['POST'])
    @login_required
    def map_scraping_data():
        """Map scraping data columns like upload data"""
        try:
            data = request.get_json()
            dataset_id = data.get('dataset_id')
            column_mapping = data.get('column_mapping', {})
            selected_ids = data.get('selected_ids', [])
            
            if not dataset_id:
                return jsonify({'success': False, 'message': 'Dataset ID required'}), 400
            
            # Get dataset
            dataset = Dataset.query.get(dataset_id)
            if not dataset:
                return jsonify({'success': False, 'message': 'Dataset not found'}), 404
            
            # Check permission dengan feedback yang jelas
            has_permission, message, http_status = check_permission_with_feedback(
                current_user, dataset.uploaded_by, 'access', 'dataset'
            )
            if not has_permission:
                return jsonify({'success': False, 'message': message}), http_status
            
            # Get scraping data
            if selected_ids:
                scraping_data = RawDataScraper.query.filter(
                    RawDataScraper.dataset_id == dataset_id,
                    RawDataScraper.id.in_(selected_ids)
                ).all()
            else:
                scraping_data = RawDataScraper.query.filter_by(dataset_id=dataset_id).all()
            
            if not scraping_data:
                return jsonify({'success': False, 'message': 'No data found'}), 404
            
            # Map data to RawData format
            success_count = 0
            for item in scraping_data:
                # Create RawData entry
                raw_data = RawData(
                    username=item.username,
                    content=item.content,
                    url=item.url,
                    dataset_id=dataset_id,
                    dataset_name=dataset.name,
                    uploaded_by=current_user.id,
                    file_name=f"scraping_{item.platform}_{item.keyword}.csv",
                    file_size=len(item.content.encode('utf-8')) if item.content else 0
                )
                db.session.add(raw_data)
                success_count += 1
            
            db.session.commit()
            
            return jsonify({
                'success': True,
                'message': f'Successfully mapped {success_count} records to upload data format',
                'mapped_count': success_count,
                'redirect_url': f'/dataset/{dataset_id}/details'
            })
            
        except Exception as e:
            db.session.rollback()
            return jsonify({'success': False, 'message': f'Error mapping data: {str(e)}'}), 500
    
    @app.route('/data/cleaning')
    @login_required
    def data_cleaning():
        """Halaman untuk cleaning data"""
        # Get raw data yang belum dibersihkan dengan filter role-based
        if current_user.is_admin():
            # Admin dapat melihat semua data
            raw_upload_data = RawData.query.filter_by(status='raw').order_by(desc(RawData.created_at)).all()
            raw_scraper_data = RawDataScraper.query.filter_by(status='raw').order_by(desc(RawDataScraper.created_at)).all()
        else:
            # Regular user hanya dapat melihat data mereka sendiri
            raw_upload_data = RawData.query.filter_by(status='raw', uploaded_by=current_user.id).order_by(desc(RawData.created_at)).all()
            raw_scraper_data = RawDataScraper.query.filter_by(status='raw', scraped_by=current_user.id).order_by(desc(RawDataScraper.created_at)).all()
        
        # Get clean data
        clean_upload_data = CleanDataUpload.query.order_by(desc(CleanDataUpload.created_at)).all()
        clean_scraper_data = CleanDataScraper.query.order_by(desc(CleanDataScraper.created_at)).all()
            
        return render_template('data/cleaning.html',
                                 raw_upload_data=raw_upload_data,
                                 raw_scraper_data=raw_scraper_data,
                                 clean_upload_data=clean_upload_data,
                                 clean_scraper_data=clean_scraper_data)
    
    @app.route('/dataset')
    @login_required
    def dataset_view():
        """Handle dataset view with optional upload_id parameter"""
        upload_id = request.args.get('upload_id')
        
        if upload_id:
            try:
                # Get the raw data to find its dataset
                raw_data = RawData.query.get_or_404(upload_id)
                
                # Check permission dengan feedback yang jelas
                has_permission, message, http_status = check_permission_with_feedback(
                    current_user, raw_data.uploaded_by, 'view', 'raw data'
                )
                if not has_permission:
                    flash(message, 'error')
                    return redirect(url_for('dataset_management_table'))
                
                # If data has dataset_id, redirect to dataset details
                if raw_data.dataset_id:
                    return redirect(url_for('dataset_details', dataset_id=raw_data.dataset_id))
                else:
                    # If no dataset_id, show upload details in dataset management
                    flash(f'Data upload "{raw_data.content[:50]}..." belum tergabung dalam dataset', 'info')
                    return redirect(url_for('dataset_management_table'))
                    
            except Exception as e:
                flash(f'Data upload tidak ditemukan: {str(e)}', 'error')
                return redirect(url_for('dataset_management_table'))
        else:
            # No upload_id, redirect to dataset management
            return redirect(url_for('dataset_management_table'))
    
    @app.route('/dataset/management')
    @login_required
    def dataset_management():
        """Redirect to table view - card view removed for simplicity"""
        # Preserve query parameters when redirecting
        args = request.args.to_dict()
        return redirect(url_for('dataset_management_table', **args))
    
    @app.route('/dataset/management/table')
    @login_required
    def dataset_management_table():
        """Dataset management with table view"""
        try:
            # Get pagination parameters (adjusted for table view)
            page = request.args.get('page', 1, type=int)
            per_page = request.args.get('per_page', 25, type=int)  # More items per page for table
            search = request.args.get('search', '', type=str)
            sort_by = request.args.get('sort_by', 'created_at', type=str)  # Changed default to created_at
            sort_order = request.args.get('sort_order', 'desc', type=str)
            
            # Build query for datasets
            query = Dataset.query
            
            # Apply user filter (admin sees all, users see datasets containing their data)
            if not current_user.is_admin():
                # Get dataset IDs that contain user's data
                user_dataset_ids = db.session.query(RawData.dataset_id).filter(
                    RawData.uploaded_by == current_user.id,
                    RawData.dataset_id.isnot(None)
                ).distinct().all()
                user_dataset_ids = [row[0] for row in user_dataset_ids]
                
                scraper_dataset_ids = db.session.query(RawDataScraper.dataset_id).filter(
                    RawDataScraper.scraped_by == current_user.id,
                    RawDataScraper.dataset_id.isnot(None)
                ).distinct().all()
                scraper_dataset_ids = [row[0] for row in scraper_dataset_ids]
                
                # Combine all dataset IDs that user has access to
                accessible_dataset_ids = list(set(user_dataset_ids + scraper_dataset_ids))
                
                # Filter datasets that either belong to user OR contain user's data
                query = query.filter(
                    db.or_(
                        Dataset.uploaded_by == current_user.id,
                        Dataset.id.in_(accessible_dataset_ids) if accessible_dataset_ids else False
                    )
                )
            
            # Apply search filter
            if search:
                query = query.filter(Dataset.name.ilike(f'%{search}%'))
            
            # Apply sorting
            if sort_by == 'name':
                if sort_order == 'desc':
                    query = query.order_by(desc(Dataset.name))
                else:
                    query = query.order_by(Dataset.name)
            elif sort_by == 'created_at':
                if sort_order == 'desc':
                    query = query.order_by(desc(Dataset.created_at))
                else:
                    query = query.order_by(Dataset.created_at)
            else:  # default to updated_at
                if sort_order == 'desc':
                    query = query.order_by(desc(Dataset.updated_at))
                else:
                    query = query.order_by(Dataset.updated_at)
            
            # Apply pagination
            datasets_pagination = query.paginate(
                page=page, per_page=per_page, error_out=False
            )
            
            # Get dataset statistics
            dataset_stats = []
            for dataset in datasets_pagination.items:
                # Ensure dataset exists and is valid
                if not dataset:
                    continue
                    
                # Count raw data (upload + scraper) with role-based filtering
                if current_user.is_admin():
                    raw_upload_count = RawData.query.filter_by(dataset_id=dataset.id).count()
                    raw_scraper_count = RawDataScraper.query.filter_by(dataset_id=dataset.id).count()
                else:
                    raw_upload_count = RawData.query.filter_by(dataset_id=dataset.id, uploaded_by=current_user.id).count()
                    raw_scraper_count = RawDataScraper.query.filter_by(dataset_id=dataset.id, scraped_by=current_user.id).count()
                raw_count = raw_upload_count + raw_scraper_count
                
                # Get sample username, URL, and content from raw data
                sample_username = None
                sample_url = None
                sample_content = None
                
                # Get sample data for display (prioritize clean data if available)
                sample_username = None
                sample_url = None
                sample_content = None
                
                # First try to get from clean data (upload)
                clean_upload_sample = db.session.execute(
                    text("SELECT cdu.username, cdu.url, cdu.cleaned_content FROM clean_data_upload cdu JOIN raw_data rd ON cdu.raw_data_id = rd.id WHERE rd.dataset_id = :dataset_id LIMIT 1"),
                    {'dataset_id': dataset.id}
                ).first()
                
                if clean_upload_sample:
                    sample_username = clean_upload_sample.username if clean_upload_sample.username and str(clean_upload_sample.username).lower() != 'nan' else None
                    sample_url = clean_upload_sample.url if clean_upload_sample.url and str(clean_upload_sample.url).lower() != 'nan' else None
                    sample_content = clean_upload_sample.cleaned_content if clean_upload_sample.cleaned_content and str(clean_upload_sample.cleaned_content).lower() != 'nan' else None
                else:
                    # Try clean data (scraper)
                    clean_scraper_sample = db.session.execute(
                        text("SELECT cds.username, cds.url, cds.cleaned_content FROM clean_data_scraper cds JOIN raw_data_scraper rds ON cds.raw_data_scraper_id = rds.id WHERE rds.dataset_id = :dataset_id LIMIT 1"),
                        {'dataset_id': dataset.id}
                    ).first()
                    
                    if clean_scraper_sample:
                        sample_username = clean_scraper_sample.username if clean_scraper_sample.username and str(clean_scraper_sample.username).lower() != 'nan' else None
                        sample_url = clean_scraper_sample.url if clean_scraper_sample.url and str(clean_scraper_sample.url).lower() != 'nan' else None
                        sample_content = clean_scraper_sample.cleaned_content if clean_scraper_sample.cleaned_content and str(clean_scraper_sample.cleaned_content).lower() != 'nan' else None
                    else:
                        # Fallback to raw data (upload)
                        sample_upload = RawData.query.filter_by(dataset_id=dataset.id).first()
                        if sample_upload:
                            sample_username = sample_upload.username if sample_upload.username and str(sample_upload.username).lower() != 'nan' else None
                            sample_url = sample_upload.url if sample_upload.url and str(sample_upload.url).lower() != 'nan' else None
                            sample_content = sample_upload.content if sample_upload.content and str(sample_upload.content).lower() != 'nan' else None
                        else:
                            # Fallback to raw data (scraper)
                            sample_scraper = RawDataScraper.query.filter_by(dataset_id=dataset.id).first()
                            if sample_scraper:
                                sample_username = sample_scraper.username if sample_scraper.username and str(sample_scraper.username).lower() != 'nan' else None
                                sample_url = sample_scraper.url if sample_scraper.url and str(sample_scraper.url).lower() != 'nan' else None
                                sample_content = sample_scraper.content if sample_scraper.content and str(sample_scraper.content).lower() != 'nan' else None
                
                # Count clean data (upload + scraper)
                clean_upload_count = db.session.execute(
                    text("SELECT COUNT(*) FROM clean_data_upload cdu JOIN raw_data rd ON cdu.raw_data_id = rd.id WHERE rd.dataset_id = :dataset_id"),
                    {'dataset_id': dataset.id}
                ).scalar() or 0
                clean_scraper_count = db.session.execute(
                    text("SELECT COUNT(*) FROM clean_data_scraper cds JOIN raw_data_scraper rds ON cds.raw_data_scraper_id = rds.id WHERE rds.dataset_id = :dataset_id"),
                    {'dataset_id': dataset.id}
                ).scalar() or 0
                
                # Count classified data (upload + scraper) with role-based filtering
                if current_user.is_admin():
                    classified_upload_count = db.session.execute(
                        text("SELECT COUNT(*) FROM classification_results cr JOIN clean_data_upload cdu ON cr.data_type = 'upload' AND cr.data_id = cdu.id JOIN raw_data rd ON cdu.raw_data_id = rd.id WHERE rd.dataset_id = :dataset_id"),
                        {'dataset_id': dataset.id}
                    ).scalar() or 0
                    classified_scraper_count = db.session.execute(
                        text("SELECT COUNT(*) FROM classification_results cr JOIN clean_data_scraper cds ON cr.data_type = 'scraper' AND cr.data_id = cds.id JOIN raw_data_scraper rds ON cds.raw_data_scraper_id = rds.id WHERE rds.dataset_id = :dataset_id"),
                        {'dataset_id': dataset.id}
                    ).scalar() or 0
                else:
                    # For regular users, only count their own data
                    classified_upload_count = db.session.execute(
                        text("SELECT COUNT(*) FROM classification_results cr JOIN clean_data_upload cdu ON cr.data_type = 'upload' AND cr.data_id = cdu.id JOIN raw_data rd ON cdu.raw_data_id = rd.id WHERE rd.dataset_id = :dataset_id AND rd.uploaded_by = :user_id"),
                        {'dataset_id': dataset.id, 'user_id': current_user.id}
                    ).scalar() or 0
                    classified_scraper_count = db.session.execute(
                        text("SELECT COUNT(*) FROM classification_results cr JOIN clean_data_scraper cds ON cr.data_type = 'scraper' AND cr.data_id = cds.id JOIN raw_data_scraper rds ON cds.raw_data_scraper_id = rds.id WHERE rds.dataset_id = :dataset_id AND rds.scraped_by = :user_id"),
                        {'dataset_id': dataset.id, 'user_id': current_user.id}
                    ).scalar() or 0
                classified_count = classified_upload_count + classified_scraper_count
                
                dataset_stats.append({
                    'dataset': dataset,
                    'raw_count': raw_count,
                    'raw_upload_count': raw_upload_count,
                    'raw_scraper_count': raw_scraper_count,
                    'clean_count': clean_upload_count + clean_scraper_count,
                    'clean_upload_count': clean_upload_count,
                    'clean_scraper_count': clean_scraper_count,
                    'classified_count': classified_count,
                    'total_records': raw_count,
                    'sample_username': sample_username or '-',
                    'sample_url': sample_url or '-',
                    'sample_content': sample_content or '-'
                })
            
            # Ensure format_datetime filter is available in template context
            return render_template('dataset/management_table.html', 
                                 dataset_stats=dataset_stats,
                                 format_datetime=format_datetime,
                                 pagination=datasets_pagination,
                                 search=search,
                                 sort_by=sort_by,
                                 sort_order=sort_order,
                                 per_page=per_page)
        
        except Exception as e:
            flash(f'Error loading dataset management table: {str(e)}', 'error')
            return redirect(url_for('dashboard'))
    
    @app.route('/api/raw_data')
    @login_required
    def get_raw_data():
        """Get raw data for cleaning"""
        try:
            # Get raw upload data with role-based filtering
            if current_user.is_admin():
                raw_upload_data = RawData.query.order_by(desc(RawData.created_at)).all()
                raw_scraper_data = RawDataScraper.query.order_by(desc(RawDataScraper.created_at)).all()
            else:
                raw_upload_data = RawData.query.filter_by(uploaded_by=current_user.id).order_by(desc(RawData.created_at)).all()
                raw_scraper_data = RawDataScraper.query.filter_by(scraped_by=current_user.id).order_by(desc(RawDataScraper.created_at)).all()

            result = []
            
            # Add upload data
            for data in raw_upload_data:
                result.append({
                    'id': data.id,
                    'content': data.content,
                    'username': data.username,
                    'platform': data.platform,
                    'status': data.status,
                    'type': 'upload',
                    'created_at': format_datetime(data.created_at, 'default')
                })
            
            # Add scraper data
            for data in raw_scraper_data:
                result.append({
                    'id': data.id,
                    'content': data.content,
                    'username': data.username,
                    'platform': data.platform,
                    'status': data.status,
                    'type': 'scraper',
                    'keyword': data.keyword,
                    'created_at': format_datetime(data.created_at, 'default')
                })
            
            return jsonify(result)
            
        except Exception as e:
            return jsonify({'error': str(e)}), 500
    
    @app.route('/dataset/clean/<data_type>/<int:data_id>')
    @login_required
    def clean_data(data_type, data_id):
        try:
            if data_type == 'upload':
                raw_data = RawData.query.get_or_404(data_id)
                
                # Check if already cleaned
                existing_clean = CleanDataUpload.query.filter_by(raw_data_id=data_id).first()
                if existing_clean:
                    flash('Data sudah dibersihkan sebelumnya!', 'warning')
                    return redirect(url_for('dataset_management'))
                
                # Clean the content
                cleaned_content = clean_text(raw_data.content)
                
                # Save cleaned data
                clean_data = CleanDataUpload(
                    raw_data_id=data_id,
                    username=raw_data.username,
                    content=raw_data.content,
                    cleaned_content=cleaned_content,
                    url=raw_data.url,
                    platform=raw_data.platform,
                    dataset_id=raw_data.dataset_id,
                    cleaned_by=current_user.id
                )
                
                # Update raw data status
                raw_data.status = 'cleaned'
                
            elif data_type == 'scraper':
                raw_data = RawDataScraper.query.get_or_404(data_id)
                
                # Check if already cleaned using raw SQL
                result = db.session.execute(text("SELECT * FROM clean_data_scraper WHERE raw_data_scraper_id = :data_id LIMIT 1"), {'data_id': data_id})
                existing_clean = result.fetchone()
                if existing_clean:
                    flash('Data sudah dibersihkan sebelumnya!', 'warning')
                    return redirect(url_for('dataset_management'))
                
                # Clean the content
                cleaned_content = clean_text(raw_data.content)
                
                # Check for duplicate content in clean data tables
                is_duplicate = check_cleaned_content_duplicate(cleaned_content)
                
                if is_duplicate:
                    flash('Konten duplikat ditemukan! Data tidak disimpan ke tabel clean data.', 'warning')
                    # Update raw data status but don't save clean data
                    raw_data.status = 'cleaned'
                    db.session.commit()
                    return redirect(url_for('dataset_management'))
                
                # Save cleaned data
                clean_data = CleanDataScraper(
                    raw_data_scraper_id=data_id,
                    username=raw_data.username,
                    content=raw_data.content,
                    cleaned_content=cleaned_content,
                    url=raw_data.url,
                    platform=raw_data.platform,
                    keyword=raw_data.keyword,
                    dataset_id=raw_data.dataset_id,
                    cleaned_by=current_user.id
                )
                
                # Update raw data status
                raw_data.status = 'cleaned'
            
            db.session.add(clean_data)
            db.session.commit()
            
            # Update dataset total_records
            dataset.total_records = RawData.query.filter_by(dataset_id=dataset.id).count() + RawDataScraper.query.filter_by(dataset_id=dataset.id).count()
            db.session.commit()
            
            # Update dataset total_records
            dataset.total_records = RawData.query.filter_by(dataset_id=dataset.id).count() + RawDataScraper.query.filter_by(dataset_id=dataset.id).count()
            db.session.commit()
            
            # Update statistics
            update_statistics()
            app.logger.info("Statistics updated successfully")
            
            flash('Data berhasil dibersihkan!', 'success')
            
        except Exception as e:
            db.session.rollback()
            flash(f'Error membersihkan data: {str(e)}', 'error')
        
        return redirect(url_for('dataset_management'))
    
    @app.route('/classification')
    @login_required
    @active_user_required
    def classification():
        # Get clean data that hasn't been classified
        from sqlalchemy import text
        
        # Check if dataset_id parameter is provided
        dataset_id = request.args.get('dataset_id')
        selected_dataset = None
        classified_count = 0
        
        if dataset_id:
            # Get specific dataset information
            selected_dataset = Dataset.query.get(dataset_id)
            
            if selected_dataset:
                # Get clean data for this specific dataset
                clean_upload_data = CleanDataUpload.query.filter_by(dataset_id=dataset_id).all()
                
                # Get scraper data for this dataset through raw_data_scraper relationship
                result = db.session.execute(text('''
                    SELECT cds.* FROM clean_data_scraper cds 
                    JOIN raw_data_scraper rds ON cds.raw_data_scraper_id = rds.id 
                    WHERE rds.dataset_id = :dataset_id 
                    ORDER BY cds.created_at DESC
                '''), {'dataset_id': dataset_id})
                clean_scraper_data = result.fetchall()
                
                # Count classified data for this dataset with role-based filtering
                if current_user.is_admin():
                    classified_upload_count = db.session.execute(
                        text("SELECT COUNT(DISTINCT cr.data_id) FROM classification_results cr JOIN clean_data_upload cdu ON cr.data_type = 'upload' AND cr.data_id = cdu.id WHERE cdu.dataset_id = :dataset_id"),
                        {'dataset_id': dataset_id}
                    ).scalar() or 0
                    
                    classified_scraper_count = db.session.execute(
                        text("SELECT COUNT(DISTINCT cr.data_id) FROM classification_results cr JOIN clean_data_scraper cds ON cr.data_type = 'scraper' AND cr.data_id = cds.id JOIN raw_data_scraper rds ON cds.raw_data_scraper_id = rds.id WHERE rds.dataset_id = :dataset_id"),
                        {'dataset_id': dataset_id}
                    ).scalar() or 0
                else:
                    # For regular users, only count their own data
                    classified_upload_count = db.session.execute(
                        text("SELECT COUNT(DISTINCT cr.data_id) FROM classification_results cr JOIN clean_data_upload cdu ON cr.data_type = 'upload' AND cr.data_id = cdu.id JOIN raw_data rd ON cdu.raw_data_id = rd.id WHERE cdu.dataset_id = :dataset_id AND rd.uploaded_by = :user_id"),
                        {'dataset_id': dataset_id, 'user_id': current_user.id}
                    ).scalar() or 0
                    
                    classified_scraper_count = db.session.execute(
                        text("SELECT COUNT(DISTINCT cr.data_id) FROM classification_results cr JOIN clean_data_scraper cds ON cr.data_type = 'scraper' AND cr.data_id = cds.id JOIN raw_data_scraper rds ON cds.raw_data_scraper_id = rds.id WHERE rds.dataset_id = :dataset_id AND rds.scraped_by = :user_id"),
                        {'dataset_id': dataset_id, 'user_id': current_user.id}
                    ).scalar() or 0
                
                classified_count = classified_upload_count + classified_scraper_count
            else:
                clean_upload_data = []
                clean_scraper_data = []
        else:
            # Get all clean data
            clean_upload_data = CleanDataUpload.query.all()
            
            # Use raw SQL for CleanDataScraper to avoid ORM issues
            result = db.session.execute(text('SELECT * FROM clean_data_scraper ORDER BY created_at DESC'))
            clean_scraper_data = result.fetchall()
            
            # Count all classified data
            classified_count = db.session.execute(
                text("SELECT COUNT(DISTINCT CONCAT(data_type, '_', data_id)) FROM classification_results")
            ).scalar() or 0
        
        # Calculate counts for template
        clean_upload_count = len(clean_upload_data)
        clean_scraper_count = len(clean_scraper_data)
        total_data_count = clean_upload_count + clean_scraper_count
        
        return render_template('classification/index.html',
                             clean_upload_data=clean_upload_data,
                             clean_scraper_data=clean_scraper_data,
                             clean_upload_count=clean_upload_count,
                             clean_scraper_count=clean_scraper_count,
                             total_data_count=total_data_count,
                             selected_dataset=selected_dataset,
                             classified_count=classified_count)

    # Add redirect route for /classify to /classification
    @app.route('/classify')
    @login_required
    @active_user_required
    def classify_redirect():
        return redirect(url_for('classification'))
    
    # Add redirect route for /admin/login to regular login
    @app.route('/admin/login')
    def admin_login_redirect():
        return redirect(url_for('login'))
    
    @app.route('/api/clean_data/<data_type>')
    @login_required
    def get_clean_data(data_type):
        """
        API endpoint untuk mengambil data bersih berdasarkan tipe
        """
        try:
            if data_type == 'upload':
                # Ambil data dari dataset upload dengan role-based filtering
                if current_user.is_admin():
                    result = db.session.execute(text("""
                        SELECT cdu.id, cdu.platform, cdu.username, cdu.content, 
                               cdu.cleaned_content, cdu.created_at, d.name as dataset_name,
                               EXISTS (
                                   SELECT 1 FROM classification_results cr 
                                   WHERE cr.data_type = 'upload' AND cr.data_id = cdu.id
                               ) as is_classified
                        FROM clean_data_upload cdu
                        LEFT JOIN datasets d ON cdu.dataset_id = d.id
                        WHERE cdu.cleaned_content IS NOT NULL
                        ORDER BY cdu.created_at DESC
                    """))
                else:
                    result = db.session.execute(text("""
                        SELECT cdu.id, cdu.platform, cdu.username, cdu.content, 
                               cdu.cleaned_content, cdu.created_at, d.name as dataset_name,
                               EXISTS (
                                   SELECT 1 FROM classification_results cr 
                                   WHERE cr.data_type = 'upload' AND cr.data_id = cdu.id
                               ) as is_classified
                        FROM clean_data_upload cdu
                        LEFT JOIN datasets d ON cdu.dataset_id = d.id
                        WHERE cdu.cleaned_content IS NOT NULL AND cdu.cleaned_by = :user_id
                        ORDER BY cdu.created_at DESC
                    """), {'user_id': current_user.id})
                
                data = [{
                    'id': row.id,
                    'platform': row.platform,
                    'username': row.username,
                    'content': row.content,
                    'cleaned_content': row.cleaned_content,
                    'created_at': row.created_at.isoformat() if row.created_at else None,
                    'dataset_name': row.dataset_name,
                    'is_classified': bool(row.is_classified)
                } for row in result]
                
                return jsonify({'success': True, 'data': data})
                
            elif data_type == 'scraper':
                # Ambil data dari dataset scraper dengan role-based filtering
                if current_user.is_admin():
                    result = db.session.execute(text("""
                        SELECT cds.id, cds.platform, cds.username, cds.content, 
                               cds.cleaned_content, cds.created_at, d.name as dataset_name,
                               EXISTS (
                                   SELECT 1 FROM classification_results cr 
                                   WHERE cr.data_type = 'scraper' AND cr.data_id = cds.id
                               ) as is_classified
                        FROM clean_data_scraper cds
                        LEFT JOIN datasets d ON cds.dataset_id = d.id
                        WHERE cds.cleaned_content IS NOT NULL
                        ORDER BY cds.created_at DESC
                    """))
                else:
                    result = db.session.execute(text("""
                        SELECT cds.id, cds.platform, cds.username, cds.content, 
                               cds.cleaned_content, cds.created_at, d.name as dataset_name,
                               EXISTS (
                                   SELECT 1 FROM classification_results cr 
                                   WHERE cr.data_type = 'scraper' AND cr.data_id = cds.id
                               ) as is_classified
                        FROM clean_data_scraper cds
                        LEFT JOIN datasets d ON cds.dataset_id = d.id
                        WHERE cds.cleaned_content IS NOT NULL AND cds.cleaned_by = :user_id
                        ORDER BY cds.created_at DESC
                    """), {'user_id': current_user.id})
                
                data = [{
                    'id': row.id,
                    'platform': row.platform,
                    'username': row.username,
                    'content': row.content,
                    'cleaned_content': row.cleaned_content,
                    'created_at': row.created_at.isoformat() if row.created_at else None,
                    'dataset_name': row.dataset_name,
                    'is_classified': bool(row.is_classified)
                } for row in result]
                
                return jsonify({'success': True, 'data': data})
            
            else:
                return jsonify({'success': False, 'message': 'Tipe data tidak valid'}), 400
            
        except Exception as e:
            current_app.logger.error(f"Error in get_clean_data: {str(e)}")
            return jsonify({'success': False, 'message': 'Terjadi kesalahan saat mengambil data'}), 500

    @app.route('/classification/classify')
    @login_required
    @active_user_required
    def classify():
        """
        Endpoint untuk halaman klasifikasi manual dan batch
        """
        classification_type = request.args.get('type', 'batch')
        
        # Get model status
        word2vec_model = current_app.config.get('WORD2VEC_MODEL')
        naive_bayes_models = current_app.config.get('NAIVE_BAYES_MODELS', {})
        
        # Prepare model status data
        word2vec_status = word2vec_model is not None
        word2vec_info = "Model Word2Vec siap digunakan" if word2vec_status else "Model Word2Vec tidak tersedia"
        
        nb1_status = naive_bayes_models.get('model1') is not None
        nb1_info = "Model Naive Bayes 1 siap digunakan" if nb1_status else "Model Naive Bayes 1 tidak tersedia"
        
        nb2_status = naive_bayes_models.get('model2') is not None
        nb2_info = "Model Naive Bayes 2 siap digunakan" if nb2_status else "Model Naive Bayes 2 tidak tersedia"
        
        nb3_status = naive_bayes_models.get('model3') is not None
        nb3_info = "Model Naive Bayes 3 siap digunakan" if nb3_status else "Model Naive Bayes 3 tidak tersedia"
        
        if classification_type == 'manual':
            # For manual classification, get actual data count instead of N/A
            from models import CleanDataUpload, CleanDataScraper, ClassificationResult
            from sqlalchemy import func
            
            # Count clean data ready for classification
            if current_user.is_admin():
                clean_upload_count = CleanDataUpload.query.count()
                clean_scraper_count = CleanDataScraper.query.count()
            else:
                clean_upload_count = CleanDataUpload.query.filter_by(cleaned_by=current_user.id).count()
                clean_scraper_count = CleanDataScraper.query.filter_by(cleaned_by=current_user.id).count()
            clean_data_count = clean_upload_count + clean_scraper_count
            
            # Count classified data for manual classification results
            if current_user.is_admin():
                classified_count = ClassificationResult.query.count() or 0
            else:
                classified_count = ClassificationResult.query.filter_by(classified_by=current_user.id).count() or 0
            
            # Count radical and non-radical content
            if current_user.is_admin():
                radical_count = db.session.query(func.count(ClassificationResult.id)).filter(
                    ClassificationResult.prediction == 'radikal'
                ).scalar() or 0
                
                non_radical_count = db.session.query(func.count(ClassificationResult.id)).filter(
                    ClassificationResult.prediction == 'non-radikal'
                ).scalar() or 0
            else:
                radical_count = db.session.query(func.count(ClassificationResult.id)).filter(
                    ClassificationResult.prediction == 'radikal',
                    ClassificationResult.classified_by == current_user.id
                ).scalar() or 0
                
                non_radical_count = db.session.query(func.count(ClassificationResult.id)).filter(
                    ClassificationResult.prediction == 'non-radikal',
                    ClassificationResult.classified_by == current_user.id
                ).scalar() or 0
            
            return render_template('classification/classify.html', 
                                 type='manual',
                                 word2vec_status=word2vec_status,
                                 word2vec_info=word2vec_info,
                                 nb1_status=nb1_status,
                                 nb1_info=nb1_info,
                                 nb2_status=nb2_status,
                                 nb2_info=nb2_info,
                                 nb3_status=nb3_status,
                                 nb3_info=nb3_info,
                                 clean_data_count=clean_data_count,
                                 classified_count=classified_count,
                                 radical_count=radical_count,
                                 non_radical_count=non_radical_count,
                                 recent_classifications=[])
        elif classification_type == 'batch':
            # Get statistics for batch classification
            from models import CleanDataUpload, CleanDataScraper, ClassificationResult
            from sqlalchemy import func
            
            # Count clean data ready for classification
            if current_user.is_admin():
                clean_upload_count = CleanDataUpload.query.count()
                clean_scraper_count = CleanDataScraper.query.count()
            else:
                clean_upload_count = CleanDataUpload.query.filter_by(cleaned_by=current_user.id).count()
                clean_scraper_count = CleanDataScraper.query.filter_by(cleaned_by=current_user.id).count()
            clean_data_count = clean_upload_count + clean_scraper_count
            
            # Count classified data
            if current_user.is_admin():
                classified_upload_count = db.session.query(func.count(ClassificationResult.id)).filter(
                    ClassificationResult.data_type == 'upload'
                ).scalar() or 0
                
                classified_scraper_count = db.session.query(func.count(ClassificationResult.id)).filter(
                    ClassificationResult.data_type == 'scraper'
                ).scalar() or 0
            else:
                classified_upload_count = db.session.query(func.count(ClassificationResult.id)).filter(
                    ClassificationResult.data_type == 'upload',
                    ClassificationResult.classified_by == current_user.id
                ).scalar() or 0
                
                classified_scraper_count = db.session.query(func.count(ClassificationResult.id)).filter(
                    ClassificationResult.data_type == 'scraper',
                    ClassificationResult.classified_by == current_user.id
                ).scalar() or 0
            
            classified_count = classified_upload_count + classified_scraper_count
            
            # Count radical and non-radical content
            if current_user.is_admin():
                radical_count = db.session.query(func.count(ClassificationResult.id)).filter(
                    ClassificationResult.prediction == 'radikal'
                ).scalar() or 0
                
                non_radical_count = db.session.query(func.count(ClassificationResult.id)).filter(
                    ClassificationResult.prediction == 'non-radikal'
                ).scalar() or 0
            else:
                radical_count = db.session.query(func.count(ClassificationResult.id)).filter(
                    ClassificationResult.prediction == 'radikal',
                    ClassificationResult.classified_by == current_user.id
                ).scalar() or 0
                
                non_radical_count = db.session.query(func.count(ClassificationResult.id)).filter(
                    ClassificationResult.prediction == 'non-radikal',
                    ClassificationResult.classified_by == current_user.id
                ).scalar() or 0
            
            # Get recent classifications for batch mode with platform information
            if current_user.is_admin():
                recent_classifications = db.session.query(
                    ClassificationResult,
                    db.func.coalesce(CleanDataUpload.platform, CleanDataScraper.platform).label('platform'),
                    db.func.coalesce(CleanDataUpload.cleaned_content, CleanDataScraper.cleaned_content).label('content'),
                    db.case(
                        (ClassificationResult.is_corrected == True, ClassificationResult.corrected_prediction),
                        else_=ClassificationResult.prediction
                    ).label('final_prediction')
                ).outerjoin(CleanDataUpload, db.and_(
                    ClassificationResult.data_type == 'upload',
                    ClassificationResult.data_id == CleanDataUpload.id
                )).outerjoin(CleanDataScraper, db.and_(
                    ClassificationResult.data_type == 'scraper',
                    ClassificationResult.data_id == CleanDataScraper.id
                )).order_by(
                    ClassificationResult.created_at.desc()
                ).limit(5).all()
            else:
                recent_classifications = db.session.query(
                    ClassificationResult,
                    db.func.coalesce(CleanDataUpload.platform, CleanDataScraper.platform).label('platform'),
                    db.func.coalesce(CleanDataUpload.cleaned_content, CleanDataScraper.cleaned_content).label('content'),
                    db.case(
                        (ClassificationResult.is_corrected == True, ClassificationResult.corrected_prediction),
                        else_=ClassificationResult.prediction
                    ).label('final_prediction')
                ).outerjoin(CleanDataUpload, db.and_(
                    ClassificationResult.data_type == 'upload',
                    ClassificationResult.data_id == CleanDataUpload.id
                )).outerjoin(CleanDataScraper, db.and_(
                    ClassificationResult.data_type == 'scraper',
                    ClassificationResult.data_id == CleanDataScraper.id
                )).filter(
                    ClassificationResult.classified_by == current_user.id
                ).order_by(
                    ClassificationResult.created_at.desc()
                ).limit(5).all()
            
            return render_template('classification/classify.html', 
                                 type='batch',
                                 word2vec_status=word2vec_status,
                                 word2vec_info=word2vec_info,
                                 nb1_status=nb1_status,
                                 nb1_info=nb1_info,
                                 nb2_status=nb2_status,
                                 nb2_info=nb2_info,
                                 nb3_status=nb3_status,
                                 nb3_info=nb3_info,
                                 clean_data_count=clean_data_count,
                                 classified_count=classified_count,
                                 radical_count=radical_count,
                                 non_radical_count=non_radical_count,
                                 recent_classifications=recent_classifications)
        else:
            flash('Tipe klasifikasi tidak valid!', 'error')
            return redirect(url_for('classification'))

    @app.route('/classification/classify/<data_type>/<int:data_id>')
    @login_required
    def classify_data(data_type, data_id):
        try:
            if data_type == 'upload':
                clean_data = CleanDataUpload.query.get_or_404(data_id)
                content = clean_data.cleaned_content
            elif data_type == 'scraper':
                # Use raw SQL for CleanDataScraper
                result = db.session.execute(text("SELECT * FROM clean_data_scraper WHERE id = :data_id"), {'data_id': data_id})
                clean_data = result.fetchone()
                if not clean_data:
                    abort(404)
                content = clean_data.cleaned_content
            elif data_type == 'batch':
                # Redirect to batch classification page
                return redirect(url_for('batch_classification'))
            else:
                flash('Silakan pilih data di Dataset Management untuk melakukan klasifikasi!', 'info')
                return redirect(url_for('classification'))
            
            # Check if already classified
            result = db.session.execute(text("SELECT * FROM classification_results WHERE data_type = :data_type AND data_id = :data_id LIMIT 1"), {'data_type': data_type, 'data_id': data_id})
            existing_classification = result.fetchone()
            
            if existing_classification:
                flash('Data sudah diklasifikasi sebelumnya!', 'warning')
                return redirect(url_for('classification'))
            
            # Get models from app config
            word2vec_model = current_app.config.get('WORD2VEC_MODEL')
            naive_bayes_models = current_app.config.get('NAIVE_BAYES_MODELS', {})
            
            # Vectorize content using Word2Vec
            if word2vec_model:
                vector = vectorize_text(content, word2vec_model)
                
                # Classify using all three models
                for model_name, model in naive_bayes_models.items():
                    if model:
                        prediction, probabilities = classify_content(vector, model)
                        
                        # Save classification result
                        # Handle probabilities consistently
                        if isinstance(probabilities, (list, tuple, np.ndarray)) and len(probabilities) >= 2:
                            prob_non_radikal = float(probabilities[0])
                            prob_radikal = float(probabilities[1])
                        else:
                            prob_non_radikal = 0.0
                            prob_radikal = 0.0
                        
                        result = ClassificationResult(
                            data_type=data_type,
                            data_id=data_id,
                            model_name=model_name,
                            prediction=prediction,
                            probability_radikal=prob_radikal,
                            probability_non_radikal=prob_non_radikal,
                            classified_by=current_user.id
                        )
                        db.session.add(result)
                
                # Update raw data status to 'classified' for scraper data
                if data_type == 'scraper':
                    # Update RawDataScraper status
                    raw_scraper_result = db.session.execute(text("SELECT raw_data_scraper_id FROM clean_data_scraper WHERE id = :data_id"), {'data_id': data_id})
                    raw_scraper_row = raw_scraper_result.fetchone()
                    if raw_scraper_row:
                        raw_scraper = RawDataScraper.query.get(raw_scraper_row.raw_data_scraper_id)
                        if raw_scraper:
                            raw_scraper.status = 'classified'
                elif data_type == 'upload':
                    # Update RawData status
                    clean_upload = CleanDataUpload.query.get(data_id)
                    if clean_upload:
                        raw_upload = RawData.query.get(clean_upload.raw_data_id)
                        if raw_upload:
                            raw_upload.status = 'classified'
                
                db.session.commit()
                
                # Update statistics
                update_statistics()
                
                flash('Data berhasil diklasifikasi dengan 3 model!', 'success')
            else:
                flash('Model Word2Vec tidak tersedia!', 'error')
                
        except Exception as e:
            db.session.rollback()
            flash(f'Error klasifikasi data: {str(e)}', 'error')
        
        return redirect(url_for('classification'))
    
    @app.route('/classification/results')
    @login_required
    def classification_results():
        # Semua user yang login dapat melihat hasil klasifikasi
        try:
            # Get all classification results from all datasets
            upload_results = db.session.execute(
                text("""
                    SELECT cr.id, cr.data_type, cr.data_id, cr.model_name, cr.prediction, 
                           cr.probability_radikal, cr.probability_non_radikal, cr.classified_at,
                           cdu.cleaned_content as content, cdu.username, cdu.url, cdu.created_at,
                           d.name as dataset_name, d.id as dataset_id
                    FROM classification_results cr 
                    JOIN clean_data_upload cdu ON cr.data_type = 'upload' AND cr.data_id = cdu.id
                    JOIN raw_data rd ON cdu.raw_data_id = rd.id
                    JOIN datasets d ON rd.dataset_id = d.id
                    ORDER BY cr.classified_at DESC
                """)
            ).fetchall()
            
            # Get classification results with joined data for scraper including dataset info (all datasets)
            scraper_results = db.session.execute(
                text("""
                    SELECT cr.id, cr.data_type, cr.data_id, cr.model_name, cr.prediction, 
                           cr.probability_radikal, cr.probability_non_radikal, cr.classified_at,
                           cds.cleaned_content as content, cds.username, cds.url, cds.created_at,
                           d.name as dataset_name, d.id as dataset_id
                    FROM classification_results cr 
                    JOIN clean_data_scraper cds ON cr.data_type = 'scraper' AND cr.data_id = cds.id
                    JOIN raw_data_scraper rds ON cds.raw_data_scraper_id = rds.id
                    JOIN datasets d ON rds.dataset_id = d.id
                    ORDER BY cr.classified_at DESC
                """)
            ).fetchall()
            
            # Combine results
            all_results = list(upload_results) + list(scraper_results)
            
            # Group results by data_id and data_type (only one dataset now)
            data_items_dict = {}
            for result in all_results:
                data_key = f"{result.data_type}_{result.data_id}"
                
                if data_key not in data_items_dict:
                    data_items_dict[data_key] = {
                        'data_id': result.data_id,
                        'data_type': result.data_type,
                        'username': result.username,
                        'content': result.content,
                        'url': result.url,
                        'created_at': result.created_at,
                        'dataset_name': result.dataset_name,
                        'dataset_id': result.dataset_id,
                        'models': {}
                    }
                
                data_items_dict[data_key]['models'][result.model_name] = {
                    'prediction': result.prediction,
                    'probability_radikal': result.probability_radikal,
                    'probability_non_radikal': result.probability_non_radikal
                }
            
            # Convert to final structure for template
            data_items = list(data_items_dict.values())
            data_items.sort(key=lambda x: x['created_at'], reverse=True)
            
            # Calculate statistics for the latest dataset
            total_items = len(data_items)
            # Count all model predictions individually
            radikal_count = 0
            non_radikal_count = 0
            
            for item in data_items:
                # Count all predictions from all models
                for model_name, model_data in item['models'].items():
                    if model_data['prediction'] == 'radikal':
                        radikal_count += 1
                    else:
                        non_radikal_count += 1
            
            # Create final datasets structure for all datasets
            final_datasets = []
            if all_results:
                # Group by dataset
                datasets_dict = {}
                for item in data_items:
                    dataset_id = item['dataset_id']
                    dataset_name = item['dataset_name']
                    
                    if dataset_id not in datasets_dict:
                        datasets_dict[dataset_id] = {
                            'dataset_name': dataset_name,
                            'dataset_id': dataset_id,
                            'data_items': [],
                            'radikal_count': 0,
                            'non_radikal_count': 0
                        }
                    
                    datasets_dict[dataset_id]['data_items'].append(item)
                    
                    # Count predictions for this dataset
                    for model_name, model_data in item['models'].items():
                        if model_data['prediction'] == 'radikal':
                            datasets_dict[dataset_id]['radikal_count'] += 1
                        else:
                            datasets_dict[dataset_id]['non_radikal_count'] += 1
                
                # Convert to final structure
                for dataset_id, dataset_data in datasets_dict.items():
                    total_items = len(dataset_data['data_items'])
                    radikal_count = dataset_data['radikal_count']
                    non_radikal_count = dataset_data['non_radikal_count']
                    
                    final_datasets.append({
                        'dataset_name': dataset_data['dataset_name'],
                        'dataset_id': dataset_id,
                        'data_items': dataset_data['data_items'],
                        'total_items': total_items,
                        'radikal_count': radikal_count,
                        'non_radikal_count': non_radikal_count,
                        'radikal_percentage': (radikal_count / (radikal_count + non_radikal_count) * 100) if (radikal_count + non_radikal_count) > 0 else 0,
                        'non_radikal_percentage': (non_radikal_count / (radikal_count + non_radikal_count) * 100) if (radikal_count + non_radikal_count) > 0 else 0
                    })
                
                # Sort datasets by latest classification time (newest first)
            # Find the latest classification time for each dataset
            for dataset in final_datasets:
                latest_classification_time = None
                for item in dataset['data_items']:
                    if latest_classification_time is None or item['created_at'] > latest_classification_time:
                        latest_classification_time = item['created_at']
                dataset['latest_classification_time'] = latest_classification_time
            
            # Sort datasets by latest classification time descending (newest first)
            final_datasets.sort(key=lambda x: x['latest_classification_time'] or datetime.min, reverse=True)
            
            # Calculate overall statistics - only for the latest dataset (first in the sorted list)
            if final_datasets:
                latest_dataset = final_datasets[0]  # Get the latest dataset (sorted by classification time descending)
                total_classifications = latest_dataset['radikal_count'] + latest_dataset['non_radikal_count']  # Total predictions from latest dataset
                total_data_items = latest_dataset['total_items']
                total_radikal = latest_dataset['radikal_count']
                total_non_radikal = latest_dataset['non_radikal_count']
            else:
                total_classifications = 0
                total_data_items = 0
                total_radikal = 0
                total_non_radikal = 0
            
            # Calculate model-wise statistics - only for the latest dataset
            model_stats = {
                'model1': {'radikal': 0, 'non_radikal': 0},
                'model2': {'radikal': 0, 'non_radikal': 0},
                'model3': {'radikal': 0, 'non_radikal': 0}
            }
            
            if final_datasets:
                latest_dataset_id = final_datasets[0]['dataset_id']
                for result in all_results:
                    # Check if this result belongs to the latest dataset
                    result_dataset_id = None
                    if hasattr(result, 'dataset_id'):
                        result_dataset_id = result.dataset_id
                    elif hasattr(result, '_mapping') and 'dataset_id' in result._mapping:
                        result_dataset_id = result._mapping['dataset_id']
                    
                    if result_dataset_id == latest_dataset_id:
                        if result.prediction == 'radikal':
                            model_stats[result.model_name]['radikal'] += 1
                        else:
                            model_stats[result.model_name]['non_radikal'] += 1
            
            return render_template('classification/results.html', 
                                 datasets=final_datasets, 
                                 total_classifications=total_classifications,
                                 total_data_items=total_data_items,
                                 total_radikal=total_radikal,
                                 total_non_radikal=total_non_radikal,
                                 model_stats=model_stats,
                                 current_date=datetime.now().date())
        except Exception as e:
            flash(f'Error mengambil hasil klasifikasi: {str(e)}', 'error')
            return render_template('classification/results.html', 
                                 datasets=[], 
                                 total_classifications=0,
                                 total_data_items=0,
                                 total_radikal=0,
                                 total_non_radikal=0,
                                 model_stats={'model1': {'radikal': 0, 'non_radikal': 0},
                                             'model2': {'radikal': 0, 'non_radikal': 0},
                                             'model3': {'radikal': 0, 'non_radikal': 0}},
                                 current_date=datetime.now().date())
    
    @app.route('/classification/batch')
    @login_required
    def batch_classification():
        """Batch classification page - now uses dataset selection"""
        return render_template('classification/batch.html')
    
    @app.route('/classification/batch/process', methods=['POST'])
    @login_required
    def process_batch_classification():
        try:
            data = request.get_json()
            dataset_id = data.get('dataset_id')
            selected_data = data.get('selected_data', [])
            
            if not selected_data:
                return jsonify({'success': False, 'message': 'Tidak ada data yang dipilih'})
            
            processed_count = 0
            error_count = 0
            radikal_count = 0
            non_radikal_count = 0
            
            total_data = len(selected_data)
            
            for index, item in enumerate(selected_data):
                try:
                    data_type = item['data_type']
                    data_id = int(item['data_id'])
                    
                    # Get content based on data type
                    if data_type == 'upload':
                        clean_data = CleanDataUpload.query.get(data_id)
                        if not clean_data:
                            error_count += 1
                            continue
                        content = clean_data.cleaned_content
                    elif data_type == 'scraper':
                        result = db.session.execute(text("SELECT * FROM clean_data_scraper WHERE id = :data_id"), {'data_id': data_id})
                        clean_data = result.fetchone()
                        if not clean_data:
                            error_count += 1
                            continue
                        content = clean_data.cleaned_content
                    else:
                        error_count += 1
                        continue
                    
                    # Check if already classified
                    result = db.session.execute(text("SELECT * FROM classification_results WHERE data_type = :data_type AND data_id = :data_id LIMIT 1"), {'data_type': data_type, 'data_id': data_id})
                    existing_classification = result.fetchone()
                    
                    if existing_classification:
                        continue  # Skip if already classified
                    
                    # Get models from app config
                    word2vec_model = current_app.config.get('WORD2VEC_MODEL')
                    naive_bayes_models = current_app.config.get('NAIVE_BAYES_MODELS', {})
                    
                    # Vectorize and classify
                    if word2vec_model:
                        vector = vectorize_text(content, word2vec_model)
                        
                        # Track predictions from all three models
                        model_predictions = []
                        
                        # Classify using all three models
                        for model_name, model in naive_bayes_models.items():
                            if model:
                                prediction, probabilities = classify_content(vector, model)
                                
                                # Save classification result
                                # Handle probabilities consistently
                                if isinstance(probabilities, (list, tuple, np.ndarray)) and len(probabilities) >= 2:
                                    prob_non_radikal = float(probabilities[0])
                                    prob_radikal = float(probabilities[1])
                                else:
                                    prob_non_radikal = 0.0
                                    prob_radikal = 0.0
                                
                                result = ClassificationResult(
                                    data_type=data_type,
                                    data_id=data_id,
                                    model_name=model_name,
                                    prediction=prediction,
                                    probability_radikal=prob_radikal,
                                    probability_non_radikal=prob_non_radikal,
                                    classified_by=current_user.id,
                                    created_at=datetime.now()
                                )
                                db.session.add(result)
                                
                                model_predictions.append(prediction)
                        
                        # Count ALL radikal/non-radikal predictions from all three models
                        if model_predictions:
                            radikal_count += model_predictions.count('radikal')
                            non_radikal_count += model_predictions.count('non-radikal')
                        
                        processed_count += 1
                    else:
                        error_count += 1
                        
                except Exception as e:
                    error_count += 1
                    continue
            
            db.session.commit()
            
            # Update statistics after batch classification
            try:
                from scheduler import cleanup_scheduler
                cleanup_scheduler.update_statistics()
            except Exception as e:
                current_app.logger.error(f"Error updating statistics: {str(e)}")
            
            return jsonify({
                'success': True,
                'processed': processed_count,
                'errors': error_count,
                'radikal_count': radikal_count,
                'non_radikal_count': non_radikal_count,
                'total_data': total_data,
                'message': f'Berhasil memproses {processed_count} data, {error_count} error'
            })
            
        except Exception as e:
            db.session.rollback()
            return jsonify({'success': False, 'message': f'Error: {str(e)}'})
    


    @app.route('/api/classification/latest-results', methods=['GET'])
    @login_required
    def get_latest_classification_results():
        """Get latest classification results for the current session"""
        try:
            # Get the most recent dataset that was classified (by any user)
            # Find the latest dataset by checking the most recent classification result
            latest_classification = ClassificationResult.query.order_by(
                ClassificationResult.created_at.desc()
            ).first()
            
            if not latest_classification:
                latest_dataset = None
            else:
                # Get dataset based on data type
                if latest_classification.data_type == 'upload':
                    clean_data = CleanDataUpload.query.get(latest_classification.data_id)
                    if clean_data:
                        raw_data = RawData.query.get(clean_data.raw_data_id)
                        latest_dataset = Dataset.query.get(raw_data.dataset_id) if raw_data else None
                else:  # scraper
                    clean_data = CleanDataScraper.query.get(latest_classification.data_id)
                    if clean_data:
                        raw_data = RawDataScraper.query.get(clean_data.raw_data_scraper_id)
                        latest_dataset = Dataset.query.get(raw_data.dataset_id) if raw_data else None
            
            # Debug: Log which dataset we found
            if latest_dataset:
                app.logger.info(f"Found latest dataset: {latest_dataset.name} (ID: {latest_dataset.id})")
            else:
                app.logger.info("No latest dataset found")
            
            if not latest_dataset:
                return jsonify({
                    'success': True,
                    'results': {
                        'total_classifications': 0,
                        'total_radikal': 0,
                        'total_non_radikal': 0,
                        'radikal_percentage': 0,
                        'non_radikal_percentage': 0,
                        'model_stats': {
                            'model1': {'radikal': 0, 'non_radikal': 0},
                            'model2': {'radikal': 0, 'non_radikal': 0},
                            'model3': {'radikal': 0, 'non_radikal': 0}
                        }
                    }
                })
            
            # Get classification results for the latest dataset only
            # First, get all clean data IDs that belong to this dataset
            clean_data_ids = []
            
            # For upload data
            clean_uploads = CleanDataUpload.query\
                .join(RawData, CleanDataUpload.raw_data_id == RawData.id)\
                .filter(RawData.dataset_id == latest_dataset.id)\
                .all()
            clean_data_ids.extend([('upload', upload.id) for upload in clean_uploads])
            
            # For scraper data  
            clean_scrapers = CleanDataScraper.query\
                .join(RawDataScraper, CleanDataScraper.raw_data_scraper_id == RawDataScraper.id)\
                .filter(RawDataScraper.dataset_id == latest_dataset.id)\
                .all()
            clean_data_ids.extend([('scraper', scraper.id) for scraper in clean_scrapers])
            
            # Now get classification results for these clean data IDs
            # Hapus filter classified_by agar semua user dapat melihat semua hasil
            results = []
            for data_type, data_id in clean_data_ids:
                dataset_results = ClassificationResult.query\
                    .filter(
                        ClassificationResult.data_type == data_type,
                        ClassificationResult.data_id == data_id
                    )\
                    .all()
                results.extend(dataset_results)
            
            # Debug: Log the number of clean data IDs and results found
            app.logger.info(f"Latest dataset: {latest_dataset.name}, Clean data IDs: {len(clean_data_ids)}, Results found: {len(results)}")
            
            # Calculate statistics
            total_classifications = len(results)
            
            # Count predictions by model
            model_stats = {
                'model1': {'radikal': 0, 'non_radikal': 0},
                'model2': {'radikal': 0, 'non_radikal': 0},
                'model3': {'radikal': 0, 'non_radikal': 0}
            }
            
            for result in results:
                if result.prediction == 'radikal':
                    model_stats[result.model_name]['radikal'] += 1
                else:
                    model_stats[result.model_name]['non_radikal'] += 1
            
            # Calculate totals
            total_radikal = sum(stats['radikal'] for stats in model_stats.values())
            total_non_radikal = sum(stats['non_radikal'] for stats in model_stats.values())
            
            # Calculate percentages
            total_predictions = total_radikal + total_non_radikal
            radikal_percentage = (total_radikal / total_predictions * 100) if total_predictions > 0 else 0
            non_radikal_percentage = (total_non_radikal / total_predictions * 100) if total_predictions > 0 else 0
            
            return jsonify({
                'success': True,
                'results': {
                    'total_classifications': total_classifications,
                    'total_radikal': total_radikal,
                    'total_non_radikal': total_non_radikal,
                    'radikal_percentage': round(radikal_percentage, 1),
                    'non_radikal_percentage': round(non_radikal_percentage, 1),
                    'model_stats': model_stats
                }
            })
            
        except Exception as e:
            return jsonify({
                'success': False,
                'message': f'Error fetching latest results: {str(e)}'
            })

    @app.route('/api/classification/reset-latest', methods=['POST'])
    @login_required
    def reset_latest_classification_results():
        """Reset latest classification results for the current user, limited to a dataset"""
        try:
            data = request.get_json(silent=True) or {}
            dataset_id = data.get('dataset_id')
            if not dataset_id:
                return jsonify({'success': False, 'message': 'Dataset ID diperlukan untuk reset hasil terbaru'}), 400

            twenty_four_hours_ago = datetime.utcnow() - timedelta(hours=24)

            # Collect IDs of classification results for uploads in the specified dataset
            upload_ids = [row[0] for row in db.session.query(ClassificationResult.id)
                .join(CleanDataUpload, ClassificationResult.data_id == CleanDataUpload.id)
                .join(RawData, RawData.id == CleanDataUpload.raw_data_id)
                .filter(
                    ClassificationResult.data_type == 'upload',
                    RawData.dataset_id == dataset_id,
                    ClassificationResult.classified_by == current_user.id,
                    ClassificationResult.created_at >= twenty_four_hours_ago
                ).all()]

            # Collect IDs of classification results for scraper in the specified dataset
            scraper_ids = [row[0] for row in db.session.query(ClassificationResult.id)
                .join(CleanDataScraper, ClassificationResult.data_id == CleanDataScraper.id)
                .join(RawDataScraper, RawDataScraper.id == CleanDataScraper.raw_data_scraper_id)
                .filter(
                    ClassificationResult.data_type == 'scraper',
                    RawDataScraper.dataset_id == dataset_id,
                    ClassificationResult.classified_by == current_user.id,
                    ClassificationResult.created_at >= twenty_four_hours_ago
                ).all()]

            ids_to_delete = upload_ids + scraper_ids

            deleted_count = 0
            if ids_to_delete:
                deleted_count = ClassificationResult.query.filter(
                    ClassificationResult.id.in_(ids_to_delete)
                ).delete(synchronize_session=False)

            db.session.commit()

            return jsonify({
                'success': True,
                'message': f'Berhasil mereset {deleted_count} hasil klasifikasi terbaru untuk dataset {dataset_id}',
                'deleted_count': deleted_count
            })

        except Exception as e:
            db.session.rollback()
            return jsonify({
                'success': False,
                'message': f'Error resetting latest results: {str(e)}'
            })
    
    @app.route('/api/classification/start', methods=['POST'])
    @login_required
    def start_classification():
        """Start classification without progress tracking"""
        try:
            data = request.get_json()
            dataset_id_raw = data.get('dataset_id')
            try:
                dataset_id = int(str(dataset_id_raw))
            except Exception:
                return jsonify({'success': False, 'message': 'Dataset ID tidak valid'}), 400
            
            if not dataset_id:
                return jsonify({'success': False, 'message': 'Dataset ID diperlukan'})
            
            # Validate dataset exists before starting
            dataset = Dataset.query.get(dataset_id)
            if not dataset:
                return jsonify({'success': False, 'message': 'Dataset tidak ditemukan'}), 404

            # Start classification in background thread
            import threading
            thread = threading.Thread(
                target=process_classification_simple,
                args=(dataset_id, current_user.id),
                name=f"classification_thread_{dataset_id}"
            )
            thread.daemon = True
            thread.start()
            
            # Log thread start for debugging
            app.logger.info(f"Started classification thread for dataset {dataset_id}")
            
            return jsonify({
                'success': True,
                'message': 'Klasifikasi dimulai. Proses akan berjalan di background.',
                'dataset_id': dataset_id
            })
            
        except Exception as e:
            return jsonify({'success': False, 'message': f'Error: {str(e)}'})
    
    def process_classification_simple(dataset_id, user_id):
        """Process classification without progress tracking"""
        
        try:
            # Create new app context for this thread
            with app.app_context():
                # Check if dataset still exists before starting
                dataset = Dataset.query.get(dataset_id)
                if not dataset:
                    app.logger.error(f"Dataset {dataset_id} tidak ditemukan atau telah dihapus")
                    return False
                
                # Get clean data for the dataset
                clean_data = []
                
                # Get upload data
                upload_data = CleanDataUpload.query.join(RawData).filter(RawData.dataset_id == dataset_id).all()
                for data in upload_data:
                    clean_data.append({
                        'data_type': 'upload',
                        'data_id': data.id,
                        'content': data.cleaned_content
                    })
                
                # Get scraper data
                scraper_data = db.session.execute(
                    text("""
                        SELECT cds.* 
                        FROM clean_data_scraper cds 
                        JOIN raw_data_scraper rds ON cds.raw_data_scraper_id = rds.id 
                        WHERE rds.dataset_id = :dataset_id
                    """),
                    {'dataset_id': dataset_id}
                ).fetchall()
                
                for data in scraper_data:
                    clean_data.append({
                        'data_type': 'scraper', 
                        'data_id': data.id,
                        'content': data.cleaned_content
                    })
                
                total_data = len(clean_data)
                
                if total_data == 0:
                    app.logger.error(f"Tidak ada data bersih untuk dataset {dataset_id}")
                    return False
                
                # Get models
                word2vec_model = app.config.get('WORD2VEC_MODEL')
                naive_bayes_models = app.config.get('NAIVE_BAYES_MODELS', {})

                # If no NB models are loaded, fail fast with a clear error to avoid false completion
                if not naive_bayes_models:
                    app.logger.error('Model Naive Bayes tidak tersedia. Pastikan path model di .env benar dan server memuatnya.')
                    return False
                
                # Process each item
                processed_count = 0
                error_count = 0
                radikal_count = 0
                non_radikal_count = 0
                
                app.logger.info(f"Starting classification for dataset {dataset_id} with {len(clean_data)} items")
                
                for index, item in enumerate(clean_data):
                    try:
                        data_type = item['data_type']
                        data_id = item['data_id']
                        content = item['content']
                        
                        # Check if already classified for THIS dataset
                        # Hapus pemeriksaan ini agar setiap dataset baru menambah ke statistik yang ada
                        # Data yang sudah diklasifikasi dari dataset lain tetap diproses untuk statistik akumulatif
                        
                        # Vectorize and classify using available models
                        vector = vectorize_text(content, word2vec_model)
                        model_predictions = []

                        # Classify using all available Naive Bayes models
                        for model_name, model in naive_bayes_models.items():
                            if model:
                                prediction, probabilities = classify_content(vector, model)

                                # Map probabilities to radikal / non-radikal
                                prob_radikal, prob_non_radikal = 0.0, 0.0
                                try:
                                    classes = getattr(model, 'classes_', None)
                                    if isinstance(probabilities, (list, tuple, np.ndarray)) and len(probabilities) >= 2:
                                        if classes is not None and len(classes) == len(probabilities):
                                            classes_list = list(classes)
                                            idx_rad = classes_list.index('Radikal') if 'Radikal' in classes_list else 1
                                            idx_non = classes_list.index('Non-Radikal') if 'Non-Radikal' in classes_list else 0
                                            prob_radikal = float(probabilities[idx_rad])
                                            prob_non_radikal = float(probabilities[idx_non])
                                        else:
                                            # Fallback: assume [Non-Radikal, Radikal]
                                            prob_non_radikal = float(probabilities[0])
                                            prob_radikal = float(probabilities[1])
                                except Exception:
                                    # Keep defaults on mapping error
                                    pass

                                result = ClassificationResult(
                                    data_type=data_type,
                                    data_id=data_id,
                                    model_name=model_name,
                                    prediction=prediction,
                                    probability_radikal=prob_radikal,
                                    probability_non_radikal=prob_non_radikal,
                                    classified_by=user_id,
                                    created_at=datetime.now()
                                )
                                db.session.add(result)
                                model_predictions.append(prediction)

                        # Count predictions
                        if model_predictions:
                            radikal_count += model_predictions.count('radikal')
                            non_radikal_count += model_predictions.count('non-radikal')

                        processed_count += 1
                        
                        # Commit every 10 items to reduce database load
                        if processed_count % 10 == 0:
                            db.session.commit()
                            app.logger.info(f"Processed {processed_count}/{total_data} items")
                            
                    except Exception as e:
                        error_count += 1
                        app.logger.error(f"Error processing item {index + 1}/{len(clean_data)}: {str(e)}")
                        continue
                
                # Final commit
                db.session.commit()
                
                # Update statistics
                try:
                    update_statistics_simplified()
                    app.logger.info("Statistics updated successfully")
                except Exception as e:
                    app.logger.error(f"Error updating statistics: {str(e)}")
                
                app.logger.info(f"Classification completed for dataset {dataset_id}. Processed: {processed_count}, Errors: {error_count}, Radikal: {radikal_count}, Non-Radikal: {non_radikal_count}")
                
                # Update dataset status to 'Terklasifikasi' in database
                try:
                    dataset.status = 'Terklasifikasi'
                    dataset.classified_at = datetime.now()
                    db.session.commit()
                    app.logger.info(f"Dataset {dataset_id} marked as classified")
                except Exception as e:
                    app.logger.error(f"Error updating dataset status: {str(e)}")
                
                return True
                
        except Exception as e:
            app.logger.error(f"Error in classification process: {str(e)}")
            return False

        except Exception as e:
            # Use app.logger directly since we might be outside app context
            app.logger.error(f"Critical error in classification process: {str(e)}")
            import traceback
            app.logger.error(f"Full traceback: {traceback.format_exc()}")
    
    # Removed duplicate admin_panel route - using /admin_panel instead
    
    @app.route('/admin/user/add', methods=['POST'])
    @login_required
    @admin_required
    def admin_add_user():
        try:
            # Sanitize input data
            username = SecurityValidator.sanitize_input(
                request.form.get('username', ''), max_length=50
            )
            email = SecurityValidator.sanitize_input(
                request.form.get('email', ''), max_length=100
            )
            password = request.form.get('password', '')  # Don't sanitize password
            role = SecurityValidator.sanitize_input(
                request.form.get('role', 'user'), max_length=20
            )
            
            # Validation
            if not username or not email or not password:
                log_security_event(
                    "USER_CREATION_INVALID", 
                    "Admin user creation attempt with missing fields",
                    user_id=current_user.id,
                    ip_address=request.remote_addr
                )
                return jsonify({'success': False, 'message': 'Semua field harus diisi!'})
            
            if len(username) < 3:
                return jsonify({'success': False, 'message': 'Username minimal 3 karakter!'})
            
            if len(password) < 6:
                return jsonify({'success': False, 'message': 'Password minimal 6 karakter!'})
            
            if User.query.filter_by(username=username).first():
                return jsonify({'success': False, 'message': 'Username sudah digunakan!'})
            
            if User.query.filter_by(email=email).first():
                return jsonify({'success': False, 'message': 'Email sudah digunakan!'})
            
            # Create new user
            user = User(username=username, email=email, role=role)
            user.set_password(password)
            
            db.session.add(user)
            db.session.commit()
            
            # Log successful user creation
            log_security_event(
                "USER_CREATED", 
                f"Admin created new user: {username} with role: {role}",
                user_id=current_user.id,
                ip_address=request.remote_addr
            )
            
            return jsonify({'success': True, 'message': 'User berhasil ditambahkan!'})
            
        except Exception as e:
            db.session.rollback()
            log_security_event(
                "USER_CREATION_ERROR", 
                f"Error creating user: {str(e)}",
                user_id=current_user.id,
                ip_address=request.remote_addr
            )
            return jsonify({'success': False, 'message': f'Error: {str(e)}'})
    
    @app.route('/admin/user/<int:user_id>/edit', methods=['POST'])
    @login_required
    @admin_required
    def admin_edit_user(user_id):
        try:
            user = User.query.get_or_404(user_id)
            
            # Sanitize input data
            username = SecurityValidator.sanitize_input(
                request.form.get('username', ''), max_length=50
            )
            email = SecurityValidator.sanitize_input(
                request.form.get('email', ''), max_length=100
            )
            role = SecurityValidator.sanitize_input(
                request.form.get('role', 'user'), max_length=20
            )
            is_active = request.form.get('is_active') == 'true'
            
            # Validation
            if not username or not email:
                log_security_event(
                    "USER_EDIT_INVALID", 
                    f"Admin user edit attempt with missing fields for user ID: {user_id}",
                    user_id=current_user.id,
                    ip_address=request.remote_addr
                )
                return jsonify({'success': False, 'message': 'Username dan email harus diisi!'})
            
            if len(username) < 3:
                return jsonify({'success': False, 'message': 'Username minimal 3 karakter!'})
            
            # Check if username/email already exists (excluding current user)
            existing_user = User.query.filter(
                User.username == username,
                User.id != user_id
            ).first()
            if existing_user:
                return jsonify({'success': False, 'message': 'Username sudah digunakan!'})
            
            existing_email = User.query.filter(
                User.email == email,
                User.id != user_id
            ).first()
            if existing_email:
                return jsonify({'success': False, 'message': 'Email sudah digunakan!'})
            
            # Update user
            user.username = username
            user.email = email
            user.role = role
            user.is_active = is_active
            
            db.session.commit()
            
            return jsonify({'success': True, 'message': 'User berhasil diperbarui!'})
            
        except Exception as e:
            db.session.rollback()
            return jsonify({'success': False, 'message': f'Error: {str(e)}'})
    
    @app.route('/admin/user/<int:user_id>/delete', methods=['POST'])
    @login_required
    @admin_required
    def admin_delete_user(user_id):
        try:
            user = User.query.get_or_404(user_id)
            
            # Prevent deleting the last admin
            if user.is_admin():
                admin_count = User.query.filter_by(role='admin').count()
                if admin_count <= 1:
                    return jsonify({'success': False, 'message': 'Tidak dapat menghapus admin terakhir!'})
            
            # Prevent self-deletion
            if user.id == current_user.id:
                return jsonify({'success': False, 'message': 'Tidak dapat menghapus akun sendiri!'})
            
            db.session.delete(user)
            db.session.commit()
            
            return jsonify({'success': True, 'message': 'User berhasil dihapus!'})
            
        except Exception as e:
            db.session.rollback()
            return jsonify({'success': False, 'message': f'Error: {str(e)}'})
    
    @app.route('/admin/user/<int:user_id>/toggle-status', methods=['POST'])
    @login_required
    @admin_required
    def admin_toggle_user_status(user_id):
        try:
            user = User.query.get_or_404(user_id)
            
            # Prevent deactivating the last admin
            if user.is_admin() and user.is_active:
                active_admin_count = User.query.filter_by(role='admin', is_active=True).count()
                if active_admin_count <= 1:
                    return jsonify({'success': False, 'message': 'Tidak dapat menonaktifkan admin terakhir!'})
            
            # Prevent self-deactivation
            if user.id == current_user.id and user.is_active:
                return jsonify({'success': False, 'message': 'Tidak dapat menonaktifkan akun sendiri!'})
            
            user.is_active = not user.is_active
            db.session.commit()
            
            status = 'diaktifkan' if user.is_active else 'dinonaktifkan'
            return jsonify({'success': True, 'message': f'User berhasil {status}!'})
            
        except Exception as e:
            db.session.rollback()
            return jsonify({'success': False, 'message': f'Error: {str(e)}'})
    
    @app.route('/admin/user/<int:user_id>/reset-password', methods=['POST'])
    @login_required
    @admin_required
    def admin_reset_password(user_id):
        try:
            user = User.query.get_or_404(user_id)
            new_password = request.form.get('new_password')
            
            if not new_password or len(new_password) < 6:
                return jsonify({'success': False, 'message': 'Password minimal 6 karakter!'})
            
            user.set_password(new_password)
            db.session.commit()
            
            return jsonify({'success': True, 'message': 'Password berhasil direset!'})
            
        except Exception as e:
            db.session.rollback()
            return jsonify({'success': False, 'message': f'Error: {str(e)}'})
    

    
    @app.route('/admin/setup_auto_triggers', methods=['POST'])
    @login_required
    @admin_required
    def admin_setup_auto_triggers():
        """Setup trigger otomatis untuk update statistik dashboard"""
        try:
            if create_auto_update_trigger():
                return jsonify({'success': True, 'message': 'Trigger otomatis berhasil dibuat! Statistik akan terupdate otomatis.'})
            else:
                return jsonify({'success': False, 'message': 'Gagal membuat trigger otomatis.'})
        except Exception as e:
            return jsonify({'success': False, 'message': f'Error: {str(e)}'})
    
    @app.route('/profile')
    @login_required
    def profile():
        # Get user statistics using raw SQL for CleanDataScraper to avoid ORM issues
        from sqlalchemy import text
        from models import UserActivity
        
        # Get clean scraper count using raw SQL
        result = db.session.execute(text('SELECT COUNT(*) FROM clean_data_scraper WHERE cleaned_by = :user_id'), {'user_id': current_user.id})
        clean_scraper_count = result.scalar()
        
        # Calculate user statistics with proper field names for template
        manual_uploads = RawData.query.filter_by(uploaded_by=current_user.id).count()
        scraping_count = RawDataScraper.query.filter_by(scraped_by=current_user.id).count()
        cleaned_data = CleanDataUpload.query.filter_by(cleaned_by=current_user.id).count() + clean_scraper_count
        total_classifications = db.session.execute(text("SELECT COUNT(*) FROM classification_results WHERE classified_by = :user_id"), {'user_id': current_user.id}).scalar()
        
        user_stats = {
            'manual_uploads': manual_uploads,
            'scraping_count': scraping_count,
            'cleaned_data': cleaned_data,
            'total_classifications': total_classifications,
            # Add fields that are used in profile.html template
            'total_uploads': manual_uploads + scraping_count,  # Total upload = manual + scraping
            'total_processed': cleaned_data  # Data diproses = cleaned data
        }
        
        # Get recent activities for the user
        recent_activities_raw = UserActivity.query.filter_by(user_id=current_user.id)\
            .order_by(UserActivity.created_at.desc())\
            .limit(5).all()
        
        # Format activities for template using WIB timezone
        recent_activities = []
        for activity in recent_activities_raw:
            recent_activities.append({
                'date': format_datetime(activity.created_at, 'date_only'),
                'time': format_datetime(activity.created_at, 'time'),
                'title': activity.action.replace('_', ' ').title(),
                'description': activity.description,
                'icon': activity.icon.replace('fa-', '') if activity.icon else 'info-circle',
                'type_color': activity.color or 'blue'
            })
        
        return render_template('profile.html', user_stats=user_stats, recent_activities=recent_activities)
    
    # Profile API Routes
    @app.route('/api/profile/edit', methods=['POST'])
    @login_required
    def edit_profile():
        """Update user profile information"""
        try:
            # Sanitize input data
            email = SecurityValidator.sanitize_input(
                request.form.get('email', ''), max_length=100
            )
            full_name = SecurityValidator.sanitize_input(
                request.form.get('full_name', ''), max_length=100
            )
            bio = SecurityValidator.sanitize_input(
                request.form.get('bio', ''), max_length=500
            )
            
            # Validation
            if not email:
                log_security_event(
                    "PROFILE_EDIT_INVALID", 
                    "Profile edit attempt with empty email",
                    user_id=current_user.id,
                    ip_address=request.remote_addr
                )
                return jsonify({'success': False, 'message': 'Email tidak boleh kosong'}), 400
            
            # Check if email already exists (excluding current user)
            existing_user = User.query.filter(
                User.email == email,
                User.id != current_user.id
            ).first()
            if existing_user:
                return jsonify({'success': False, 'message': 'Email sudah digunakan oleh pengguna lain'}), 400
            
            # Update user profile
            current_user.email = email
            current_user.full_name = full_name if full_name else None
            current_user.bio = bio if bio else None
            current_user.updated_at = datetime.utcnow()
            
            db.session.commit()
            
            # Log activity
            from utils import generate_activity_log
            generate_activity_log(
                action='profile_update',
                description='Profil pengguna berhasil diperbarui',
                user_id=current_user.id,
                details={'email': email, 'full_name': full_name},
                icon='fas fa-user-edit',
                color='warning'
            )
            
            return jsonify({
                'success': True, 
                'message': 'Profil berhasil diperbarui',
                'data': {
                    'email': current_user.email,
                    'full_name': current_user.full_name,
                    'bio': current_user.bio
                }
            })
            
        except Exception as e:
            db.session.rollback()
            return jsonify({'success': False, 'message': f'Terjadi kesalahan: {str(e)}'}), 500
    
    @app.route('/api/profile/change-password', methods=['POST'])
    @login_required
    def change_password():
        """Change user password"""
        try:
            current_password = request.form.get('current_password')
            new_password = request.form.get('new_password')
            
            # Validation
            if not current_password or not new_password:
                return jsonify({'success': False, 'message': 'Password lama dan baru harus diisi'}), 400
            
            if len(new_password) < 6:
                return jsonify({'success': False, 'message': 'Password baru minimal 6 karakter'}), 400
            
            # Verify current password
            if not current_user.check_password(current_password):
                return jsonify({'success': False, 'message': 'Password lama tidak benar'}), 400
            
            # Update password
            current_user.set_password(new_password)
            current_user.updated_at = datetime.utcnow()
            
            db.session.commit()
            
            # Log activity
            from utils import generate_activity_log
            generate_activity_log(
                action='password_change',
                description='Password berhasil diubah',
                user_id=current_user.id
            )
            
            return jsonify({'success': True, 'message': 'Password berhasil diubah'})
            
        except Exception as e:
            db.session.rollback()
            return jsonify({'success': False, 'message': f'Terjadi kesalahan: {str(e)}'}), 500
    
    @app.route('/api/profile/preferences', methods=['POST'])
    @login_required
    def save_preferences():
        """Save user preferences"""
        try:
            preferences = {
                'language': request.form.get('language', 'id'),
                'timezone': request.form.get('timezone', 'Asia/Jakarta'),
                'items_per_page': int(request.form.get('itemsPerPage', 25)),
                'default_dataset': request.form.get('defaultDataset', ''),
                'email_notifications': request.form.get('emailNotifications') == 'true',
                'auto_refresh': request.form.get('autoRefresh') == 'true',
                'dark_mode': request.form.get('darkMode') == 'true',
                'auto_classify': request.form.get('autoClassify') == 'true',
                'show_probability': request.form.get('showProbability') == 'true',
                'compact_view': request.form.get('compactView') == 'true'
            }
            
            # Update user preferences
            current_user.set_preferences(preferences)
            current_user.updated_at = datetime.utcnow()
            
            db.session.commit()
            
            # Log activity
            from utils import generate_activity_log
            generate_activity_log(
                action='preferences_update',
                description='Preferensi pengguna berhasil diperbarui',
                user_id=current_user.id,
                details=preferences
            )
            
            return jsonify({
                'success': True, 
                'message': 'Preferensi berhasil disimpan',
                'data': preferences
            })
            
        except Exception as e:
            db.session.rollback()
            return jsonify({'success': False, 'message': f'Terjadi kesalahan: {str(e)}'}), 500
    
    @app.route('/api/profile/activities', methods=['GET'])
    @login_required
    def get_user_activities():
        """Get user recent activities"""
        try:
            limit = request.args.get('limit', 10, type=int)
            
            from models import UserActivity
            activities = UserActivity.query.filter_by(user_id=current_user.id)\
                                         .order_by(UserActivity.created_at.desc())\
                                         .limit(limit).all()
            
            activities_data = []
            for activity in activities:
                activity_dict = activity.to_dict()
                # Format waktu ke WIB untuk respons API
                activity_dict['created_at'] = format_datetime(activity.created_at, 'full')
                activities_data.append(activity_dict)
            
            return jsonify({
                'success': True,
                'data': activities_data
            })
            
        except Exception as e:
            return jsonify({'success': False, 'message': f'Terjadi kesalahan: {str(e)}'}), 500
    
    # Data Source Routes
    @app.route('/upload')
    @login_required
    @active_user_required
    def upload_page():
        """Display upload page"""
        return render_template('data/upload.html')
    
    @app.route('/upload_data', methods=['POST'])
    @login_required
    @active_user_required
    def upload_data():
        """Handle file upload with enhanced security validation"""
        filepath = None
        try:
            if 'file' not in request.files:
                return jsonify({'success': False, 'message': 'Tidak ada file yang dipilih'}), 400
            
            file = request.files['file']
            if file.filename == '':
                return jsonify({'success': False, 'message': 'Tidak ada file yang dipilih'}), 400
            
            # Use new security validation instead of allowed_file
            is_valid, message, file_info = SecurityValidator.validate_file_upload(file)
            if not is_valid:
                log_security_event(
                    "FILE_UPLOAD_REJECTED", 
                    f"API file upload rejected: {message} | File: {file.filename}",
                    user_id=current_user.id,
                    ip_address=request.remote_addr
                )
                return jsonify({'success': False, 'message': f'Validasi file gagal: {message}'}), 400
            
            # Generate secure filename and path
            try:
                filepath, unique_filename = generate_secure_filename(
                    file.filename, 
                    app.config['UPLOAD_FOLDER']
                )
            except Exception as e:
                return jsonify({'success': False, 'message': f'Error saat memproses nama file: {str(e)}'}), 500
            
            # Create upload directory if not exists and validate write permission with self-healing
            try:
                upload_dir = app.config.get('UPLOAD_FOLDER')
                if not upload_dir:
                    return jsonify({'success': False, 'message': 'Konfigurasi folder upload tidak ditemukan.'}), 500
                os.makedirs(upload_dir, exist_ok=True)

                # Early check
                if not os.access(upload_dir, os.W_OK):
                    app.logger.warning(f"Folder upload tidak writable: {upload_dir}. Mencoba memperbaiki izin...")
                    # Try chmod and chown as fallback (Linux containers)
                    try:
                        os.chmod(upload_dir, 0o775)
                    except Exception as e:
                        app.logger.warning(f"Gagal chmod {upload_dir} ke 775: {e}")
                    if os.name != 'nt':
                        try:
                            uid = os.getuid()
                            gid = os.getgid()
                            os.chown(upload_dir, uid, gid)
                        except Exception as e:
                            app.logger.warning(f"Gagal chown {upload_dir}: {e}")

                # Final check
                if not os.access(upload_dir, os.W_OK):
                    guide = (
                        "Folder upload tidak dapat ditulis. Jika menggunakan Docker, pastikan volume host 'uploads' dimiliki user "
                        "yang kompatibel dengan container (contoh: chown -R $(id -u):$(id -g) uploads && chmod -R 775 uploads)."
                    )
                    return jsonify({'success': False, 'message': guide}), 500
            except Exception as e:
                return jsonify({'success': False, 'message': f'Error saat menyiapkan direktori upload: {str(e)}'}), 500
            
            # Save the file
            try:
                file.save(filepath)
            except PermissionError:
                return jsonify({'success': False, 'message': 'Izin ditolak saat menyimpan file ke folder upload. Hubungi administrator.'}), 500
            except Exception as e:
                return jsonify({'success': False, 'message': f'Error saat menyimpan file: {str(e)}'}), 500
            
            # Log successful upload
            log_security_event(
                "API_FILE_UPLOAD_SUCCESS", 
                f"API file uploaded successfully: {file.filename} -> {unique_filename}",
                user_id=current_user.id,
                ip_address=request.remote_addr
            )
            
            # Get file size in bytes
            try:
                file_size = os.path.getsize(filepath)
            except Exception as e:
                file_size = 0
            
            # Read and process file with proper encoding handling
            if file_info['mime_type'] in ['text/csv', 'text/plain', 'application/csv'] or file_info.get('detected_format') == 'csv':
                # Simpan delimiter & encoding yang digunakan agar konsisten saat baca ulang
                used_delimiter = file_info.get('delimiter')
                used_encoding = None

                # Gunakan chardet untuk deteksi encoding otomatis
                try:
                    import chardet

                    # Baca sampel dari file untuk deteksi encoding
                    file.seek(0)
                    raw_data = file.read(min(file_size, 100000))  # Baca maksimal 100KB untuk deteksi
                    file.seek(0)  # Reset ke awal file

                    # Deteksi encoding
                    result = chardet.detect(raw_data)
                    encoding = result['encoding']
                    confidence = result['confidence']

                    # Gunakan encoding yang terdeteksi jika confidence cukup tinggi
                    if encoding and confidence > 0.7:
                        try:
                            if used_delimiter:
                                df = pd.read_csv(filepath, encoding=encoding, sep=used_delimiter)
                            else:
                                df = pd.read_csv(filepath, encoding=encoding)
                            used_encoding = encoding
                        except Exception:
                            # Lanjutkan ke fallback encodings
                            pass
                except ImportError:
                    # Fallback ke metode encoding yang ada
                    pass
                except Exception:
                    # Fallback ke metode encoding yang ada
                    pass

                # Fallback ke metode encoding yang ada jika auto-detection gagal
                encodings_to_try = ['utf-8', 'utf-8-sig', 'latin1', 'cp1252', 'iso-8859-1']
                df = df if 'df' in locals() else None
                last_error = None

                for encoding in encodings_to_try:
                    if df is not None:
                        break
                    try:
                        if used_delimiter:
                            df = pd.read_csv(filepath, encoding=encoding, sep=used_delimiter)
                        else:
                            df = pd.read_csv(filepath, encoding=encoding)
                        used_encoding = encoding
                        break
                    except (UnicodeDecodeError, UnicodeError) as e:
                        last_error = e
                        continue
                    except Exception as e:
                        # For other errors (like parsing errors), try with error handling
                        try:
                            if used_delimiter:
                                df = pd.read_csv(filepath, encoding=encoding, sep=used_delimiter, on_bad_lines='skip')
                            else:
                                df = pd.read_csv(filepath, encoding=encoding, on_bad_lines='skip')
                            used_encoding = encoding
                            break
                        except Exception as e2:
                            last_error = e2
                            continue

                if df is None:
                    # Clean up the file if we can't process it
                    if os.path.exists(filepath):
                        os.remove(filepath)
                    return jsonify({'success': False, 'message': 'File tidak dapat dibaca. Pastikan format CSV valid.'}), 400
            else:
                try:
                    # Coba baca sebagai Excel
                    try:
                        df = pd.read_excel(filepath)
                    except Exception as excel_error:
                        # Coba baca sebagai CSV jika Excel gagal
                        encodings_to_try = ['utf-8', 'utf-8-sig', 'latin1', 'cp1252', 'iso-8859-1']
                        df = None
                        last_error = excel_error
                        
                        for encoding in encodings_to_try:
                            try:
                                df = pd.read_csv(filepath, encoding=encoding)
                                break
                            except Exception as e:
                                last_error = e
                                continue
                        
                        if df is None:
                            raise last_error
                except Exception as e:
                    # Clean up the file if we can't process it
                    if os.path.exists(filepath):
                        os.remove(filepath)
                    return jsonify({'success': False, 'message': f'Error saat membaca file: {str(e)}'}), 400
            
            # Store file temporarily and show column mapping page

            
            # Get sample data for preview (first 5 rows) with input sanitization
            try:
                sample_df = df.head(5).fillna('')
                
                # Clean sample data to ensure JSON serialization works properly
                sample_data = []
                for _, row in sample_df.iterrows():
                    clean_row = {}
                    for col, value in row.items():
                        # Convert to string and handle special characters
                        if pd.isna(value) or value is None:
                            clean_row[str(col)] = ''
                        else:
                            # Convert to string and handle Unicode properly
                            try:
                                str_value = str(value)
                                # Sanitize the value using security function
                                str_value = SecurityValidator.sanitize_input(str_value, max_length=200)
                                clean_row[str(col)] = str_value
                            except (UnicodeEncodeError, UnicodeDecodeError) as e:
                                # Handle Unicode errors gracefully
                                clean_row[str(col)] = SecurityValidator.sanitize_input(repr(value), max_length=200)
                            except Exception as e:
                                clean_row[str(col)] = '[Error processing value]'
                    sample_data.append(clean_row)
            except Exception as e:
                # Clean up the file if we can't process it
                if os.path.exists(filepath):
                    os.remove(filepath)
                return jsonify({'success': False, 'message': f'Error saat memproses data: {str(e)}'}), 500
            
            # Store file info in session for later processing
            try:
                session['upload_file_path'] = filepath
                session['upload_filename'] = unique_filename
                session['upload_original_filename'] = file.filename  # Store original filename for display
                session['upload_file_size'] = file_size
                session['upload_columns'] = list(df.columns)
                session['upload_sample_data'] = sample_data
                # Simpan parameter pembacaan agar konsisten saat proses mapping
                try:
                    session['upload_used_encoding'] = used_encoding
                    session['upload_used_delimiter'] = used_delimiter
                except Exception:
                    # Abaikan jika bukan CSV
                    pass
                
                # Sanitize form inputs
                session['upload_description'] = SecurityValidator.sanitize_input(
                    request.form.get('description', ''), max_length=500
                )
                session['upload_source'] = SecurityValidator.sanitize_input(
                    request.form.get('source', 'manual'), max_length=50
                )
                
                # Get dataset name from form or use filename as fallback
                dataset_name_input = SecurityValidator.sanitize_input(
                    request.form.get('dataset_name', '').strip(), max_length=100
                )
                if not dataset_name_input:  # If empty or None
                    # Use original filename without extension as dataset name
                    dataset_name_input = os.path.splitext(file.filename)[0]
                    dataset_name_input = SecurityValidator.sanitize_input(dataset_name_input, max_length=100)
                session['upload_dataset_name'] = dataset_name_input
            except Exception as e:
                # Clean up the file if we can't store session data
                if os.path.exists(filepath):
                    os.remove(filepath)
                return jsonify({'success': False, 'message': f'Error saat menyimpan data sesi: {str(e)}'}), 500
            
            # Clean column names to ensure JSON serialization works properly
            try:
                clean_columns = []
                for col in df.columns:
                    # Convert to string and sanitize column names
                    clean_col = SecurityValidator.sanitize_input(str(col), max_length=100)
                    clean_columns.append(clean_col)
                
                return jsonify({
                    'success': True,
                    'show_mapping': True,
                    'columns': clean_columns,
                    'sample_data': sample_data,
                    'filename': unique_filename
                })
            except Exception as e:
                # Clean up the file if we can't prepare response
                if os.path.exists(filepath):
                    os.remove(filepath)
                return jsonify({'success': False, 'message': f'Error saat mempersiapkan data respons: {str(e)}'}), 500
            
        except Exception as e:
            import traceback
            
            db.session.rollback()
            # Clean up the file if it exists
            if filepath and os.path.exists(filepath):
                try:
                    os.remove(filepath)
                except Exception:
                    pass
            
            return jsonify({'success': False, 'message': f'Error: {str(e)}'}), 500
    
    @app.route('/process_column_mapping', methods=['POST'])
    @login_required
    @active_user_required
    def process_column_mapping():
        """Process the column mapping selected by user and save data to database"""
        try:
            # Get mapping data from request
            mapping_data = request.get_json()
            content_column = mapping_data.get('content_column')
            username_column = mapping_data.get('username_column')
            url_column = mapping_data.get('url_column')
            
            # Debug logging
            app.logger.info(f"Column mapping received - content: {content_column}, username: {username_column}, url: {url_column}")
            
            # Validate required mapping
            if not content_column:
                app.logger.error("Content column not provided")
                return jsonify({
                    'success': False,
                    'message': 'Kolom content harus dipilih'
                }), 400
            
            # Get file info from session
            filepath = session.get('upload_file_path')
            filename = session.get('upload_filename')  # Hashed filename for storage
            original_filename = session.get('upload_original_filename')  # Original filename for display
            file_size = session.get('upload_file_size', 0)
            description = session.get('upload_description', '')
            source = session.get('upload_source', 'manual')
            dataset_name = session.get('upload_dataset_name', 'Unknown Dataset')
            
            # Use original filename for display if available, otherwise fallback to hashed filename
            display_filename = original_filename if original_filename else filename
            
            if not filepath or not os.path.exists(filepath):
                return jsonify({
                    'success': False,
                    'message': 'File upload tidak ditemukan. Silakan upload ulang file.'
                }), 400
            
            # Read the file again using the same encoding & delimiter as upload
            used_encoding = session.get('upload_used_encoding')
            used_delimiter = session.get('upload_used_delimiter')
            if str(filename).lower().endswith('.csv'):
                try:
                    if used_delimiter:
                        df = pd.read_csv(filepath, encoding=used_encoding or 'utf-8', sep=used_delimiter, on_bad_lines='skip')
                    else:
                        df = pd.read_csv(filepath, encoding=used_encoding or 'utf-8', on_bad_lines='skip')
                except Exception:
                    # Fallback minimal jika parameter gagal
                    df = pd.read_csv(filepath, on_bad_lines='skip')
            else:
                df = pd.read_excel(filepath)

            # Samakan sanitasi nama kolom dengan yang ditampilkan ke UI saat upload
            df.columns = [SecurityValidator.sanitize_input(str(c), max_length=100) for c in df.columns]

            # Validate selected columns exist
            if content_column not in df.columns:
                return jsonify({
                    'success': False,
                    'message': f'Kolom {content_column} tidak ditemukan dalam file'
                }), 400
            
            # Create or get existing dataset
            dataset = Dataset.query.filter_by(name=dataset_name, uploaded_by=current_user.id).first()
            if not dataset:
                dataset = Dataset(
                    name=dataset_name,
                    description=description,
                    uploaded_by=current_user.id
                )
                db.session.add(dataset)
                db.session.flush()  # Get the dataset ID
            
            # Save data to database
            records_added = 0
            for _, row in df.iterrows():
                if pd.notna(row[content_column]) and str(row[content_column]).strip():
                    content_text = str(row[content_column]).strip()
                    
                    # Get mapped values
                    url_value = row.get(url_column, '') if url_column and url_column in df.columns else ''
                    username_value = row.get(username_column, 'unknown') if username_column and username_column in df.columns else 'unknown'
                    
                    # Ensure username is not empty
                    if not username_value or not str(username_value).strip():
                        username_value = 'unknown'
                    
                    # Auto-detect platform from URL or use default
                    detected_platform = 'manual'  # Default for manual uploads
                    if url_value:
                        if 'twitter.com' in str(url_value) or 'x.com' in str(url_value):
                            detected_platform = 'twitter'
                        elif 'facebook.com' in str(url_value):
                            detected_platform = 'facebook'
                        elif 'tiktok.com' in str(url_value):
                            detected_platform = 'tiktok'
                        elif 'instagram.com' in str(url_value):
                            detected_platform = 'instagram'
                    
                    raw_data = RawData(
                        content=content_text,
                        platform=detected_platform,
                        username=str(username_value).strip(),
                        url=str(url_value) if url_value else '',
                        file_size=file_size,
                        original_filename=secure_filename(filename),
                        dataset_id=dataset.id,
                        dataset_name=dataset_name,
                        uploaded_by=current_user.id
                    )
                    db.session.add(raw_data)
                    records_added += 1
            
            db.session.commit()
            
            # Update dataset total_records
            dataset.total_records = RawData.query.filter_by(dataset_id=dataset.id).count() + RawDataScraper.query.filter_by(dataset_id=dataset.id).count()
            db.session.commit()
            
            # Update statistics
            update_statistics()
            
            # Log aktivitas upload data
            log_message = f'Berhasil mengupload {records_added} data dari file {display_filename}'
            
            generate_activity_log(
                action='upload_data',
                description=log_message,
                user_id=current_user.id,
                details={
                    'filename': display_filename,
                    'records_count': records_added,
                    'dataset_name': dataset_name,
                    'file_size': file_size
                },
                icon='fa-upload',
                color='success'
            )
            
            # Clean up file and session
            os.remove(filepath)
            session.pop('upload_file_path', None)
            session.pop('upload_filename', None)
            session.pop('upload_original_filename', None)
            session.pop('upload_file_size', None)
            session.pop('upload_columns', None)
            session.pop('upload_sample_data', None)
            session.pop('upload_description', None)
            session.pop('upload_source', None)
            session.pop('upload_dataset_name', None)
            
            success_message = f'Berhasil mengupload {records_added} data baru dari file {display_filename}'
            
            # Pastikan response hanya berisi pesan yang bersih tanpa ID apapun
            response_data = {
                'success': True,
                'message': success_message
            }
            
            # Bersihkan session data secara menyeluruh untuk menghindari kebocoran data
            session_keys_to_remove = [
                'upload_file_path', 'upload_filename', 'upload_file_size',
                'upload_columns', 'upload_sample_data', 'upload_description',
                'upload_source', 'upload_dataset_name', 'scraping_temp_id',
                'scraping_data', 'scraping_raw_data', 'scraping_platform',
                'scraping_keyword', 'scraping_date_from', 'scraping_date_to',
                'scraping_dataset_id', 'scraping_dataset_name', 'scraping_run_id'
            ]
            
            for key in session_keys_to_remove:
                session.pop(key, None)
            
            return jsonify(response_data)
            
        except Exception as e:
            db.session.rollback()
            
            # Clean up file if it exists
            filepath = session.get('upload_file_path')
            if filepath and os.path.exists(filepath):
                try:
                    os.remove(filepath)
                except Exception:
                    pass
            
            # Clean session data
            session.pop('upload_file_path', None)
            session.pop('upload_filename', None)
            session.pop('upload_file_size', None)
            session.pop('upload_columns', None)
            session.pop('upload_sample_data', None)
            session.pop('upload_description', None)
            session.pop('upload_source', None)
            session.pop('upload_dataset_name', None)
            
            return jsonify({'success': False, 'message': f'Error: {str(e)}'}), 500
    
    @app.route('/process_scraping_column_mapping', methods=['POST'])
    @login_required
    @active_user_required
    def process_scraping_column_mapping():
        """Process the column mapping selected by user for scraping data and save to database"""
        try:
            # Get mapping data from request
            mapping_data = request.get_json()
            content_column = mapping_data.get('content_column')
            username_column = mapping_data.get('username_column')
            url_column = mapping_data.get('url_column')
            
            # Validate required mapping
            if not content_column:
                return jsonify({
                    'success': False,
                    'message': 'Kolom content harus dipilih'
                }), 400
            
            # Get scraping info from temporary file
            temp_id = session.get('scraping_temp_id')
            scraping_info = None
            
            if temp_id:
                # Read from temporary file
                temp_file_path = os.path.join(tempfile.gettempdir(), f'waskita_scraping_{temp_id}.json')
                
                if os.path.exists(temp_file_path):
                    try:
                        with open(temp_file_path, 'r', encoding='utf-8') as f:
                            scraping_info = json.load(f)
                    except Exception as e:
                        app.logger.error(f"Error reading temp file: {str(e)}")
                        scraping_info = None
            
            if not scraping_info:
                # Fallback to old session format for compatibility
                scraping_info = session.get('scraping_data')
            
            if scraping_info:
                # Extract data from scraping info
                scraped_data = scraping_info.get('scraped_data')
                platform = scraping_info.get('platform')
                keyword = scraping_info.get('keywords')
                date_from = scraping_info.get('start_date')
                date_to = scraping_info.get('end_date')
                dataset_id = scraping_info.get('dataset_id')
                dataset_name = scraping_info.get('dataset_name')
                run_id = scraping_info.get('run_id')
            else:
                # Old format - fallback
                scraped_data = session.get('scraping_raw_data')
                platform = session.get('scraping_platform')
                keyword = session.get('scraping_keyword')
                date_from = session.get('scraping_date_from')
                date_to = session.get('scraping_date_to')
                dataset_id = session.get('scraping_dataset_id')
                dataset_name = session.get('scraping_dataset_name')
                run_id = session.get('scraping_run_id')
            
            if not scraped_data:
                app.logger.error(f"No scraped_data found. Session keys: {list(session.keys())}")
                app.logger.error(f"Scraping info: {scraping_info}")
                return jsonify({
                    'success': False,
                    'message': 'Data scraping tidak ditemukan. Silakan lakukan scraping ulang.'
                }), 400
            
            app.logger.info(f"Found scraped data - platform: {platform}, keyword: {keyword}, dataset_id: {dataset_id}, data_count: {len(scraped_data)}")
            
            # Validate selected columns exist in data
            if scraped_data:
                first_item = scraped_data[0]
                if content_column not in first_item:
                    return jsonify({
                        'success': False,
                        'message': f'Kolom {content_column} tidak ditemukan dalam data scraping'
                    }), 400
            
            # Get dataset
            dataset = Dataset.query.get(dataset_id)
            if not dataset:
                return jsonify({
                    'success': False,
                    'message': 'Dataset tidak ditemukan'
                }), 400
            
            # Save data to database with column mapping
            records_added = 0
            scrape_date = datetime.strptime(date_from, '%Y-%m-%d').date()
            
            app.logger.info(f"Starting to save {len(scraped_data)} records to database")
            
            for data in scraped_data:
                # Get mapped values
                content_value = data.get(content_column, '')
                username_value = data.get(username_column, 'unknown') if username_column and username_column in data else 'unknown'
                url_value = data.get(url_column, '') if url_column and url_column in data else ''
                
                # Skip empty content
                if not content_value or not str(content_value).strip():
                    continue
                
                # Ensure username is not empty
                if not username_value or not str(username_value).strip():
                    username_value = 'unknown'
                
                # Check for duplicate content in scraper data
                content_to_check = str(content_value).strip()
                existing_scraper_data = RawDataScraper.query.filter_by(
                    content=content_to_check,
                    dataset_id=dataset.id,
                    platform=platform,
                    keyword=keyword
                ).first()
                
                if existing_scraper_data:
                    # Skip duplicate content
                    continue
                
                # Extract engagement data based on platform
                likes = data.get('likes', 0) or 0
                retweets = data.get('retweets', 0) or 0
                replies = data.get('replies', 0) or 0
                comments = data.get('comments', 0) or 0
                shares = data.get('shares', 0) or 0
                views = data.get('views', 0) or 0
                
                # Handle TikTok specific engagement fields
                if platform.lower() == 'tiktok':
                    # TikTok uses different field names
                    likes = data.get('diggCount', 0) or data.get('likes', 0) or 0
                    comments = data.get('commentCount', 0) or data.get('comments', 0) or 0
                    shares = data.get('shareCount', 0) or data.get('shares', 0) or 0
                    views = data.get('playCount', 0) or data.get('views', 0) or 0
                
                # Truncate username to 255 characters to prevent database errors
                truncated_username = str(username_value).strip()[:255]
                
                raw_data_scraper = RawDataScraper(
                    username=truncated_username,
                    content=content_to_check,
                    url=str(url_value) if url_value else '',
                    platform=platform,
                    keyword=keyword,
                    scrape_date=scrape_date,
                    dataset_id=dataset.id,
                    dataset_name=dataset.name,
                    scraped_by=current_user.id,
                    # Engagement data
                    likes=likes,
                    retweets=retweets,
                    replies=replies,
                    comments=comments,
                    shares=shares,
                    views=views
                )
                db.session.add(raw_data_scraper)
                records_added += 1
                
                # Debug logging for all platforms
                if records_added <= 5:  # Log first 5 records
                    app.logger.info(f"Record {records_added} - Platform: {platform}, Username: {username_value}, Content length: {len(content_to_check)}, Likes: {likes}, Views: {views}")
            
            app.logger.info(f"Processing completed - Total scraped: {len(scraped_data)}, Records added: {records_added}, Skipped: {len(scraped_data) - records_added}")
            app.logger.info(f"About to commit {records_added} records to database")
            db.session.commit()
            app.logger.info(f"Successfully committed {records_added} records to database")
            
            # Update statistics
            update_statistics()
            
            # Clean up session and temporary file
            session.pop('scraping_data', None)
            temp_id = session.pop('scraping_temp_id', None)
            
            # Delete temporary file
            if temp_id:
                temp_file_path = os.path.join(tempfile.gettempdir(), f'waskita_scraping_{temp_id}.json')
                if os.path.exists(temp_file_path):
                    try:
                        os.remove(temp_file_path)
                    except Exception as e:
                        pass
            
            # Create consistent success message based on platform
            platform_name = {
                'twitter': 'Twitter',
                'tiktok': 'TikTok',
                'facebook': 'Facebook',
                'instagram': 'Instagram'
            }.get(platform.lower(), platform.title())
            
            success_msg = f'Berhasil menyimpan {records_added} data dari {platform_name}!'
            if run_id:
                success_msg += f' (Apify Run ID: {run_id})'
            
            # Log aktivitas scraping
            from utils import generate_activity_log
            generate_activity_log(
                action='scraping',
                description=f'Berhasil scraping {records_added} data dari {platform}',
                user_id=current_user.id,
                details={
                    'platform': platform,
                    'records_added': records_added,
                    'run_id': run_id,
                    'keyword': keyword
                },
                icon='fa-search',
                color='info'
            )
            
            return jsonify({
                'success': True,
                'message': success_msg,
                'dataset_id': dataset.id,
                'total_records': records_added
            })
            
        except Exception as e:
            db.session.rollback()
            import traceback
            error_details = traceback.format_exc()
            app.logger.error(f"Error in process_scraping_column_mapping: {str(e)}")
            app.logger.error(f"Full traceback: {error_details}")
            
            # More specific error messages
            if "update_statistics" in str(e):
                error_msg = "Error saat memperbarui statistik database"
            elif "database" in str(e).lower() or "sql" in str(e).lower():
                error_msg = "Error database saat menyimpan data"
            elif "json" in str(e).lower():
                error_msg = "Error parsing data JSON"
            else:
                error_msg = f"Error tidak terduga: {str(e)}"

            return jsonify({'success': False, 'message': error_msg}), 500
    
    @app.route('/scraping')
    @login_required
    @active_user_required
    def scraping_page():
        """Display scraping page - data loaded via AJAX"""
        return render_template('data/scraping.html')
    
    @app.route('/api/recent-uploads')
    @login_required
    @active_user_required
    def api_recent_uploads():
        """API endpoint for recent uploads with pagination"""
        try:
            # Get pagination parameters
            page = request.args.get('page', 1, type=int)
            limit = request.args.get('limit', 10, type=int)
            
            # Calculate offset
            offset = (page - 1) * limit
            
            # Get grouped upload sessions (group by filename and dataset)
            
            # Get total count of upload sessions for pagination
            total_sessions = db.session.query(
                RawData.original_filename,
                RawData.dataset_id
            ).filter(
                RawData.uploaded_by == current_user.id
            ).group_by(
                RawData.original_filename,
                RawData.dataset_id
            ).count()
            
            total_count = total_sessions
            
            # Query to group uploads by filename and upload time (not by minute)
            upload_sessions = db.session.query(
                RawData.original_filename.label('filename'),
                func.count(RawData.id).label('records_count'),
                func.min(RawData.created_at).label('first_upload'),
                func.max(RawData.created_at).label('last_upload'),
                RawData.uploaded_by,
                RawData.dataset_id
            ).filter(
                RawData.uploaded_by == current_user.id
            ).group_by(
                RawData.original_filename,
                RawData.uploaded_by,
                RawData.dataset_id
            ).order_by(
                desc('first_upload')
            ).offset(offset).limit(limit).all()
            
            uploads_data = []
            for session in upload_sessions:
                # Get status counts for this upload file
                status_counts = db.session.query(
                    RawData.status,
                    func.count(RawData.id).label('count')
                ).filter(
                    RawData.uploaded_by == current_user.id,
                    RawData.original_filename == session.filename,
                    RawData.dataset_id == session.dataset_id
                ).group_by(RawData.status).all()
                
                # Calculate status based on data processing state
                raw_count = 0
                cleaned_count = 0
                for status_row in status_counts:
                    if status_row.status == 'raw':
                        raw_count = status_row.count
                    elif status_row.status == 'cleaned':
                        cleaned_count = status_row.count
                
                # Check if data has been classified
                # Get raw data IDs from this upload file
                session_raw_ids = db.session.query(RawData.id).filter(
                    RawData.uploaded_by == current_user.id,
                    RawData.original_filename == session.filename,
                    RawData.dataset_id == session.dataset_id
                ).all()
                
                session_raw_ids_list = [row[0] for row in session_raw_ids]
                
                # Get clean upload IDs for these raw data
                clean_upload_ids = db.session.query(CleanDataUpload.id).filter(
                    CleanDataUpload.raw_data_id.in_(session_raw_ids_list)
                ).all()
                
                clean_upload_ids_list = [row[0] for row in clean_upload_ids]
                
                # Count classifications for clean data
                classified_count = 0
                if clean_upload_ids_list:
                    classified_count = db.session.query(func.count(ClassificationResult.id)).filter(
                        ClassificationResult.data_type == 'upload',
                        ClassificationResult.data_id.in_(clean_upload_ids_list)
                    ).scalar() or 0
                
                # Get first raw data ID from this upload file for actions
                first_raw_data = RawData.query.filter(
                    RawData.uploaded_by == current_user.id,
                    RawData.original_filename == session.filename,
                    RawData.dataset_id == session.dataset_id
                ).first()
                
                # Use stored status from database instead of calculating dynamically
                # Get dataset status if available
                status = 'Mentah'  # Default status
                if first_raw_data and first_raw_data.dataset_id:
                    dataset = Dataset.query.get(first_raw_data.dataset_id)
                    if dataset and dataset.status:
                        status = dataset.status
                
                # Get dataset name if available
                dataset_name = None
                if first_raw_data and first_raw_data.dataset_id:
                    dataset = Dataset.query.get(first_raw_data.dataset_id)
                    if dataset:
                        dataset_name = dataset.name
                
                uploads_data.append({
                    'id': first_raw_data.id if first_raw_data else None,
                    'filename': session.filename or 'data.csv',
                    'dataset_name': dataset_name,
                    'records_count': session.records_count,
                    'status': status,
                    'created_date': format_datetime(session.first_upload, 'date_only'),
                    'created_time': format_datetime(session.first_upload, 'time'),
                    'username': current_user.username
                })
            
            # Calculate pagination info
            total_pages = (total_count + limit - 1) // limit
            has_next = page < total_pages
            has_prev = page > 1
            
            return jsonify({
                'success': True,
                'data': uploads_data,
                'pagination': {
                    'page': page,
                    'limit': limit,
                    'total': total_count,
                    'total_pages': total_pages,
                    'has_next': has_next,
                    'has_prev': has_prev
                }
            })
        except Exception as e:
            app.logger.error(f"Error in api_recent_uploads: {str(e)}")
            app.logger.error(f"Exception type: {type(e).__name__}")
            import traceback
            app.logger.error(f"Traceback: {traceback.format_exc()}")
            return jsonify({'success': False, 'message': str(e)}), 500
    
    @app.route('/api/upload-statistics')
    @login_required
    @active_user_required
    def api_upload_statistics():
        """API endpoint for upload statistics"""
        try:
            from datetime import datetime, date
            
            # Total uploads by user
            total_uploads = RawData.query.filter_by(uploaded_by=current_user.id).count()
            
            # Total records by user
            total_records = total_uploads  # Each RawData entry is one record
            
            # Today's uploads
            today = date.today()
            today_uploads = RawData.query.filter(
                RawData.uploaded_by == current_user.id,
                db.func.date(RawData.created_at) == today
            ).count()
            
            # Average file size calculation
            avg_file_size_result = db.session.query(func.avg(RawData.file_size)).filter(
                RawData.uploaded_by == current_user.id,
                RawData.file_size.isnot(None)
            ).scalar()
            
            if avg_file_size_result:
                # Convert bytes to MB and format
                avg_file_size_mb = avg_file_size_result / (1024 * 1024)
                avg_file_size = f"{avg_file_size_mb:.2f} MB"
            else:
                avg_file_size = "N/A"
            
            return jsonify({
                'success': True,
                'data': {
                    'total': total_uploads,
                    'totalRecords': total_records,
                    'todayUploads': today_uploads,
                    'avgFileSize': avg_file_size
                }
            })
        except Exception as e:
            return jsonify({'success': False, 'message': str(e)}), 500
    
    @app.route('/start_scraping', methods=['POST'])
    @login_required
    @active_user_required
    def start_scraping():
        """Start scraping process"""
        try:
            data = request.get_json()
            
            # Debug logging
            app.logger.info(f"Received scraping request data: {data}")
            
            # Check if data is None
            if data is None:
                app.logger.error("No JSON data received")
                return jsonify({'success': False, 'message': 'No JSON data received'}), 400
            
            # Validate required fields
            required_fields = ['platform', 'keywords', 'start_date', 'end_date', 'max_results']
            missing_fields = []
            for field in required_fields:
                if not data.get(field):
                    missing_fields.append(field)
            
            if missing_fields:
                app.logger.error(f"Missing required fields: {missing_fields}")
                return jsonify({'success': False, 'message': f'Field(s) {missing_fields} wajib diisi'}), 400
            
            # Create new dataset automatically based on keyword
            dataset_name = f"Scraper Data {data['platform'].title()} - {data['keywords']}"
            
            dataset = Dataset(
                name=dataset_name,
                description=f"Data hasil scraping dari {data['platform']} dengan kata kunci '{data['keywords']}'",
                uploaded_by=current_user.id
            )
            db.session.add(dataset)
            db.session.flush()  # Get the ID
            db.session.commit()  # Commit to ensure dataset is saved
            
            # Use Apify API for scraping
            try:
                # Prepare Instagram specific parameters if platform is Instagram
                instagram_params = None
                if data['platform'].lower() == 'instagram':
                    instagram_params = {
                        'search_type': data.get('instagram_search_type', 'hashtag'),
                        'results_type': data.get('instagram_results_type', 'posts'),
                        'direct_url': data.get('instagram_direct_url', ''),
                        'results_limit': int(data.get('instagram_results_limit', data['max_results'])),
                        'search_limit': int(data.get('instagram_search_limit', 1)),
                        'add_parent_data': data.get('instagram_add_parent_data', 'false') == 'true',
                        'enhance_user_search': data.get('instagram_enhance_user_search', 'false') == 'true',
                        'is_user_reel_feed': data.get('instagram_is_user_reel_feed', 'false') == 'true',
                        'is_user_tagged_feed': data.get('instagram_is_user_tagged_feed', 'false') == 'true'
                    }
                
                scraped_data, run_id = scrape_with_apify(
                    platform=data['platform'],
                    keyword=data['keywords'],
                    date_from=data['start_date'],
                    date_to=data['end_date'],
                    max_results=int(data['max_results']),
                    instagram_params=instagram_params
                )
                
                # Store scraping info in temporary file to avoid large session cookies
                # Generate unique temp file ID
                temp_id = str(uuid.uuid4())
                temp_file_path = os.path.join(tempfile.gettempdir(), f'waskita_scraping_{temp_id}.json')
                
                # Save scraped data to temporary file
                temp_data = {
                    'scraped_data': scraped_data,
                    'run_id': run_id,
                    'platform': data['platform'],
                    'keywords': data['keywords'],
                    'start_date': data['start_date'],
                    'end_date': data['end_date'],
                    'dataset_id': dataset.id,
                    'dataset_name': dataset.name
                }
                
                from utils import DateTimeEncoder
                with open(temp_file_path, 'w', encoding='utf-8') as f:
                    json.dump(temp_data, f, ensure_ascii=False, indent=2, cls=DateTimeEncoder)
                
                # Store only temp file ID in session
                session['scraping_temp_id'] = temp_id
                
                # Get column names from scraped data
                columns = []
                if scraped_data:
                    columns = list(scraped_data[0].keys())
                
                # Return data for column mapping with run_id for progress tracking
                return jsonify({
                    'success': True,
                    'requires_mapping': True,
                    'message': f'Berhasil scraping {len(scraped_data)} data dari {data["platform"]}',
                    'total_records': len(scraped_data),
                    'columns': columns,
                    'sample_data': scraped_data[:5] if scraped_data else [],  # First 5 items for preview
                    'dataset_id': dataset.id,
                    'run_id': run_id,
                    'platform': data['platform'],
                    'keywords': data['keywords']
                })
                
            except Exception as e:
                db.session.rollback()
                return jsonify({
                     'success': False,
                     'message': f'Error saat scraping: {str(e)}'
                 }), 500
        
        except Exception as e:
            db.session.rollback()
            return jsonify({
                'success': False,
                'message': f'Error: {str(e)}'
            }), 500
    
    @app.route('/delete_upload/<int:upload_id>', methods=['DELETE'])
    @login_required
    @admin_required
    def delete_upload(upload_id):
        """Delete upload data completely from database"""
        try:
            # Get raw data to delete
            raw_data = RawData.query.get_or_404(upload_id)
            
            # Get clean upload data IDs for classification results
            clean_upload_data = CleanDataUpload.query.filter_by(raw_data_id=upload_id).all()
            clean_upload_ids = [cd.id for cd in clean_upload_data]
            
            # Delete classification results first
            if clean_upload_ids:
                ClassificationResult.query.filter(
                    ClassificationResult.data_type == 'upload',
                    ClassificationResult.data_id.in_(clean_upload_ids)
                ).delete(synchronize_session=False)
            
            # Delete clean upload data
            CleanDataUpload.query.filter_by(raw_data_id=upload_id).delete()
            
            # Delete raw upload data
            db.session.delete(raw_data)
            
            db.session.commit()
            update_statistics()
            
            # Log activity
            generate_activity_log(
                action='delete_upload_data',
                description=f'Menghapus data upload ID: {upload_id}',
                user_id=current_user.id,
                icon='fas fa-trash',
                color='danger'
            )
            
            return jsonify({'success': True, 'message': 'Data upload berhasil dihapus dari database'})
        except Exception as e:
            db.session.rollback()
            return jsonify({'success': False, 'message': f'Error: {str(e)}'}), 500
    
    @app.route('/api/delete-upload/<int:upload_id>', methods=['DELETE'])
    @login_required
    @active_user_required
    def api_delete_upload(upload_id):
        """API endpoint to delete upload history (mark as deleted, don't actually delete data)"""
        try:
            # Get the raw data to check ownership
            raw_data = RawData.query.get_or_404(upload_id)
            
            # Check permission dengan feedback yang jelas
            has_permission, message, http_status = check_permission_with_feedback(
                current_user, raw_data.uploaded_by, 'delete', 'raw data'
            )
            if not has_permission:
                return jsonify({'success': False, 'message': message}), http_status
            
            # Get all related data in the same upload session (same minute)
            session_start = raw_data.created_at.replace(second=0, microsecond=0)
            session_end = session_start.replace(second=59, microsecond=999999)
            
            # Get all raw data IDs in this session
            session_raw_data = RawData.query.filter(
                RawData.uploaded_by == raw_data.uploaded_by,
                RawData.created_at >= session_start,
                RawData.created_at <= session_end
            ).all()
            
            session_ids = [rd.id for rd in session_raw_data]
            
            # Delete classification results first
            clean_data_items = CleanDataUpload.query.filter(CleanDataUpload.raw_data_id.in_(session_ids)).all()
            clean_data_ids = [cd.id for cd in clean_data_items]
            if clean_data_ids:
                ClassificationResult.query.filter(
                    ClassificationResult.data_type == 'upload',
                    ClassificationResult.data_id.in_(clean_data_ids)
                ).delete(synchronize_session=False)
            
            # Delete clean data
            CleanDataUpload.query.filter(CleanDataUpload.raw_data_id.in_(session_ids)).delete(synchronize_session=False)
            
            # Delete raw data
            RawData.query.filter(RawData.id.in_(session_ids)).delete(synchronize_session=False)
            
            db.session.commit()
            update_statistics()
            
            # Log activity
            generate_activity_log(
                action='delete_upload_history',
                description=f'Menghapus riwayat upload ({len(session_ids)} records)',
                user_id=current_user.id,
                icon='fas fa-history',
                color='warning'
            )
            
            return jsonify({'success': True, 'message': f'Riwayat upload berhasil dihapus dari tampilan ({len(session_ids)} records)'})
        except Exception as e:
            db.session.rollback()
            return jsonify({'success': False, 'message': f'Error: {str(e)}'}), 500
    
    @app.route('/api/classify_manual_text', methods=['POST'])
    @login_required
    @active_user_required
    def classify_manual_text():
        """Classify manual text input with all 3 models"""
        try:
            # Get and sanitize text from request
            if request.is_json:
                raw_text = request.json.get('text', '').strip()
            else:
                raw_text = request.form.get('text', '').strip()
            
            # Sanitize input text
            text = SecurityValidator.sanitize_input(raw_text, max_length=5000)
            
            if not text:
                log_security_event(
                    "TEXT_CLASSIFICATION_INVALID", 
                    "Text classification attempt with empty text",
                    user_id=current_user.id,
                    ip_address=request.remote_addr
                )
                return jsonify({'success': False, 'message': 'Teks tidak boleh kosong'}), 400
            
            # Log classification attempt
            log_security_event(
                "TEXT_CLASSIFICATION_ATTEMPT", 
                f"Manual text classification attempt - text length: {len(text)}",
                user_id=current_user.id,
                ip_address=request.remote_addr
            )
            
            # Clean the text
            cleaned_text = clean_text(text)
            
            if not cleaned_text:
                return jsonify({'success': False, 'message': 'Teks tidak valid setelah dibersihkan'}), 400
            
            # Get models from app config
            word2vec_model = current_app.config.get('WORD2VEC_MODEL')
            naive_bayes_models = current_app.config.get('NAIVE_BAYES_MODELS', {})
            
            # Vectorize text
            text_vector = vectorize_text(cleaned_text, word2vec_model)
            
            # Classify with all 3 models
            results = []
            for model_name, model in naive_bayes_models.items():
                if model is not None:
                    try:
                        prediction, probabilities = classify_content(text_vector, model)
                        
                        results.append({
                            'model': model_name,
                            'prediction': prediction,
                            'probability_radikal': float(probabilities[1]) if len(probabilities) > 1 else 0.0,
                            'probability_non_radikal': float(probabilities[0]) if len(probabilities) > 0 else 0.0
                        })
                    except Exception as model_error:
                        results.append({
                            'model': model_name,
                            'prediction': 'Error',
                            'probability_radikal': 0.0,
                            'probability_non_radikal': 0.0,
                            'error': str(model_error)
                        })
            
            if not results:
                return jsonify({'success': False, 'message': 'Tidak ada model yang tersedia'}), 500
            
            return jsonify({
                'success': True,
                'text': text,
                'cleaned_text': cleaned_text,
                'results': results
            })
            
        except Exception as e:
            return jsonify({'success': False, 'message': f'Error: {str(e)}'}), 500
    
    # Bulk Operations Routes
    @app.route('/dataset/bulk/clean', methods=['POST'])
    @login_required
    @active_user_required
    def bulk_clean_datasets():
        """Clean multiple datasets"""
        try:
            data = request.get_json()
            dataset_ids = data.get('dataset_ids', [])
            
            if not dataset_ids:
                return jsonify({'success': False, 'message': 'Tidak ada dataset yang dipilih'}), 400
            
            processed_count = 0
            already_cleaned_count = 0
            errors = []
            
            for dataset_id in dataset_ids:
                try:
                    dataset = Dataset.query.get(dataset_id)
                    if not dataset:
                        errors.append(f'Dataset ID {dataset_id} tidak ditemukan')
                        continue
                    
                    # Check permission dengan feedback yang jelas
                    has_permission, message, http_status = check_permission_with_feedback(
                        current_user, dataset.uploaded_by, 'clean', 'dataset'
                    )
                    if not has_permission:
                        errors.append(message)
                        continue
                    
                    # Check if classification is currently in progress for this dataset
                    # Note: Progress tracking has been removed, classification runs synchronously
                    
                    # Check if dataset already has clean data
                    has_clean_upload = db.session.query(CleanDataUpload).join(
                        RawData, CleanDataUpload.raw_data_id == RawData.id
                    ).filter(RawData.dataset_id == dataset_id).first()
                    
                    has_clean_scraper = db.session.query(CleanDataScraper).join(
                        RawDataScraper, CleanDataScraper.raw_data_scraper_id == RawDataScraper.id
                    ).filter(RawDataScraper.dataset_id == dataset_id).first()
                    
                    if has_clean_upload or has_clean_scraper:
                        already_cleaned_count += 1
                        continue
                    
                    # Clean raw upload data
                    raw_uploads = RawData.query.filter_by(dataset_id=dataset_id).all()
                    for raw_data in raw_uploads:
                        if not CleanDataUpload.query.filter_by(raw_data_id=raw_data.id).first():
                            cleaned_content = clean_text(raw_data.content)
                            
                            # Check for duplicate content within the same dataset
                            is_duplicate = check_cleaned_content_duplicate_by_dataset(cleaned_content, raw_scraper.dataset_id)
                            
                            if not is_duplicate:
                                clean_data = CleanDataUpload(
                                    raw_data_id=raw_data.id,
                                    username=raw_data.username,
                                    content=raw_data.content,
                                    cleaned_content=cleaned_content,
                                    url=raw_data.url,
                                    platform=raw_data.platform,
                                    cleaned_by=current_user.id
                                )
                                db.session.add(clean_data)
                            
                            # Update raw data status regardless of duplication
                            raw_data.status = 'cleaned'
                    
                    # Clean raw scraper data
                    raw_scrapers = RawDataScraper.query.filter_by(dataset_id=dataset_id).all()
                    for raw_scraper in raw_scrapers:
                        if not CleanDataScraper.query.filter_by(raw_data_scraper_id=raw_scraper.id).first():
                            cleaned_content = clean_text(raw_scraper.content)
                            
                            # Check for duplicate content within the same dataset
                            is_duplicate = check_cleaned_content_duplicate_by_dataset(cleaned_content, raw_scraper.dataset_id)
                            
                            if not is_duplicate:
                                clean_scraper = CleanDataScraper(
                                    raw_data_scraper_id=raw_scraper.id,
                                    username=raw_scraper.username,
                                    content=raw_scraper.content,
                                    cleaned_content=cleaned_content,
                                    url=raw_scraper.url,
                                    platform=raw_scraper.platform,
                                    keyword=raw_scraper.keyword,
                                    dataset_id=raw_scraper.dataset_id,
                                    cleaned_by=current_user.id
                                )
                                db.session.add(clean_scraper)
                            
                            # Update raw data status regardless of duplication
                            raw_scraper.status = 'cleaned'
                    
                    processed_count += 1
                    
                except Exception as e:
                    errors.append(f'Error pada dataset {dataset_id}: {str(e)}')
                    continue
            
            db.session.commit()
            
            # Update statistics after successful deletions
            if processed_count > 0:
                update_statistics()
            
            # Build informative message
            message_parts = []
            if processed_count > 0:
                message_parts.append(f'{processed_count} dataset berhasil dibersihkan')
            if already_cleaned_count > 0:
                message_parts.append(f'{already_cleaned_count} dataset sudah dalam status bersih')
            
            message = ' dan '.join(message_parts) if message_parts else 'Tidak ada dataset yang perlu dibersihkan'
            
            if errors:
                status_code = 400 if processed_count == 0 else 200
                return jsonify({
                    'success': processed_count > 0,
                    'processed': processed_count,
                    'already_cleaned': already_cleaned_count,
                    'message': message,
                    'errors': errors
                }), status_code
            
            return jsonify({
                'success': True, 
                'processed': processed_count,
                'already_cleaned': already_cleaned_count,
                'message': message
            })
            
        except Exception as e:
            db.session.rollback()
            return jsonify({'success': False, 'message': f'Error: {str(e)}'}), 500
    
    # Bulk classification route intentionally removed: gunakan klasifikasi per-dataset
            if not SKLEARN_AVAILABLE or not GENSIM_AVAILABLE:
                return jsonify({'success': False, 'message': 'Library ML tidak tersedia'}), 500
            
            processed_count = 0
            already_classified_count = 0
            no_clean_data_count = 0
            errors = []
            
            for dataset_id in dataset_ids:
                try:
                    dataset = Dataset.query.get(dataset_id)
                    if not dataset:
                        errors.append(f'Dataset ID {dataset_id} tidak ditemukan')
                        continue
                    
                    # Check permission dengan feedback yang jelas
                    has_permission, message, http_status = check_permission_with_feedback(
                        current_user, dataset.uploaded_by, 'classify', 'dataset'
                    )
                    if not has_permission:
                        errors.append(message)
                        continue
                    
                    # Check if dataset has clean data
                    clean_uploads_count = db.session.query(CleanDataUpload).join(
                        RawData, CleanDataUpload.raw_data_id == RawData.id
                    ).filter(RawData.dataset_id == dataset_id).count()
                    
                    clean_scrapers_count = db.session.query(CleanDataScraper).join(
                        RawDataScraper, CleanDataScraper.raw_data_scraper_id == RawDataScraper.id
                    ).filter(RawDataScraper.dataset_id == dataset_id).count()
                    
                    total_clean_data = clean_uploads_count + clean_scrapers_count
                    
                    if total_clean_data == 0:
                        no_clean_data_count += 1
                        errors.append(f'Dataset {dataset.name} tidak memiliki data bersih. Silakan bersihkan data terlebih dahulu.')
                        continue
                    
                    # Check if dataset already has classification results
                    classified_uploads_count = db.session.query(ClassificationResult).join(
                        CleanDataUpload, ClassificationResult.data_id == CleanDataUpload.id
                    ).join(RawData, CleanDataUpload.raw_data_id == RawData.id
                    ).filter(RawData.dataset_id == dataset_id).count()
                    
                    classified_scrapers_count = db.session.query(ClassificationResult).join(
                        CleanDataScraper, ClassificationResult.data_id == CleanDataScraper.id
                    ).join(RawDataScraper, CleanDataScraper.raw_data_scraper_id == RawDataScraper.id
                    ).filter(RawDataScraper.dataset_id == dataset_id).count()
                    
                    total_classified = classified_uploads_count + classified_scrapers_count
                    
                    if total_classified >= total_clean_data:
                        already_classified_count += 1
                        continue
                    
                    # Classify clean upload data
                    clean_uploads = db.session.query(CleanDataUpload).join(
                        RawData, CleanDataUpload.raw_data_id == RawData.id
                    ).filter(RawData.dataset_id == dataset_id).all()
                    
                    for clean_data in clean_uploads:
                        if not ClassificationResult.query.filter_by(
                            data_type='upload', data_id=clean_data.id
                        ).first():
                            prediction, probability = classify_content(
                                clean_data.cleaned_content, word2vec_model, naive_bayes_models
                            )
                            
                            classification = ClassificationResult(
                                data_type='upload',
                                data_id=clean_data.id,
                                prediction=prediction,
                                probability=probability,
                                classified_at=datetime.now(),
                                classified_by=current_user.id
                            )
                            db.session.add(classification)
                            
                            # Update RawData status
                            raw_upload = RawData.query.get(clean_data.raw_data_id)
                            if raw_upload:
                                raw_upload.status = 'classified'
                    
                    # Classify clean scraper data
                    clean_scrapers = db.session.query(CleanDataScraper).join(
                        RawDataScraper, CleanDataScraper.raw_data_scraper_id == RawDataScraper.id
                    ).filter(RawDataScraper.dataset_id == dataset_id).all()
                    
                    for clean_scraper in clean_scrapers:
                        if not ClassificationResult.query.filter_by(
                            data_type='scraper', data_id=clean_scraper.id
                        ).first():
                            prediction, probability = classify_content(
                                clean_scraper.cleaned_content, word2vec_model, naive_bayes_models
                            )
                            
                            classification = ClassificationResult(
                                data_type='scraper',
                                data_id=clean_scraper.id,
                                prediction=prediction,
                                probability=probability,
                                classified_at=datetime.now(),
                                classified_by=current_user.id
                            )
                            db.session.add(classification)
                            
                            # Update RawDataScraper status
                            raw_scraper = RawDataScraper.query.get(clean_scraper.raw_data_scraper_id)
                            if raw_scraper:
                                raw_scraper.status = 'classified'
                    
                    processed_count += 1
                    
                except Exception as e:
                    errors.append(f'Error pada dataset {dataset_id}: {str(e)}')
                    continue
            
            db.session.commit()
            
            # Update statistics after classification
            update_statistics()
            
            # Build informative message
            message_parts = []
            if processed_count > 0:
                message_parts.append(f'{processed_count} dataset berhasil diklasifikasi')
            if already_classified_count > 0:
                message_parts.append(f'{already_classified_count} dataset sudah dalam status terklasifikasi')
            if no_clean_data_count > 0:
                message_parts.append(f'{no_clean_data_count} dataset tidak memiliki data bersih')
            
            message = ' dan '.join(message_parts) if message_parts else 'Tidak ada dataset yang perlu diklasifikasi'
            
            if errors:
                return jsonify({
                    'success': True, 
                    'processed': processed_count,
                    'already_classified': already_classified_count,
                    'no_clean_data': no_clean_data_count,
                    'message': message,
                    'errors': errors
                })
            
            return jsonify({
                'success': True, 
                'processed': processed_count,
                'already_classified': already_classified_count,
                'no_clean_data': no_clean_data_count,
                'message': message
            })
            
        except Exception as e:
            db.session.rollback()
            return jsonify({'success': False, 'message': f'Error: {str(e)}'}), 500
    
    @app.route('/dataset/bulk/delete', methods=['POST'])
    @login_required
    @active_user_required
    def bulk_delete_datasets():
        """Delete multiple datasets"""
        try:
            data = request.get_json()
            dataset_ids = data.get('dataset_ids', [])
            
            if not dataset_ids:
                return jsonify({'success': False, 'message': 'Tidak ada dataset yang dipilih'}), 400
            
            processed_count = 0
            errors = []
            
            for dataset_id in dataset_ids:
                try:
                    dataset = Dataset.query.get(dataset_id)
                    if not dataset:
                        errors.append(f'Dataset ID {dataset_id} tidak ditemukan')
                        continue
                    
                    # Check permission dengan feedback yang jelas
                    has_permission, message, http_status = check_permission_with_feedback(
                        current_user, dataset.uploaded_by, 'delete', 'dataset'
                    )
                    if not has_permission:
                        errors.append(message)
                        continue
                    
                    # Delete all related data
                    # Delete classification results
                    db.session.execute(text("""
                        DELETE FROM classification_results 
                        WHERE (data_type = 'upload' AND data_id IN (
                            SELECT cdu.id FROM clean_data_upload cdu 
                            JOIN raw_data rd ON cdu.raw_data_id = rd.id 
                            WHERE rd.dataset_id = :dataset_id
                        )) OR (data_type = 'scraper' AND data_id IN (
                            SELECT cds.id FROM clean_data_scraper cds 
                            JOIN raw_data_scraper rds ON cds.raw_data_scraper_id = rds.id 
                            WHERE rds.dataset_id = :dataset_id
                        ))
                    """), {'dataset_id': dataset_id})
                    
                    # Delete clean data
                    db.session.execute(text("""
                        DELETE FROM clean_data_upload 
                        WHERE raw_data_id IN (
                            SELECT id FROM raw_data WHERE dataset_id = :dataset_id
                        )
                    """), {'dataset_id': dataset_id})
                    
                    db.session.execute(text("""
                        DELETE FROM clean_data_scraper 
                        WHERE raw_data_scraper_id IN (
                            SELECT id FROM raw_data_scraper WHERE dataset_id = :dataset_id
                        )
                    """), {'dataset_id': dataset_id})
                    
                    # Delete raw data
                    RawData.query.filter_by(dataset_id=dataset_id).delete()
                    RawDataScraper.query.filter_by(dataset_id=dataset_id).delete()
                    
                    # Dataset statistics will be updated after all deletions
                    
                    # Delete dataset
                    db.session.delete(dataset)
                    
                    processed_count += 1
                    
                except Exception as e:
                    errors.append(f'Error pada dataset {dataset_id}: {str(e)}')
                    continue
            
            db.session.commit()
            
            # Update statistics after deletion
            update_statistics()
            
            # Log activity
            generate_activity_log(
                action='bulk_delete_datasets',
                description=f'Menghapus {processed_count} dataset secara bulk',
                user_id=current_user.id,
                icon='fas fa-trash-alt',
                color='danger'
            )
            
            if errors:
                status_code = 400 if processed_count == 0 else 200
                return jsonify({
                    'success': processed_count > 0,
                    'processed': processed_count,
                    'message': f'{processed_count} dataset berhasil dihapus',
                    'errors': errors
                }), status_code
            
            return jsonify({
                'success': True, 
                'processed': processed_count,
                'message': f'{processed_count} dataset berhasil dihapus'
            })
            
        except Exception as e:
            db.session.rollback()
            return jsonify({'success': False, 'message': f'Error: {str(e)}'}), 500
    
    @app.route('/api/clean/all-raw-data', methods=['POST'])
    @login_required
    @active_user_required
    def clean_all_raw_data():
        """Clean all raw data (upload and scraper) at once"""
        try:
            # Get all raw upload data with status 'raw' dengan filter role-based
            if current_user.is_admin():
                # Admin dapat melihat semua data
                raw_uploads = RawData.query.filter_by(status='raw').all()
                raw_scrapers = RawDataScraper.query.filter_by(status='raw').all()
                
                # Also check for data that might need re-cleaning (status != 'cleaned')
                uncleaned_uploads = RawData.query.filter(RawData.status != 'cleaned').all()
                uncleaned_scrapers = RawDataScraper.query.filter(RawDataScraper.status != 'cleaned').all()
            else:
                # Regular user hanya dapat melihat data mereka sendiri
                raw_uploads = RawData.query.filter_by(status='raw', uploaded_by=current_user.id).all()
                raw_scrapers = RawDataScraper.query.filter_by(status='raw', scraped_by=current_user.id).all()
                
                # Also check for data that might need re-cleaning (status != 'cleaned')
                uncleaned_uploads = RawData.query.filter(RawData.status != 'cleaned', uploaded_by=current_user.id).all()
                uncleaned_scrapers = RawDataScraper.query.filter(RawDataScraper.status != 'cleaned', scraped_by=current_user.id).all()
            
            # Combine raw and uncleaned data
            all_uploads = list(set(raw_uploads + uncleaned_uploads))
            all_scrapers = list(set(raw_scrapers + uncleaned_scrapers))
            
            total_data = len(all_uploads) + len(all_scrapers)
            
            if total_data == 0:
                # Check if there's any data at all
                total_raw_data = RawData.query.count() + RawDataScraper.query.count()
                if total_raw_data == 0:
                    return jsonify({
                        'success': False, 
                        'message': 'Tidak ada data yang tersedia untuk dibersihkan. Silakan upload atau scrape data terlebih dahulu.'
                    }), 400
                else:
                    return jsonify({
                        'success': False, 
                        'message': 'Semua data sudah dalam status bersih. Tidak ada data yang perlu dibersihkan.'
                    }), 400
            
            processed_upload = 0
            processed_scraper = 0
            errors = []
            
            # Batch processing configuration
            BATCH_SIZE = 50  # Process 50 records at a time
            
            # Process upload data in batches
            for i in range(0, len(all_uploads), BATCH_SIZE):
                batch_uploads = all_uploads[i:i + BATCH_SIZE]
                
                for raw_data in batch_uploads:
                    try:
                        # Check if already cleaned
                        if CleanDataUpload.query.filter_by(raw_data_id=raw_data.id).first():
                            continue
                        
                        # Clean the content
                        cleaned_content = clean_text(raw_data.content)
                        
                        # Check for duplicate content
                        is_duplicate = check_cleaned_content_duplicate(cleaned_content)
                        
                        if not is_duplicate and cleaned_content:
                            clean_data = CleanDataUpload(
                                raw_data_id=raw_data.id,
                                username=raw_data.username,
                                content=raw_data.content,
                                cleaned_content=cleaned_content,
                                url=raw_data.url,
                                platform=raw_data.platform,
                                cleaned_by=current_user.id
                            )
                            db.session.add(clean_data)
                        
                        # Update raw data status regardless of duplication
                        raw_data.status = 'cleaned'
                        processed_upload += 1
                        
                    except Exception as e:
                        errors.append(f'Error pada upload data ID {raw_data.id}: {str(e)}')
                        continue
                
                # Commit batch to avoid timeout
                try:
                    db.session.commit()
                except Exception as e:
                    db.session.rollback()
                    errors.append(f'Error commit batch upload: {str(e)}')
            
            # Process scraper data in batches
            for i in range(0, len(all_scrapers), BATCH_SIZE):
                batch_scrapers = all_scrapers[i:i + BATCH_SIZE]
                
                for raw_scraper in batch_scrapers:
                    try:
                        # Check if already cleaned
                        if CleanDataScraper.query.filter_by(raw_data_scraper_id=raw_scraper.id).first():
                            continue
                        
                        # Clean the content
                        cleaned_content = clean_text(raw_scraper.content)
                        
                        # Check for duplicate content
                        is_duplicate = check_cleaned_content_duplicate(cleaned_content)
                        
                        if not is_duplicate and cleaned_content:
                            clean_scraper = CleanDataScraper(
                                raw_data_scraper_id=raw_scraper.id,
                                username=raw_scraper.username,
                                content=raw_scraper.content,
                                cleaned_content=cleaned_content,
                                url=raw_scraper.url,
                                platform=raw_scraper.platform,
                                keyword=raw_scraper.keyword,
                                dataset_id=raw_scraper.dataset_id,
                                cleaned_by=current_user.id
                            )
                            db.session.add(clean_scraper)
                        
                        # Update raw data status regardless of duplication
                        raw_scraper.status = 'cleaned'
                        processed_scraper += 1
                    
                    except Exception as e:
                        errors.append(f'Error pada scraper data ID {raw_scraper.id}: {str(e)}')
                        continue
                
                # Commit batch to avoid timeout
                try:
                    db.session.commit()
                except Exception as e:
                    db.session.rollback()
                    errors.append(f'Error commit batch scraper: {str(e)}')
            
            # Final commit for any remaining changes
            try:
                db.session.commit()
            except Exception as e:
                db.session.rollback()
                errors.append(f'Error final commit: {str(e)}')
            
            # Update statistics
            update_statistics()
            
            total_processed = processed_upload + processed_scraper
            message = f'{total_processed} data berhasil dibersihkan ({processed_upload} upload, {processed_scraper} scraper)'
            
            if errors:
                return jsonify({
                    'success': True,
                    'processed': total_processed,
                    'processed_upload': processed_upload,
                    'processed_scraper': processed_scraper,
                    'total_data': total_data,
                    'message': message,
                    'errors': errors,
                    'estimated_time': f'{total_processed * 0.1:.1f} detik',
                    'processing_rate': f'{total_processed / max(1, total_data) * 100:.1f}%'
                })
            
            return jsonify({
                'success': True,
                'processed': total_processed,
                'processed_upload': processed_upload,
                'processed_scraper': processed_scraper,
                'total_data': total_data,
                'message': message,
                'estimated_time': f'{total_processed * 0.1:.1f} detik',
                'processing_rate': f'{total_processed / max(1, total_data) * 100:.1f}%'
            })
            
        except Exception as e:
            db.session.rollback()
            return jsonify({'success': False, 'message': f'Error: {str(e)}'}), 500
    
    # Dataset detail page route
    @app.route('/dataset/<int:dataset_id>/details')
    @login_required
    def dataset_details(dataset_id):
        try:
            dataset = Dataset.query.get_or_404(dataset_id)
            
            # Check permission dengan feedback yang jelas
            has_permission, message, http_status = check_permission_with_feedback(
                current_user, dataset.uploaded_by, 'view', 'dataset'
            )
            if not has_permission:
                flash(message, 'error')
                return redirect(url_for('dataset_management_table'))
            
            # Get page parameters for each tab
            raw_page = request.args.get('raw_page', 1, type=int)
            clean_page = request.args.get('clean_page', 1, type=int)
            classified_page = request.args.get('classified_page', 1, type=int)
            per_page = 10  # Show 10 items per page
            
            # Get dataset statistics (both upload and scraper data) with role-based filtering
            if current_user.is_admin():
                raw_upload_data = RawData.query.filter_by(dataset_id=dataset_id).all()
                raw_scraper_data = RawDataScraper.query.filter_by(dataset_id=dataset_id).all()
            else:
                # For regular users, only show their own data
                raw_upload_data = RawData.query.filter_by(dataset_id=dataset_id, uploaded_by=current_user.id).all()
                raw_scraper_data = RawDataScraper.query.filter_by(dataset_id=dataset_id, scraped_by=current_user.id).all()
            
            # Get clean data from both sources using ORM
            clean_upload_data = db.session.query(CleanDataUpload).join(
                RawData, CleanDataUpload.raw_data_id == RawData.id
            ).filter(RawData.dataset_id == dataset_id).all()
            
            clean_scraper_data = db.session.query(CleanDataScraper).join(
                RawDataScraper, CleanDataScraper.raw_data_scraper_id == RawDataScraper.id
            ).filter(RawDataScraper.dataset_id == dataset_id).all()
            
            # Get classification results from both sources with content
            # Group by data_id to get all three models for each data entry
            classified_upload_data = []
            classified_scraper_data = []
            
            if clean_upload_data:
                # Get all classification results for upload data with role-based filtering
                if current_user.is_admin():
                    upload_results = db.session.execute(
                        text("SELECT cr.id, cr.data_type, cr.data_id, cr.model_name, cr.prediction, cr.probability_radikal, cr.probability_non_radikal, cr.classified_at, cdu.cleaned_content as content, cdu.username, cdu.url, cdu.created_at FROM classification_results cr JOIN clean_data_upload cdu ON cr.data_type = 'upload' AND cr.data_id = cdu.id JOIN raw_data rd ON cdu.raw_data_id = rd.id WHERE rd.dataset_id = :dataset_id ORDER BY cdu.id, cr.model_name"),
                        {'dataset_id': dataset_id}
                    ).mappings().fetchall()
                else:
                    # For regular users, only show their own data
                    upload_results = db.session.execute(
                        text("SELECT cr.id, cr.data_type, cr.data_id, cr.model_name, cr.prediction, cr.probability_radikal, cr.probability_non_radikal, cr.classified_at, cdu.cleaned_content as content, cdu.username, cdu.url, cdu.created_at FROM classification_results cr JOIN clean_data_upload cdu ON cr.data_type = 'upload' AND cr.data_id = cdu.id JOIN raw_data rd ON cdu.raw_data_id = rd.id WHERE rd.dataset_id = :dataset_id AND rd.uploaded_by = :user_id ORDER BY cdu.id, cr.model_name"),
                        {'dataset_id': dataset_id, 'user_id': current_user.id}
                    ).mappings().fetchall()
                
                # Group results by data_id
                upload_data_by_id = {}
                for result in upload_results:
                    data_id = result['data_id']
                    if data_id not in upload_data_by_id:
                        upload_data_by_id[data_id] = {
                            'id': result['id'],
                            'data_type': result['data_type'],
                            'data_id': data_id,
                            'content': result['content'],
                            'username': result['username'],
                            'url': result['url'],
                            'created_at': result['created_at'],
                            'models': {}
                        }
                    
                    # Store model results
                    upload_data_by_id[data_id]['models'][result['model_name']] = {
                        'prediction': result['prediction'],
                        'probability_radikal': result['probability_radikal'],
                        'probability_non_radikal': result['probability_non_radikal']
                    }
                
                classified_upload_data = list(upload_data_by_id.values())
            
            if clean_scraper_data:
                # Get all classification results for scraper data with role-based filtering
                if current_user.is_admin():
                    scraper_results = db.session.execute(
                        text("SELECT cr.id, cr.data_type, cr.data_id, cr.model_name, cr.prediction, cr.probability_radikal, cr.probability_non_radikal, cr.classified_at, cds.cleaned_content as content, cds.username, cds.url, cds.created_at FROM classification_results cr JOIN clean_data_scraper cds ON cr.data_type = 'scraper' AND cr.data_id = cds.id JOIN raw_data_scraper rds ON cds.raw_data_scraper_id = rds.id WHERE rds.dataset_id = :dataset_id ORDER BY cds.id, cr.model_name"),
                        {'dataset_id': dataset_id}
                    ).mappings().fetchall()
                else:
                    # For regular users, only show their own data
                    scraper_results = db.session.execute(
                        text("SELECT cr.id, cr.data_type, cr.data_id, cr.model_name, cr.prediction, cr.probability_radikal, cr.probability_non_radikal, cr.classified_at, cds.cleaned_content as content, cds.username, cds.url, cds.created_at FROM classification_results cr JOIN clean_data_scraper cds ON cr.data_type = 'scraper' AND cr.data_id = cds.id JOIN raw_data_scraper rds ON cds.raw_data_scraper_id = rds.id WHERE rds.dataset_id = :dataset_id AND rds.scraped_by = :user_id ORDER BY cds.id, cr.model_name"),
                        {'dataset_id': dataset_id, 'user_id': current_user.id}
                    ).mappings().fetchall()
                
                # Group results by data_id
                scraper_data_by_id = {}
                for result in scraper_results:
                    data_id = result['data_id']
                    if data_id not in scraper_data_by_id:
                        scraper_data_by_id[data_id] = {
                            'id': result['id'],
                            'data_type': result['data_type'],
                            'data_id': data_id,
                            'content': result['content'],
                            'username': result['username'],
                            'url': result['url'],
                            'created_at': result['created_at'],
                            'models': {}
                        }
                    
                    # Store model results
                    scraper_data_by_id[data_id]['models'][result['model_name']] = {
                        'prediction': result['prediction'],
                        'probability_radikal': result['probability_radikal'],
                        'probability_non_radikal': result['probability_non_radikal']
                    }
                
                classified_scraper_data = list(scraper_data_by_id.values())
            
            # Prepare paginated data for each tab with independent pagination
            # Raw data pagination - separate for upload and scraper
            raw_upload_paginated = raw_upload_data[(raw_page-1)*per_page:raw_page*per_page]
            raw_scraper_paginated = raw_scraper_data[(raw_page-1)*per_page:raw_page*per_page]
            raw_upload_total_pages = (len(raw_upload_data) + per_page - 1) // per_page
            raw_scraper_total_pages = (len(raw_scraper_data) + per_page - 1) // per_page
            raw_total_pages = max(raw_upload_total_pages, raw_scraper_total_pages)
            
            # Clean data pagination - separate for upload and scraper
            clean_upload_paginated = clean_upload_data[(clean_page-1)*per_page:clean_page*per_page]
            clean_scraper_paginated = clean_scraper_data[(clean_page-1)*per_page:clean_page*per_page]
            clean_upload_total_pages = (len(clean_upload_data) + per_page - 1) // per_page
            clean_scraper_total_pages = (len(clean_scraper_data) + per_page - 1) // per_page
            clean_total_pages = max(clean_upload_total_pages, clean_scraper_total_pages)
            
            # Classification results pagination - separate for upload and scraper
            classified_upload_paginated = classified_upload_data[(classified_page-1)*per_page:classified_page*per_page]
            classified_scraper_paginated = classified_scraper_data[(classified_page-1)*per_page:classified_page*per_page]
            classified_upload_total_pages = (len(classified_upload_data) + per_page - 1) // per_page
            classified_scraper_total_pages = (len(classified_scraper_data) + per_page - 1) // per_page
            classified_total_pages = max(classified_upload_total_pages, classified_scraper_total_pages)
            
            # Calculate total items for each type
            total_raw_items = len(raw_upload_data) + len(raw_scraper_data)
            total_clean_items = len(clean_upload_data) + len(clean_scraper_data)
            total_classified_items = len(classified_upload_data) + len(classified_scraper_data)
            
            return render_template('dataset/details.html', 
                                 dataset=dataset,
                                 raw_upload_data=raw_upload_paginated,
                                 raw_scraper_data=raw_scraper_paginated,
                                 clean_upload_data=clean_upload_paginated,
                                 clean_scraper_data=clean_scraper_paginated,
                                 classified_upload_data=classified_upload_paginated,
                                 classified_scraper_data=classified_scraper_paginated,
                                 raw_page=raw_page,
                                 clean_page=clean_page,
                                 classified_page=classified_page,
                                 per_page=per_page,
                                 raw_upload_total_pages=raw_upload_total_pages,
                                 raw_scraper_total_pages=raw_scraper_total_pages,
                                 clean_upload_total_pages=clean_upload_total_pages,
                                 clean_scraper_total_pages=clean_scraper_total_pages,
                                 classified_upload_total_pages=classified_upload_total_pages,
                                 classified_scraper_total_pages=classified_scraper_total_pages,
                                 raw_total_pages=raw_total_pages,
                                 clean_total_pages=clean_total_pages,
                                 classified_total_pages=classified_total_pages,
                                 total_raw_items=total_raw_items,
                                 total_clean_items=total_clean_items,
                                 total_classified_items=total_classified_items)
        except Exception as e:
            flash(f'Error loading dataset details: {str(e)}', 'error')
            return redirect(url_for('dataset_management_table'))
    
    # API Routes for dataset operations
    @app.route('/api/dataset/<int:dataset_id>/details')
    @login_required
    def api_dataset_details(dataset_id):
        try:
            dataset = Dataset.query.get_or_404(dataset_id)
            
            # Check permission dengan feedback yang jelas
            has_permission, message, http_status = check_permission_with_feedback(
                current_user, dataset.uploaded_by, 'view', 'dataset'
            )
            if not has_permission:
                return jsonify({'error': message}), http_status
            
            # Get dataset statistics (both upload and scraper data) with role-based filtering
            if current_user.is_admin():
                raw_upload_data = RawData.query.filter_by(dataset_id=dataset_id).all()
                raw_scraper_data = RawDataScraper.query.filter_by(dataset_id=dataset_id).all()
            else:
                # For regular users, only show their own data
                raw_upload_data = RawData.query.filter_by(dataset_id=dataset_id, uploaded_by=current_user.id).all()
                raw_scraper_data = RawDataScraper.query.filter_by(dataset_id=dataset_id, scraped_by=current_user.id).all()
            
            # Get clean data from both sources
            clean_upload_data = db.session.execute(
                text("SELECT cdu.* FROM clean_data_upload cdu JOIN raw_data rd ON cdu.raw_data_id = rd.id WHERE rd.dataset_id = :dataset_id"),
                {'dataset_id': dataset_id}
            ).fetchall()
            clean_scraper_data = db.session.execute(
                text("SELECT cds.* FROM clean_data_scraper cds JOIN raw_data_scraper rds ON cds.raw_data_scraper_id = rds.id WHERE rds.dataset_id = :dataset_id"),
                {'dataset_id': dataset_id}
            ).fetchall()
            
            # Get classification results from both sources
            classified_upload_data = []
            classified_scraper_data = []
            
            if clean_upload_data:
                if current_user.is_admin():
                    classified_upload_data = db.session.execute(
                        text("SELECT cr.* FROM classification_results cr JOIN clean_data_upload cdu ON cr.data_type = 'upload' AND cr.data_id = cdu.id JOIN raw_data rd ON cdu.raw_data_id = rd.id WHERE rd.dataset_id = :dataset_id"),
                        {'dataset_id': dataset_id}
                    ).mappings().fetchall()
                else:
                    # For regular users, only show their own data
                    classified_upload_data = db.session.execute(
                        text("SELECT cr.* FROM classification_results cr JOIN clean_data_upload cdu ON cr.data_type = 'upload' AND cr.data_id = cdu.id JOIN raw_data rd ON cdu.raw_data_id = rd.id WHERE rd.dataset_id = :dataset_id AND rd.uploaded_by = :user_id"),
                        {'dataset_id': dataset_id, 'user_id': current_user.id}
                    ).mappings().fetchall()
            
            if clean_scraper_data:
                if current_user.is_admin():
                    classified_scraper_data = db.session.execute(
                        text("SELECT cr.* FROM classification_results cr JOIN clean_data_scraper cds ON cr.data_type = 'scraper' AND cr.data_id = cds.id JOIN raw_data_scraper rds ON cds.raw_data_scraper_id = rds.id WHERE rds.dataset_id = :dataset_id"),
                        {'dataset_id': dataset_id}
                    ).mappings().fetchall()
                else:
                    # For regular users, only show their own data
                    classified_scraper_data = db.session.execute(
                        text("SELECT cr.* FROM classification_results cr JOIN clean_data_scraper cds ON cr.data_type = 'scraper' AND cr.data_id = cds.id JOIN raw_data_scraper rds ON cds.raw_data_scraper_id = rds.id WHERE rds.dataset_id = :dataset_id AND rds.scraped_by = :user_id"),
                        {'dataset_id': dataset_id, 'user_id': current_user.id}
                    ).mappings().fetchall()
            
            return render_template('dataset/detail_modal.html', 
                                 dataset=dataset,
                                 raw_upload_data=raw_upload_data,
                                 raw_scraper_data=raw_scraper_data,
                                 clean_upload_data=clean_upload_data,
                                 clean_scraper_data=clean_scraper_data,
                                 classified_upload_data=classified_upload_data,
                                 classified_scraper_data=classified_scraper_data)
        except Exception as e:
            return jsonify({'error': f'Internal server error: {str(e)}'}), 500
    
    @app.route('/api/classification/status/<int:dataset_id>', methods=['GET'])
    @login_required
    def api_classification_status(dataset_id):
        try:
            dataset = Dataset.query.get_or_404(dataset_id)
            
            # Check permission dengan feedback yang jelas
            has_permission, message, http_status = check_permission_with_feedback(
                current_user, dataset.uploaded_by, 'view', 'classification status'
            )
            if not has_permission:
                return jsonify({'success': False, 'error': message}), http_status
            
            # Return dataset status in JSON format
            return jsonify({
                'success': True,
                'dataset': {
                    'id': dataset.id,
                    'name': dataset.name,
                    'status': dataset.status,
                    'updated_at': dataset.updated_at.isoformat() if dataset.updated_at else None
                }
            })
            
        except Exception as e:
            return jsonify({'success': False, 'error': f'Internal server error: {str(e)}'}), 500

    @app.route('/api/dataset/<int:dataset_id>/clean', methods=['POST'])
    @login_required
    def api_dataset_clean(dataset_id):
        try:
            dataset = Dataset.query.get_or_404(dataset_id)
            
            # Check permission dengan feedback yang jelas
            has_permission, message, http_status = check_permission_with_feedback(
                current_user, dataset.uploaded_by, 'clean', 'dataset'
            )
            if not has_permission:
                return jsonify({'success': False, 'message': message}), http_status
            
            # Get all raw data for this dataset (both upload and scraper) with status 'raw'
            raw_upload_data = RawData.query.filter_by(dataset_id=dataset_id, status='raw').all()
            raw_scraper_data = RawDataScraper.query.filter_by(dataset_id=dataset_id, status='raw').all()
            
            # Check if all data is already cleaned
            all_upload_data = RawData.query.filter_by(dataset_id=dataset_id).all()
            all_scraper_data = RawDataScraper.query.filter_by(dataset_id=dataset_id).all()
            
            if not raw_upload_data and not raw_scraper_data:
                if all_upload_data or all_scraper_data:
                    # Data exists but all already cleaned
                    return jsonify({
                        'success': False, 
                        'message': 'Semua data sudah dibersihkan sebelumnya',
                        'already_cleaned': True
                    })
                else:
                    # No data at all
                    return jsonify({'success': False, 'message': 'Tidak ada data yang perlu dibersihkan'})
            
            cleaned_count = 0
            skipped_count = 0
            duplicate_removed = 0
            
            # Process upload data
            for raw_data in raw_upload_data:
                # Clean the content
                cleaned_content = clean_text(raw_data.content)
                
                # Check if already has clean data
                existing_clean = CleanDataUpload.query.filter_by(raw_data_id=raw_data.id).first()
                if existing_clean:
                    # Remove existing clean data to avoid duplicates
                    db.session.delete(existing_clean)
                    duplicate_removed += 1
                
                # Check for duplicate content in clean data tables across entire dataset
                is_duplicate = check_cleaned_content_duplicate_by_dataset(cleaned_content, dataset_id)
                
                if not is_duplicate:
                    # Create clean data record
                    clean_data = CleanDataUpload(
                        raw_data_id=raw_data.id,
                        platform=raw_data.platform,
                        username=raw_data.username,
                        content=raw_data.content,
                        cleaned_content=cleaned_content,
                        url=raw_data.url,
                        dataset_id=dataset_id,
                        cleaned_by=current_user.id
                    )
                    
                    db.session.add(clean_data)
                    cleaned_count += 1
                else:
                    skipped_count += 1
                
                # Update raw data status
                raw_data.status = 'cleaned'
            
            # Process scraper data
            for raw_scraper in raw_scraper_data:
                # Clean the content
                cleaned_content = clean_text(raw_scraper.content)
                
                # Check if already has clean data
                existing_clean = CleanDataScraper.query.filter_by(raw_data_scraper_id=raw_scraper.id).first()
                if existing_clean:
                    # Remove existing clean data to avoid duplicates
                    db.session.delete(existing_clean)
                    duplicate_removed += 1
                
                # Check for duplicate content in clean data tables across entire dataset
                is_duplicate = check_cleaned_content_duplicate_by_dataset(cleaned_content, dataset_id)
                
                if not is_duplicate:
                    # Create clean data record
                    clean_data = CleanDataScraper(
                        raw_data_scraper_id=raw_scraper.id,
                        platform=raw_scraper.platform,
                        username=raw_scraper.username,
                        content=raw_scraper.content,
                        cleaned_content=cleaned_content,
                        url=raw_scraper.url,
                        keyword=raw_scraper.keyword,
                        dataset_id=dataset_id,
                        cleaned_by=current_user.id
                    )
                    
                    db.session.add(clean_data)
                    cleaned_count += 1
                else:
                    skipped_count += 1
                
                # Update raw scraper status
                raw_scraper.status = 'cleaned'
            
            # Update dataset statistics
            dataset.updated_at = datetime.utcnow()
            
            db.session.commit()
            
            # Update global statistics
            update_statistics()
            
            # Prepare response message
            message = f'{cleaned_count} data berhasil dibersihkan'
            if skipped_count > 0:
                message += f', {skipped_count} data dilewati karena duplikasi konten'
            if duplicate_removed > 0:
                message += f', {duplicate_removed} data duplikat dihapus'
            
            return jsonify({
                'success': True, 
                'message': message,
                'cleaned_count': cleaned_count,
                'skipped_count': skipped_count,
                'duplicate_removed': duplicate_removed
            })
            
        except Exception as e:
            db.session.rollback()
            
            # Enhanced error logging
            import traceback
            import logging
            
            error_msg = f"Dataset clean API error for dataset_id {dataset_id}: {str(e)}"
            logging.error(error_msg)
            logging.error(f"Traceback: {traceback.format_exc()}")
            
            return jsonify({'success': False, 'message': str(e)}), 500
    
    @app.route('/api/dataset/<int:dataset_id>/classify', methods=['POST'])
    @login_required
    def api_dataset_classify(dataset_id):
        import traceback
        try:
            dataset = Dataset.query.get_or_404(dataset_id)
            
            # Check permission dengan feedback yang jelas
            has_permission, message, http_status = check_permission_with_feedback(
                current_user, dataset.uploaded_by, 'classify', 'dataset'
            )
            if not has_permission:
                return jsonify({'success': False, 'message': message}), http_status
            
            # Get all clean data for this dataset that hasn't been classified
            clean_upload_list = CleanDataUpload.query.filter_by(dataset_id=dataset_id).all()
            
            # Get clean scraper data for this dataset
            clean_scraper_list = db.session.query(CleanDataScraper).join(
                RawDataScraper, CleanDataScraper.raw_data_scraper_id == RawDataScraper.id
            ).filter(RawDataScraper.dataset_id == dataset_id).all()
            
            if not clean_upload_list and not clean_scraper_list:
                return jsonify({'success': False, 'message': 'Tidak ada data bersih untuk diklasifikasi'})
            
            classified_count = 0
            
            # Process upload data
            for clean_data in clean_upload_list:
                # Check if already classified (check all models first)
                result = db.session.execute(text("SELECT COUNT(*) as count FROM classification_results WHERE data_type = :data_type AND data_id = :data_id"), {'data_type': 'upload', 'data_id': clean_data.id})
                existing_count = result.fetchone()[0]
                if existing_count >= 3:  # Already classified with all 3 models
                    continue
                    
                # Get models from app config
                word2vec_model = current_app.config.get('WORD2VEC_MODEL')
                naive_bayes_models = current_app.config.get('NAIVE_BAYES_MODELS', {})
                
                # Vectorize text first
                text_vector = vectorize_text(clean_data.cleaned_content, word2vec_model)
                
                if text_vector is not None:
                    # Perform classification with all three models
                    for model_name, model in naive_bayes_models.items():
                        if model:
                            prediction, probabilities = classify_content(text_vector, model)
                            
                            # Create classification result
                            # Handle probabilities consistently
                            if isinstance(probabilities, (list, tuple, np.ndarray)) and len(probabilities) >= 2:
                                prob_non_radikal = float(probabilities[0])
                                prob_radikal = float(probabilities[1])
                            else:
                                prob_non_radikal = 0.0
                                prob_radikal = 0.0
                            
                            classification_result = ClassificationResult(
                                data_type='upload',
                                data_id=clean_data.id,
                                model_name=model_name,
                                prediction=prediction,
                                probability_radikal=prob_radikal,
                                probability_non_radikal=prob_non_radikal,
                                classified_by=current_user.id
                            )
                            
                            db.session.add(classification_result)
                    
                    # Update RawData status
                    raw_upload = RawData.query.get(clean_data.raw_data_id)
                    if raw_upload:
                        raw_upload.status = 'classified'
                    
                    classified_count += 1
                else:
                    pass
            
            # Process scraper data
            for clean_scraper in clean_scraper_list:
                # Check if already classified (check all models first)
                result = db.session.execute(text("SELECT COUNT(*) as count FROM classification_results WHERE data_type = :data_type AND data_id = :data_id"), {'data_type': 'scraper', 'data_id': clean_scraper.id})
                existing_count = result.fetchone()[0]
                if existing_count >= 3:  # Already classified with all 3 models
                    continue
                    
                # Get models from app config
                word2vec_model = current_app.config.get('WORD2VEC_MODEL')
                naive_bayes_models = current_app.config.get('NAIVE_BAYES_MODELS', {})
                
                # Vectorize text first
                text_vector = vectorize_text(clean_scraper.cleaned_content, word2vec_model)
                
                if text_vector is not None:
                    # Perform classification with all three models
                    for model_name, model in naive_bayes_models.items():
                        if model:
                            prediction, probabilities = classify_content(text_vector, model)
                            
                            # Create classification result
                            # Handle probabilities consistently
                            if isinstance(probabilities, (list, tuple, np.ndarray)) and len(probabilities) >= 2:
                                prob_non_radikal = float(probabilities[0])
                                prob_radikal = float(probabilities[1])
                            else:
                                prob_non_radikal = 0.0
                                prob_radikal = 0.0
                            
                            classification_result = ClassificationResult(
                                data_type='scraper',
                                data_id=clean_scraper.id,
                                model_name=model_name,
                                prediction=prediction,
                                probability_radikal=prob_radikal,
                                probability_non_radikal=prob_non_radikal,
                                classified_by=current_user.id
                            )
                            
                            db.session.add(classification_result)
                    
                    # Update RawDataScraper status
                    raw_scraper = RawDataScraper.query.get(clean_scraper.raw_data_scraper_id)
                    if raw_scraper:
                        raw_scraper.status = 'classified'
                    
                    classified_count += 1
                else:
                    pass
            
            # Update dataset statistics
            dataset.updated_at = datetime.utcnow()
            
            db.session.commit()
            
            # Update global statistics after successful classification
            update_statistics()
            
            return jsonify({
                'success': True, 
                'message': f'{classified_count} data berhasil diklasifikasi',
                'classified_count': classified_count
            })
            
        except Exception as e:
            db.session.rollback()
            error_msg = f"Error in api_dataset_classify: {str(e)}"
            pass
            return jsonify({'success': False, 'message': str(e)}), 500
    
    @app.route('/api/dataset/<int:dataset_id>', methods=['DELETE'])
    @login_required
    def api_dataset_delete(dataset_id):
        try:
            dataset = Dataset.query.get_or_404(dataset_id)
            
            # Check permission dengan feedback yang jelas
            has_permission, message, http_status = check_permission_with_feedback(
                current_user, dataset.uploaded_by, 'delete', 'dataset'
            )
            if not has_permission:
                return jsonify({'success': False, 'message': message}), http_status
            
            # Check if classification is currently in progress for this dataset
            # Note: Progress tracking has been removed, classification runs synchronously
            
            # Delete all related data
            # Delete classification results first (both upload and scraper)
            clean_data_ids = [cd.id for cd in CleanDataUpload.query.filter_by(dataset_id=dataset_id).all()]
            if clean_data_ids:
                ClassificationResult.query.filter(
                    ClassificationResult.data_type == 'upload',
                    ClassificationResult.data_id.in_(clean_data_ids)
                ).delete(synchronize_session=False)
            
            # Get raw scraper data IDs
            raw_scraper_ids = [sd.id for sd in RawDataScraper.query.filter_by(dataset_id=dataset_id).all()]
            
            # Get clean scraper data IDs for classification results
            clean_scraper_ids = []
            if raw_scraper_ids:
                clean_scraper_data = db.session.execute(
                    text("SELECT id FROM clean_data_scraper WHERE raw_data_scraper_id IN :ids"),
                    {'ids': tuple(raw_scraper_ids)}
                ).fetchall()
                clean_scraper_ids = [row[0] for row in clean_scraper_data]
            
            # Delete classification results for scraper data (using clean data IDs)
            if clean_scraper_ids:
                db.session.execute(
                    text("DELETE FROM classification_results WHERE data_type = 'scraper' AND data_id IN :ids"),
                    {'ids': tuple(clean_scraper_ids)}
                )
            
            # Delete clean scraper data (using raw data IDs)
            if raw_scraper_ids:
                db.session.execute(
                    text("DELETE FROM clean_data_scraper WHERE raw_data_scraper_id IN :ids"),
                    {'ids': tuple(raw_scraper_ids)}
                )
            
            # Delete clean upload data
            CleanDataUpload.query.filter_by(dataset_id=dataset_id).delete()
            
            # Delete raw data (both upload and scraper)
            RawData.query.filter_by(dataset_id=dataset_id).delete()
            RawDataScraper.query.filter_by(dataset_id=dataset_id).delete()
            
            # Delete dataset
            db.session.delete(dataset)
            
            db.session.commit()
            
            # Clean up classification progress data for this dataset
            # Note: Progress tracking has been removed, classification runs synchronously
            
            # Log activity
            generate_activity_log(
                action='delete_dataset',
                description=f'Menghapus dataset: {dataset.name}',
                user_id=current_user.id,
                icon='fas fa-trash-alt',
                color='danger'
            )
            
            # Update statistics after deletion
            update_statistics()
            
            return jsonify({
                'success': True, 
                'message': 'Dataset berhasil dihapus'
            })
            
        except Exception as e:
            db.session.rollback()
            return jsonify({'success': False, 'message': str(e)}), 500
    
    # API Endpoints untuk Scraping
    @app.route('/api/scraping/status/<int:job_id>')
    @login_required
    def get_scraping_status(job_id):
        """Get status of a specific scraping job"""
        try:
            scraping_job = RawDataScraper.query.filter_by(id=job_id).first()
            
            if not scraping_job:
                return jsonify({'error': 'Scraping job not found'}), 404
            
            # Check permission dengan feedback yang jelas
            has_permission, message, http_status = check_permission_with_feedback(
                current_user, scraping_job.scraped_by, 'view', 'scraping job'
            )
            if not has_permission:
                return jsonify({'error': message}), http_status
            
            # Count related data - count all records with same keyword/platform combination
            if current_user.is_admin():
                data_count = RawDataScraper.query.filter_by(
                    keyword=scraping_job.keyword,
                    platform=scraping_job.platform
                ).count()
            else:
                data_count = RawDataScraper.query.filter_by(
                    keyword=scraping_job.keyword,
                    platform=scraping_job.platform,
                    scraped_by=current_user.id
                ).count()
            
            status_data = {
                'job_id': job_id,
                'platform': scraping_job.platform,
                'keywords': scraping_job.keyword,
                'status': 'completed',  # For now, all jobs are completed since we use mock data
                'progress': 100,
                'total_found': data_count,
                'results_count': data_count,
                'created_at': format_datetime(scraping_job.created_at, 'default') if scraping_job.created_at else None,
                'completed_at': format_datetime(scraping_job.created_at, 'default') if scraping_job.created_at else None
            }
            
            return jsonify(status_data)
            
        except Exception as e:
            return jsonify({'error': f'Error getting scraping status: {str(e)}'}), 500
    
    @app.route('/api/scraping/progress/<run_id>')
    @login_required
    def get_scraping_progress(run_id):
        """Get real-time progress of Apify actor run"""
        try:
            from utils import get_apify_run_progress
            
            # Get progress information from Apify API
            progress_info = get_apify_run_progress(run_id)
            
            # Add user-friendly status messages
            status_messages = {
                'READY': 'Mempersiapkan scraping...',
                'RUNNING': 'Sedang melakukan scraping data...',
                'SUCCEEDED': 'Scraping berhasil diselesaikan!',
                'FAILED': 'Scraping gagal, silakan coba lagi.',
                'ABORTED': 'Scraping dibatalkan.',
                'TIMED-OUT': 'Scraping timeout, waktu habis.',
                'ERROR': 'Terjadi kesalahan saat mengecek progress.'
            }
            
            progress_info['status_message'] = status_messages.get(
                progress_info['status'], 
                'Status tidak diketahui'
            )
            
            # Format time remaining
            if progress_info.get('estimated_time_remaining'):
                remaining_seconds = int(progress_info['estimated_time_remaining'])
                if remaining_seconds > 60:
                    minutes = remaining_seconds // 60
                    seconds = remaining_seconds % 60
                    progress_info['time_remaining_formatted'] = f"{minutes}m {seconds}s"
                else:
                    progress_info['time_remaining_formatted'] = f"{remaining_seconds}s"
            
            return jsonify(progress_info)
            
        except Exception as e:
            return jsonify({
                'run_id': run_id,
                'status': 'ERROR',
                'progress_percentage': 0,
                'status_message': 'Terjadi kesalahan saat mengecek progress.',
                'error': str(e)
            }), 500
    
    @app.route('/api/scraping/statistics')
    @login_required
    def get_scraping_statistics():
        """Get overall scraping statistics"""
        try:
            # Base query - filter by user if not admin
            base_query = RawDataScraper.query
            if not current_user.is_admin():
                base_query = base_query.filter_by(scraped_by=current_user.id)
            
            # Total scraping jobs
            total_scraping = base_query.count()
            
            # Platform breakdown
            platform_stats = db.session.query(
                RawDataScraper.platform,
                func.count(RawDataScraper.id).label('count')
            )
            
            if not current_user.is_admin():
                platform_stats = platform_stats.filter_by(scraped_by=current_user.id)
            
            platform_stats = platform_stats.group_by(RawDataScraper.platform).all()
            
            # Convert to dict
            platform_dict = {}
            for platform, count in platform_stats:
                platform_dict[platform.lower()] = count
            
            # Recent scraping jobs (last 7 days)
            from datetime import datetime, timedelta
            week_ago = datetime.now() - timedelta(days=7)
            
            recent_query = base_query.filter(RawDataScraper.created_at >= week_ago)
            recent_scraping = recent_query.count()
            
            statistics = {
                'total': total_scraping,
                'twitter': platform_dict.get('twitter', 0),
                'facebook': platform_dict.get('facebook', 0),
                'tiktok': platform_dict.get('tiktok', 0),
                'instagram': platform_dict.get('instagram', 0),
                'recent_week': recent_scraping,
                'platforms': platform_dict
            }
            
            return jsonify(statistics)
            
        except Exception as e:
            return jsonify({'error': f'Error getting scraping statistics: {str(e)}'}), 500
    
    @app.route('/api/scraping/history')
    @login_required
    def get_scraping_history():
        """Get paginated scraping history without duplicates with search support"""
        try:
            page = request.args.get('page', 1, type=int)
            per_page = request.args.get('per_page', 10, type=int)
            search_query = request.args.get('search', '', type=str).strip()
            
            # Get unique scraping jobs grouped by keyword, platform, and dataset_id to show all scraping history
            if current_user.is_admin():
                # Use subquery to get the latest record for each unique combination
                subquery = db.session.query(
                    RawDataScraper.keyword,
                    RawDataScraper.platform,
                    RawDataScraper.dataset_id,
                    func.max(RawDataScraper.created_at).label('max_created_at')
                ).group_by(
                    RawDataScraper.keyword,
                    RawDataScraper.platform,
                    RawDataScraper.dataset_id
                ).subquery()
                
                base_query = db.session.query(RawDataScraper).join(
                    subquery,
                    db.and_(
                        RawDataScraper.keyword == subquery.c.keyword,
                        RawDataScraper.platform == subquery.c.platform,
                        RawDataScraper.dataset_id == subquery.c.dataset_id,
                        RawDataScraper.created_at == subquery.c.max_created_at
                    )
                )
                
                # Apply search filter if provided
                if search_query:
                    base_query = base_query.filter(
                        db.or_(
                            RawDataScraper.keyword.ilike(f'%{search_query}%'),
                            RawDataScraper.platform.ilike(f'%{search_query}%')
                        )
                    )
                
                # Order by created_at desc to show newest first
                base_query = base_query.order_by(desc(RawDataScraper.created_at))
            else:
                # Use subquery to get the latest record for each unique combination for current user
                subquery = db.session.query(
                    RawDataScraper.keyword,
                    RawDataScraper.platform,
                    RawDataScraper.dataset_id,
                    func.max(RawDataScraper.created_at).label('max_created_at')
                ).filter_by(
                    scraped_by=current_user.id
                ).group_by(
                    RawDataScraper.keyword,
                    RawDataScraper.platform,
                    RawDataScraper.dataset_id
                ).subquery()
                
                base_query = db.session.query(RawDataScraper).join(
                    subquery,
                    db.and_(
                        RawDataScraper.keyword == subquery.c.keyword,
                        RawDataScraper.platform == subquery.c.platform,
                        RawDataScraper.dataset_id == subquery.c.dataset_id,
                        RawDataScraper.created_at == subquery.c.max_created_at,
                        RawDataScraper.scraped_by == current_user.id
                    )
                )
                
                # Apply search filter if provided
                if search_query:
                    base_query = base_query.filter(
                        db.or_(
                            RawDataScraper.keyword.ilike(f'%{search_query}%'),
                            RawDataScraper.platform.ilike(f'%{search_query}%')
                        )
                    )
                
                # Order by created_at desc to show newest first
                base_query = base_query.order_by(desc(RawDataScraper.created_at))
            
            # Get total count for pagination
            total_count = base_query.count()
            
            # Apply pagination manually
            offset = (page - 1) * per_page
            items = base_query.offset(offset).limit(per_page).all()
            
            # Create pagination object manually
            class MockPagination:
                def __init__(self, items, page, per_page, total):
                    self.items = items
                    self.page = page
                    self.per_page = per_page
                    self.total = total
                    self.pages = (total + per_page - 1) // per_page
                    self.has_next = page < self.pages
                    self.has_prev = page > 1
            
            pagination = MockPagination(items, page, per_page, total_count)
            
            history_data = []
            for job in pagination.items:
                # Count related data for each specific dataset
                if current_user.is_admin():
                    data_count = RawDataScraper.query.filter_by(
                        keyword=job.keyword,
                        platform=job.platform,
                        dataset_id=job.dataset_id
                    ).count()
                else:
                    data_count = RawDataScraper.query.filter_by(
                        keyword=job.keyword,
                        platform=job.platform,
                        dataset_id=job.dataset_id,
                        scraped_by=current_user.id
                    ).count()
                
                # Determine status based on data processing state for specific dataset
                if current_user.is_admin():
                    # Get clean scraper IDs for this specific dataset
                    clean_scraper_ids = db.session.query(CleanDataScraper.id).join(
                        RawDataScraper, CleanDataScraper.raw_data_scraper_id == RawDataScraper.id
                    ).filter(
                        RawDataScraper.keyword == job.keyword,
                        RawDataScraper.platform == job.platform,
                        RawDataScraper.dataset_id == job.dataset_id
                    ).all()
                    
                    # Extract clean scraper IDs list
                    clean_scraper_ids_list = [row[0] for row in clean_scraper_ids]
                    
                    classified_count = db.session.query(func.count(ClassificationResult.id)).filter(
                        ClassificationResult.data_type == 'scraper',
                        ClassificationResult.data_id.in_(clean_scraper_ids_list)
                    ).scalar() or 0 if clean_scraper_ids_list else 0
                    
                    cleaned_count = CleanDataScraper.query.join(
                        RawDataScraper, CleanDataScraper.raw_data_scraper_id == RawDataScraper.id
                    ).filter(
                        RawDataScraper.keyword == job.keyword,
                        RawDataScraper.platform == job.platform,
                        RawDataScraper.dataset_id == job.dataset_id
                    ).count()
                else:
                    # Get clean scraper IDs for this specific dataset and user
                    clean_scraper_ids = db.session.query(CleanDataScraper.id).join(
                        RawDataScraper, CleanDataScraper.raw_data_scraper_id == RawDataScraper.id
                    ).filter(
                        RawDataScraper.keyword == job.keyword,
                        RawDataScraper.platform == job.platform,
                        RawDataScraper.dataset_id == job.dataset_id,
                        RawDataScraper.scraped_by == current_user.id
                    ).all()
                    
                    # Extract clean scraper IDs list
                    clean_scraper_ids_list = [row[0] for row in clean_scraper_ids]
                    
                    classified_count = db.session.query(func.count(ClassificationResult.id)).filter(
                        ClassificationResult.data_type == 'scraper',
                        ClassificationResult.data_id.in_(clean_scraper_ids_list)
                    ).scalar() or 0 if clean_scraper_ids_list else 0
                    
                    cleaned_count = CleanDataScraper.query.join(
                        RawDataScraper, CleanDataScraper.raw_data_scraper_id == RawDataScraper.id
                    ).filter(
                        RawDataScraper.keyword == job.keyword,
                        RawDataScraper.platform == job.platform,
                        RawDataScraper.dataset_id == job.dataset_id,
                        RawDataScraper.scraped_by == current_user.id
                    ).count()
                
                # Use stored status from database instead of calculating dynamically
                status = 'Mentah'  # Default status
                if job.dataset_id:
                    dataset = Dataset.query.get(job.dataset_id)
                    if dataset and dataset.status:
                        status = dataset.status
                
                # Check individual scraper data status for more accurate status
                # If any data in this scraping job has been cleaned, mark as 'Bersih'
                if cleaned_count > 0:
                    status = 'Bersih'
                # If any data in this scraping job has been classified, mark as 'Terklasifikasi'
                if classified_count > 0:
                    status = 'Terklasifikasi'
                
                # Get dataset information
                dataset = Dataset.query.get(job.dataset_id) if job.dataset_id else None
                dataset_name = dataset.name if dataset else f"Scraper Data {job.platform.title()} - {job.keyword}"
                
                # Get user information
                user = User.query.get(job.scraped_by) if job.scraped_by else None
                scraped_by_username = user.username if user else 'Unknown'
                
                job_data = {
                    'id': job.id,
                    'platform': job.platform,
                    'keywords': job.keyword,
                    'dataset_name': dataset_name,
                    'scraped_at': format_datetime(job.created_at, 'default') if job.created_at else None,
                    'created_at': format_datetime(job.created_at, 'datetime') if job.created_at else None,
                    'results_count': data_count,
                    'status': status,
                    'scraped_by': scraped_by_username
                }
                history_data.append(job_data)
            
            response_data = {
                'history': history_data,
                'pagination': {
                    'page': page,
                    'per_page': per_page,
                    'total': pagination.total,
                    'pages': pagination.pages,
                    'has_next': pagination.has_next,
                    'has_prev': pagination.has_prev
                }
            }
            
            return jsonify(response_data)
            
        except Exception as e:
            return jsonify({'error': f'Error getting scraping history: {str(e)}'}), 500
    
    @app.route('/delete_scraping/<int:job_id>', methods=['DELETE'])
    @login_required
    @admin_required
    def delete_scraping(job_id):
        """Delete scraping data completely from database"""
        try:
            # Get scraper data to delete
            scraper_data = RawDataScraper.query.get_or_404(job_id)
            
            # Get clean scraper data IDs for classification results
            clean_scraper_data = CleanDataScraper.query.filter_by(raw_data_scraper_id=job_id).all()
            clean_scraper_ids = [cd.id for cd in clean_scraper_data]
            
            # Delete classification results first
            if clean_scraper_ids:
                ClassificationResult.query.filter(
                    ClassificationResult.data_type == 'scraper',
                    ClassificationResult.data_id.in_(clean_scraper_ids)
                ).delete(synchronize_session=False)
            
            # Delete clean scraper data
            CleanDataScraper.query.filter_by(raw_data_scraper_id=job_id).delete()
            
            # Delete raw scraper data
            db.session.delete(scraper_data)
            
            db.session.commit()
            update_statistics()
            
            # Create consistent delete message based on platform
            platform_name = {
                'twitter': 'Twitter',
                'tiktok': 'TikTok', 
                'facebook': 'Facebook',
                'instagram': 'Instagram'
            }.get(scraper_data.platform.lower(), scraper_data.platform.title())
            
            # Log activity
            generate_activity_log(
                action='delete_scraping_data',
                description=f'Menghapus data scraping {platform_name} ID: {job_id}',
                user_id=current_user.id,
                icon='fas fa-trash',
                color='danger'
            )
            
            return jsonify({'success': True, 'message': f'Data scraping {platform_name} berhasil dihapus dari database'})
        except Exception as e:
            db.session.rollback()
            return jsonify({'success': False, 'message': f'Error: {str(e)}'}), 500
    
    @app.route('/api/scraper/<int:scraper_id>/delete', methods=['DELETE'])
    @login_required
    def api_delete_scraper(scraper_id):
        """Delete scraper data via API endpoint"""
        try:
            # Get scraper data to delete
            scraper_data = RawDataScraper.query.get_or_404(scraper_id)
            
            # Check permission dengan feedback yang jelas
            has_permission, message, http_status = check_permission_with_feedback(
                current_user, scraper_data.scraped_by, 'delete', 'scraper data'
            )
            if not has_permission:
                return jsonify({'success': False, 'message': message}), http_status
            
            # Get clean scraper data IDs for classification results
            clean_scraper_data = CleanDataScraper.query.filter_by(raw_data_scraper_id=scraper_id).all()
            clean_scraper_ids = [cd.id for cd in clean_scraper_data]
            
            # Delete classification results first
            if clean_scraper_ids:
                ClassificationResult.query.filter(
                    ClassificationResult.data_type == 'scraper',
                    ClassificationResult.data_id.in_(clean_scraper_ids)
                ).delete(synchronize_session=False)
            
            # Delete clean scraper data
            CleanDataScraper.query.filter_by(raw_data_scraper_id=scraper_id).delete()
            
            # Delete raw scraper data
            db.session.delete(scraper_data)
            
            db.session.commit()
            update_statistics()
            
            # Create consistent delete message based on platform
            platform_name = {
                'twitter': 'Twitter',
                'tiktok': 'TikTok',
                'facebook': 'Facebook', 
                'instagram': 'Instagram'
            }.get(scraper_data.platform.lower(), scraper_data.platform.title())
            
            # Log activity
            generate_activity_log(
                action='delete_scraping_data',
                description=f'Menghapus data scraping {platform_name} ID: {scraper_id}',
                user_id=current_user.id,
                icon='fas fa-trash',
                color='danger'
            )
            
            return jsonify({'success': True, 'message': f'Data scraping {platform_name} berhasil dihapus'})
        except Exception as e:
            db.session.rollback()
            return jsonify({'success': False, 'message': f'Error: {str(e)}'}), 500
    
    @app.route('/api/cleanup/orphaned-data', methods=['DELETE'])
    @login_required
    @admin_required
    def cleanup_orphaned_data():
        """Delete upload and scraper data that is not associated with any dataset"""
        try:
            total_deleted = 0
            
            # Clean up orphaned upload data
            orphaned_upload_ids = [row[0] for row in db.session.execute(
                text("SELECT id FROM raw_data WHERE dataset_id IS NULL")
            ).fetchall()]
            
            if orphaned_upload_ids:
                # Get clean upload IDs that will be deleted
                clean_upload_ids = [row[0] for row in db.session.execute(
                    text("SELECT id FROM clean_data_upload WHERE raw_data_id IN :ids"),
                    {'ids': tuple(orphaned_upload_ids)}
                ).fetchall()]
                
                # Delete classification results for clean upload data
                if clean_upload_ids:
                    db.session.execute(
                        text("DELETE FROM classification_results WHERE data_type = 'upload' AND data_id IN :ids"),
                        {'ids': tuple(clean_upload_ids)}
                    )
                
                # Delete clean upload data for orphaned records
                db.session.execute(
                    text("DELETE FROM clean_data_upload WHERE raw_data_id IN :ids"),
                    {'ids': tuple(orphaned_upload_ids)}
                )
                
                # Delete orphaned upload data
                db.session.execute(
                    text("DELETE FROM raw_data WHERE dataset_id IS NULL")
                )
                
                total_deleted += len(orphaned_upload_ids)
            
            # Clean up orphaned scraper data
            orphaned_scraper_ids = [row[0] for row in db.session.execute(
                text("SELECT id FROM raw_data_scraper WHERE dataset_id IS NULL")
            ).fetchall()]
            
            if orphaned_scraper_ids:
                # Get clean scraper IDs that will be deleted
                clean_scraper_ids = [row[0] for row in db.session.execute(
                    text("SELECT id FROM clean_data_scraper WHERE raw_data_scraper_id IN :ids"),
                    {'ids': tuple(orphaned_scraper_ids)}
                ).fetchall()]
                
                # Delete classification results for clean scraper data
                if clean_scraper_ids:
                    db.session.execute(
                        text("DELETE FROM classification_results WHERE data_type = 'scraper' AND data_id IN :ids"),
                        {'ids': tuple(clean_scraper_ids)}
                    )
                
                # Delete clean scraper data for orphaned records
                db.session.execute(
                    text("DELETE FROM clean_data_scraper WHERE raw_data_scraper_id IN :ids"),
                    {'ids': tuple(orphaned_scraper_ids)}
                )
                
                # Delete orphaned scraper data
                db.session.execute(
                    text("DELETE FROM raw_data_scraper WHERE dataset_id IS NULL")
                )
                
                total_deleted += len(orphaned_scraper_ids)
            
            db.session.commit()
            update_statistics()
            
            if total_deleted > 0:
                return jsonify({
                    'success': True, 
                    'message': f'{total_deleted} data orphan berhasil dihapus ({len(orphaned_upload_ids)} upload, {len(orphaned_scraper_ids)} scraper)'
                })
            else:
                return jsonify({
                    'success': True, 
                    'message': 'Tidak ada data orphan yang ditemukan'
                })
                
        except Exception as e:
            db.session.rollback()
            return jsonify({'success': False, 'message': f'Error: {str(e)}'}), 500
    
    # Removed duplicate dataset_management route - using /dataset/management instead
    
    @app.route('/api/dataset/<int:data_id>')
    @login_required
    @active_user_required
    def get_dataset_detail(data_id):
        """Get dataset detail"""
        try:
            data = RawData.query.get_or_404(data_id)
            
            # Get classification result if exists
            result_cr = db.session.execute(text("SELECT * FROM classification_results WHERE data_type = 'upload' AND data_id = :data_id LIMIT 1"), {'data_id': data_id})
            classification = result_cr.fetchone()
            
            result = {
                'id': data.id,
                'text': data.text,
                'source': data.source,
                'platform': data.platform,
                'is_cleaned': data.is_cleaned,
                'is_classified': data.is_classified,
                'created_at': format_datetime(data.created_at, 'default'),
                'cleaned_text': None,
                'classification_result': None
            }
            
            # Get cleaned text
            if data.is_cleaned:
                if data.source == 'upload':
                    clean_data = CleanDataUpload.query.filter_by(raw_data_id=data_id).first()
                    if clean_data:
                        result['cleaned_text'] = clean_data.cleaned_text
                else:
                    # Use raw SQL for CleanDataScraper
                    result_query = db.session.execute(text("SELECT * FROM clean_data_scraper WHERE raw_data_scraper_id = :data_id LIMIT 1"), {'data_id': data_id})
                    clean_data = result_query.fetchone()
                    if clean_data:
                        result['cleaned_text'] = clean_data.cleaned_text
            
            # Get classification result
            if classification:
                result['classification_result'] = {
                    'prediction': classification.prediction,
                    'probability': classification.probability
                }
            
            return jsonify(result)
        except Exception as e:
            return jsonify({'error': str(e)}), 500
    
    @app.route('/api/raw_data/<int:data_id>', methods=['DELETE'])
    @login_required
    @active_user_required
    def delete_raw_data(data_id):
        """Delete single dataset"""
        try:
            data = RawData.query.get_or_404(data_id)
            
            # Get clean data IDs for classification results
            clean_data_ids = [cd.id for cd in CleanDataUpload.query.filter_by(raw_data_id=data_id).all()]
            
            # Delete classification results for this raw data
            if clean_data_ids:
                db.session.execute(
                    text("DELETE FROM classification_results WHERE data_type = 'upload' AND data_id IN :ids"),
                    {'ids': tuple(clean_data_ids)}
                )
            
            # Delete clean data upload
            CleanDataUpload.query.filter_by(raw_data_id=data_id).delete()
            
            # Delete main record
            db.session.delete(data)
            db.session.commit()
            update_statistics()
            
            return jsonify({'success': True, 'message': 'Data berhasil dihapus'})
        except Exception as e:
            db.session.rollback()
            return jsonify({'success': False, 'message': f'Error: {str(e)}'}), 500
    
    @app.route('/api/dataset/bulk_delete', methods=['POST'])
    @login_required
    @active_user_required
    def bulk_delete_dataset():
        """Bulk delete datasets"""
        try:
            data_ids = request.form.getlist('data_ids')
            if not data_ids:
                return jsonify({'success': False, 'message': 'Tidak ada data yang dipilih'}), 400
            
            # Convert to integers
            data_ids = [int(id) for id in data_ids]
            
            # Delete related records
            placeholders_cr = ','.join([':id' + str(i) for i in range(len(data_ids))])
            params_cr = {'id' + str(i): data_ids[i] for i in range(len(data_ids))}
            db.session.execute(text(f"DELETE FROM classification_results WHERE data_type = 'upload' AND data_id IN ({placeholders_cr})"), params_cr)
            CleanDataUpload.query.filter(CleanDataUpload.raw_data_id.in_(data_ids)).delete(synchronize_session=False)
            # Use raw SQL for CleanDataScraper bulk delete
            placeholders = ','.join([':id' + str(i) for i in range(len(data_ids))])
            params = {'id' + str(i): data_ids[i] for i in range(len(data_ids))}
            db.session.execute(text(f"DELETE FROM clean_data_scraper WHERE raw_data_scraper_id IN ({placeholders})"), params)
            
            # Delete main records
            RawData.query.filter(RawData.id.in_(data_ids)).delete(synchronize_session=False)
            
            db.session.commit()
            update_statistics()
            
            return jsonify({'success': True, 'message': f'{len(data_ids)} data berhasil dihapus'})
        except Exception as e:
            db.session.rollback()
            return jsonify({'success': False, 'message': f'Error: {str(e)}'}), 500
    
    @app.route('/api/clean_data', methods=['POST'])
    @login_required
    @active_user_required
    def clean_data_api():
        """Clean data API"""
        try:
            # Handle both JSON and form data
            if request.is_json:
                data_ids = request.json.get('data_ids', [])
            else:
                data_ids = request.form.getlist('data_ids')
                
            if not data_ids:
                return jsonify({'success': False, 'message': 'Tidak ada data yang dipilih'}), 400
            
            # Convert to integers
            data_ids = [int(id) for id in data_ids]
            
            cleaned_count = 0
            for data_id in data_ids:
                # Check RawData first
                raw_data = RawData.query.get(data_id)
                if raw_data:
                    # Check if already cleaned
                    existing_clean = CleanDataUpload.query.filter_by(raw_data_id=data_id).first()
                    if existing_clean:
                        continue
                    
                    # Clean the content
                    cleaned_content = clean_text(raw_data.content)
                    
                    # Check for duplicate content
                    is_duplicate = check_cleaned_content_duplicate(cleaned_content)
                    
                    if not is_duplicate:
                        # Save cleaned data
                        clean_data = CleanDataUpload(
                            raw_data_id=data_id,
                            username=raw_data.username,
                            content=raw_data.content,
                            cleaned_content=cleaned_content,
                            url=raw_data.url,
                            platform=raw_data.platform,
                            cleaned_by=current_user.id
                        )
                        
                        db.session.add(clean_data)
                        cleaned_count += 1
                    
                    # Update raw data status regardless of duplication
                    raw_data.status = 'cleaned'
                    continue
                
                # Check RawDataScraper
                raw_scraper = RawDataScraper.query.get(data_id)
                if raw_scraper:
                    # Check if already cleaned using raw SQL
                    result = db.session.execute(text("SELECT * FROM clean_data_scraper WHERE raw_data_scraper_id = :data_id LIMIT 1"), {'data_id': data_id})
                    existing_clean = result.fetchone()
                    if existing_clean:
                        continue
                    
                    # Clean the content
                    cleaned_content = clean_text(raw_scraper.content)
                    
                    # Check for duplicate content
                    is_duplicate = check_cleaned_content_duplicate(cleaned_content)
                    
                    if not is_duplicate:
                        # Save cleaned data
                        clean_data = CleanDataScraper(
                            raw_data_scraper_id=data_id,
                            username=raw_scraper.username,
                            content=raw_scraper.content,
                            cleaned_content=cleaned_content,
                            url=raw_scraper.url,
                            platform=raw_scraper.platform,
                            keyword=raw_scraper.keyword,
                            dataset_id=raw_scraper.dataset_id,
                            cleaned_by=current_user.id
                        )
                        
                        db.session.add(clean_data)
                        cleaned_count += 1
                    
                    # Update raw data status regardless of duplication
                    raw_scraper.status = 'cleaned'
            
            db.session.commit()
            update_statistics()
            
            # Log cleaning activity
            if cleaned_count > 0:
                generate_activity_log(
                    action='Data Cleaning',
                    description=f'Membersihkan {cleaned_count} data',
                    user_id=current_user.id,
                    details={'cleaned_count': cleaned_count},
                    icon='fas fa-broom',
                    color='warning'
                )
            
            return jsonify({
                'success': True,
                'message': f'{cleaned_count} data berhasil dibersihkan',
                'cleaned_count': cleaned_count
            })
        except Exception as e:
            db.session.rollback()
            return jsonify({'success': False, 'message': f'Error: {str(e)}'}), 500
    
    @app.route('/api/cleaned_data', methods=['GET'])
    @login_required
    def get_cleaned_data():
        """Get cleaned data API"""
        try:
            # Get cleaned upload data
            cleaned_uploads = CleanDataUpload.query.all()
            upload_data = []
            for item in cleaned_uploads:
                upload_data.append({
                    'id': item.id,
                    'raw_data_id': item.raw_data_id,
                    'username': item.username,
                    'content': item.content,
                    'cleaned_content': item.cleaned_content,
                    'url': item.url,
                    'platform': item.platform,
                    'type': 'upload',
                    'cleaned_by': item.cleaned_by,
                    'created_at': format_datetime(item.created_at, 'default') if item.created_at else None
                })
            
            # Get cleaned scraper data using raw SQL
            result = db.session.execute(text("SELECT * FROM clean_data_scraper ORDER BY created_at DESC"))
            cleaned_scrapers = result.fetchall()
            scraper_data = []
            for item in cleaned_scrapers:
                scraper_data.append({
                    'id': item.id,
                    'raw_data_scraper_id': item.raw_data_scraper_id,
                    'username': item.username,
                    'content': item.content,
                    'cleaned_content': item.cleaned_content,
                    'url': item.url,
                    'platform': item.platform,
                    'keyword': item.keyword,
                    'type': 'scraper',
                    'cleaned_by': item.cleaned_by,
                    'created_at': item.created_at.isoformat() if item.created_at else None
                })
            
            # Combine both datasets
            all_cleaned_data = upload_data + scraper_data
            
            return jsonify(all_cleaned_data)
        except Exception as e:
            return jsonify({'error': f'Error retrieving cleaned data: {str(e)}'}), 500
    
    @app.route('/api/classify_data', methods=['POST'])
    @login_required
    @active_user_required
    def classify_data_api():
        """Classify data API"""
        try:
            # Support both JSON and form data
            if request.is_json:
                data_ids = request.json.get('data_ids', [])
            else:
                data_ids = request.form.getlist('data_ids')
            
            if not data_ids:
                return jsonify({'success': False, 'message': 'Tidak ada data yang dipilih'}), 400
            
            # Convert to integers
            data_ids = [int(id) for id in data_ids]
            
            classified_count = 0
            for data_id in data_ids:
                # Check both CleanDataUpload and CleanDataScraper
                clean_data_upload = CleanDataUpload.query.get(data_id)
                # Use raw SQL for CleanDataScraper
                result = db.session.execute(text("SELECT * FROM clean_data_scraper WHERE id = :data_id"), {'data_id': data_id})
                clean_data_scraper = result.fetchone()
                
                clean_data = clean_data_upload or clean_data_scraper
                if not clean_data:
                    continue
                
                # Determine data type and get cleaned text
                if clean_data_upload:
                    data_type = 'upload'
                    cleaned_text = clean_data_upload.cleaned_content
                else:
                    data_type = 'scraper'
                    cleaned_text = clean_data_scraper.cleaned_content
                
                if not cleaned_text:
                    continue
                
                # Check if already classified
                result = db.session.execute(text("SELECT * FROM classification_results WHERE data_type = :data_type AND data_id = :data_id LIMIT 1"), {'data_type': data_type, 'data_id': data_id})
                existing_classification = result.fetchone()
                if existing_classification:
                    continue
                
                # Classify the text using available models
                try:
                    # Get models from app config
                    word2vec_model = current_app.config.get('WORD2VEC_MODEL')
                    naive_bayes_models = current_app.config.get('NAIVE_BAYES_MODELS', {})
                    
                    # Vectorize text
                    text_vector = vectorize_text(cleaned_text, word2vec_model)
                    
                    # Classify with each available model
                    for model_name, model in naive_bayes_models.items():
                        if model is not None:
                            prediction, probabilities = classify_content(text_vector, model)
                            
                            # Save classification result
                            # Handle probabilities consistently
                            if isinstance(probabilities, (list, tuple, np.ndarray)) and len(probabilities) >= 2:
                                prob_non_radikal = float(probabilities[0])
                                prob_radikal = float(probabilities[1])
                            else:
                                prob_non_radikal = 0.0
                                prob_radikal = 0.0
                            
                            classification = ClassificationResult(
                                data_type=data_type,
                                data_id=data_id,
                                model_name=model_name,
                                prediction=prediction,
                                probability_radikal=prob_radikal,
                                probability_non_radikal=prob_non_radikal,
                                classified_by=current_user.id
                            )
                            
                            db.session.add(classification)
                    
                    # Update raw data status to 'classified'
                    if data_type == 'scraper':
                        # Update RawDataScraper status
                        raw_scraper_result = db.session.execute(text("SELECT raw_data_scraper_id FROM clean_data_scraper WHERE id = :data_id"), {'data_id': data_id})
                        raw_scraper_row = raw_scraper_result.fetchone()
                        if raw_scraper_row:
                            raw_scraper = RawDataScraper.query.get(raw_scraper_row.raw_data_scraper_id)
                            if raw_scraper:
                                raw_scraper.status = 'classified'
                    elif data_type == 'upload':
                        # Update RawData status
                        clean_upload = CleanDataUpload.query.get(data_id)
                        if clean_upload:
                            raw_upload = RawData.query.get(clean_upload.raw_data_id)
                            if raw_upload:
                                raw_upload.status = 'classified'
                    
                    classified_count += 1
                except Exception as classify_error:
                    continue
            
            db.session.commit()
            update_statistics()
            
            # Log classification activity
            if classified_count > 0:
                generate_activity_log(
                    action='Data Classification',
                    description=f'Mengklasifikasi {classified_count} data',
                    user_id=current_user.id,
                    details={'classified_count': classified_count},
                    icon='fas fa-brain',
                    color='info'
                )
            
            return jsonify({
                'success': True, 
                'message': f'{classified_count} data berhasil diklasifikasi',
                'classified_count': classified_count
            })
        except Exception as e:
            db.session.rollback()
            return jsonify({'success': False, 'message': f'Error: {str(e)}'}), 500
    
    @app.route('/api/test_classification_models', methods=['GET'])
    @login_required
    @active_user_required
    def test_classification_models():
        """Test API to check if 3 models are working correctly"""
        try:
            # Get sample classification results grouped by data_id to see all 3 models
            result_query = db.session.execute(text("""
                SELECT data_type, data_id, model_name, prediction, 
                       probability_radikal, probability_non_radikal, created_at 
                FROM classification_results 
                ORDER BY data_id, model_name 
                LIMIT 15
            """))
            results = result_query.fetchall()
            
            test_data = []
            for result in results:
                test_data.append({
                    'data_type': result.data_type,
                    'data_id': result.data_id,
                    'model_name': result.model_name,
                    'prediction': result.prediction,
                    'probability_radikal': result.probability_radikal,
                    'probability_non_radikal': result.probability_non_radikal,
                    'created_at': result.created_at.isoformat() if result.created_at else None
                })
            
            return jsonify({
                'success': True,
                'total_results': len(test_data),
                'results': test_data
            })
        except Exception as e:
            return jsonify({'success': False, 'error': str(e)}), 500
    
    @app.route('/api/classification_results', methods=['GET'])
    @login_required
    @active_user_required
    def get_classification_results():
        """Get classification results API"""
        # Check if user is admin
        if not current_user.is_admin():
            return jsonify({'error': 'Hanya admin yang dapat mengakses semua hasil klasifikasi'}), 403
        
        try:
            # Get all classification results
            result_query = db.session.execute(text("SELECT * FROM classification_results ORDER BY created_at DESC"))
            results = result_query.fetchall()
            
            classification_data = []
            for result in results:
                # Get the original data based on data_type
                if result.data_type == 'upload':
                    clean_data = CleanDataUpload.query.get(result.data_id)
                    if clean_data:
                        data_info = {
                            'id': result.id,
                            'data_id': result.data_id,
                            'data_type': result.data_type,
                            'model_name': result.model_name,
                            'prediction': result.prediction,
                            'probability_radikal': result.probability_radikal,
                            'probability_non_radikal': result.probability_non_radikal,
                            'content': clean_data.cleaned_content[:100] + '...' if len(clean_data.cleaned_content) > 100 else clean_data.cleaned_content,
                            'platform': getattr(clean_data, 'platform', 'Upload'),
                            'username': getattr(clean_data, 'username', 'N/A'),
                            'created_at': format_datetime(result.created_at, 'default')
                        }
                        classification_data.append(data_info)
                else:
                    # Use raw SQL for CleanDataScraper
                    result_query = db.session.execute(text("SELECT * FROM clean_data_scraper WHERE id = :data_id"), {'data_id': result.data_id})
                    clean_data = result_query.fetchone()
                    if clean_data:
                        data_info = {
                            'id': result.id,
                            'data_id': result.data_id,
                            'data_type': result.data_type,
                            'model_name': result.model_name,
                            'prediction': result.prediction,
                            'probability_radikal': result.probability_radikal,
                            'probability_non_radikal': result.probability_non_radikal,
                            'content': clean_data.cleaned_content[:100] + '...' if len(clean_data.cleaned_content) > 100 else clean_data.cleaned_content,
                            'platform': clean_data.platform,
                            'username': clean_data.username,
                            'created_at': format_datetime(result.created_at, 'default')
                        }
                        classification_data.append(data_info)
            
            return jsonify(classification_data)
        except Exception as e:
            return jsonify({'error': f'Error retrieving classification results: {str(e)}'}), 500
    
    @app.route('/api/export_classification_results', methods=['GET'])
    @app.route('/api/export/classification-results', methods=['POST'])
    @login_required
    @active_user_required
    def export_classification_results_api():
        """Export classification results to CSV or Excel sesuai dengan tampilan UI"""
        # All logged-in users can export classification results
        
        try:
            from utils import export_classification_results
            from flask import Response
            import io
            
            # Get format parameter from GET args or POST JSON
            if request.method == 'POST' and request.is_json:
                format_type = request.json.get('format', 'csv').lower()
                # For POST requests, we can use the data sent from frontend
                frontend_data = request.json.get('data', [])
                # Get dataset_id parameter for filtering
                dataset_id = request.json.get('dataset_id')
            else:
                format_type = request.args.get('format', 'csv').lower()
                frontend_data = None
                dataset_id = request.args.get('dataset_id')
            
            if format_type not in ['csv', 'excel']:
                return jsonify({'error': 'Format harus csv atau excel'}), 400
            
            # Check if openpyxl is available for Excel export
            if format_type == 'excel' and not OPENPYXL_AVAILABLE:
                return jsonify({'error': 'Library openpyxl tidak tersedia untuk export Excel'}), 400
            
            # Use frontend data if available, otherwise query database
            if frontend_data:
                # Convert frontend data to the expected format
                final_results = []
                for item in frontend_data:
                    result_item = {
                        'data_id': item.get('data_id'),
                        'data_type': item.get('data_type', 'upload'),
                        'username': item.get('username', ''),
                        'content': item.get('content', ''),
                        'url': item.get('url', ''),
                        'created_at': item.get('created_at'),
                        'models': {
                            'model1': {
                                'prediction': item.get('model1', ''),
                                'probability_radikal': 0,
                                'probability_non_radikal': 0
                            },
                            'model2': {
                                'prediction': item.get('model2', ''),
                                'probability_radikal': 0,
                                'probability_non_radikal': 0
                            },
                            'model3': {
                                'prediction': item.get('model3', ''),
                                'probability_radikal': 0,
                                'probability_non_radikal': 0
                            }
                        }
                    }
                    final_results.append(result_item)
            else:
                # Build queries based on dataset_id filter
                if dataset_id:
                    # Filter by specific dataset
                    upload_results = db.session.execute(
                        text("""
                            SELECT cr.id, cr.data_type, cr.data_id, cr.model_name, cr.prediction, 
                                   cr.probability_radikal, cr.probability_non_radikal, cr.created_at,
                                   cdu.cleaned_content as content, cdu.username, cdu.url
                            FROM classification_results cr 
                            JOIN clean_data_upload cdu ON cr.data_type = 'upload' AND cr.data_id = cdu.id
                            JOIN raw_data rd ON cdu.raw_data_id = rd.id
                            WHERE rd.dataset_id = :dataset_id
                            ORDER BY cr.created_at DESC
                        """),
                        {'dataset_id': dataset_id}
                    ).fetchall()
                    
                    scraper_results = db.session.execute(
                        text("""
                            SELECT cr.id, cr.data_type, cr.data_id, cr.model_name, cr.prediction, 
                                   cr.probability_radikal, cr.probability_non_radikal, cr.created_at,
                                   cds.cleaned_content as content, cds.username, cds.url
                            FROM classification_results cr 
                            JOIN clean_data_scraper cds ON cr.data_type = 'scraper' AND cr.data_id = cds.id
                            JOIN raw_data_scraper rds ON cds.raw_data_scraper_id = rds.id
                            WHERE rds.dataset_id = :dataset_id
                            ORDER BY cr.created_at DESC
                        """),
                        {'dataset_id': dataset_id}
                    ).fetchall()
                else:
                    # Get all classification results (same as UI)
                    upload_results = db.session.execute(
                        text("""
                            SELECT cr.id, cr.data_type, cr.data_id, cr.model_name, cr.prediction, 
                                   cr.probability_radikal, cr.probability_non_radikal, cr.created_at,
                                   cdu.cleaned_content as content, cdu.username, cdu.url
                            FROM classification_results cr 
                            JOIN clean_data_upload cdu ON cr.data_type = 'upload' AND cr.data_id = cdu.id
                            ORDER BY cr.created_at DESC
                        """)
                    ).fetchall()
                    
                    # Get classification results with joined data for scraper (same as UI)
                    scraper_results = db.session.execute(
                        text("""
                            SELECT cr.id, cr.data_type, cr.data_id, cr.model_name, cr.prediction, 
                                   cr.probability_radikal, cr.probability_non_radikal, cr.created_at,
                                   cds.cleaned_content as content, cds.username, cds.url
                            FROM classification_results cr 
                            JOIN clean_data_scraper cds ON cr.data_type = 'scraper' AND cr.data_id = cds.id
                            ORDER BY cr.created_at DESC
                        """)
                    ).fetchall()
                
                # Combine results
                all_results = list(upload_results) + list(scraper_results)
                
                if not all_results:
                    error_msg = f'Tidak ada data hasil klasifikasi untuk dataset yang dipilih' if dataset_id else 'Tidak ada data hasil klasifikasi untuk diexport'
                    return jsonify({'error': error_msg}), 404
                
                # Group results by data_id and data_type to show all 3 models in one row (same as UI)
                grouped_results = {}
                for result in all_results:
                    key = f"{result.data_type}_{result.data_id}"
                    if key not in grouped_results:
                        grouped_results[key] = {
                            'data_id': result.data_id,
                            'data_type': result.data_type,
                            'username': result.username,
                            'content': result.content,
                            'url': result.url,
                            'created_at': result.created_at,
                            'models': {}
                        }
                    grouped_results[key]['models'][result.model_name] = {
                        'prediction': result.prediction,
                        'probability_radikal': result.probability_radikal,
                        'probability_non_radikal': result.probability_non_radikal
                    }
                
                # Convert to list and sort by created_at desc
                final_results = list(grouped_results.values())
                final_results.sort(key=lambda x: x['created_at'], reverse=True)
            
            if not final_results:
                return jsonify({'error': 'Tidak ada data hasil klasifikasi untuk diexport'}), 404
            
            # Use the updated export function
            filename = export_classification_results(final_results, format_type)
            
            if not filename:
                return jsonify({'error': 'Gagal membuat file export'}), 500
            
            # Log download activity
            generate_activity_log(
                action='download_results',
                description=f'Mengunduh hasil klasifikasi dalam format {format_type.upper()}',
                user_id=current_user.id,
                details={
                    'format': format_type,
                    'record_count': len(final_results),
                    'dataset_id': dataset_id if dataset_id else 'all'
                },
                icon='fas fa-download',
                color='success'
            )
            
            # Read the file and return as response
            if format_type == 'csv':
                with open(filename, 'r', encoding='utf-8-sig') as f:
                    content = f.read()
                os.remove(filename)  # Clean up temp file
                
                return Response(
                    content,
                    mimetype='text/csv',
                    headers={'Content-Disposition': f'attachment; filename={filename}'}
                )
            
            elif format_type == 'excel':
                with open(filename, 'rb') as f:
                    content = f.read()
                os.remove(filename)  # Clean up temp file
                
                return Response(
                    content,
                    mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                    headers={'Content-Disposition': f'attachment; filename={filename}'}
                )
                
        except Exception as e:
            return jsonify({'error': f'Error exporting classification results: {str(e)}'}), 500
    
    @app.route('/api/model_metrics', methods=['GET'])
    @login_required
    @active_user_required
    def get_model_metrics():
        """Get model performance metrics API"""
        try:
            metrics = {}
            
            # Get metrics for each model
            for model_name in ['model1', 'model2', 'model3']:
                total_predictions = db.session.execute(text("SELECT COUNT(*) FROM classification_results WHERE model_name = :model_name"), {'model_name': model_name}).scalar()
                radikal_predictions = db.session.execute(text("SELECT COUNT(*) FROM classification_results WHERE model_name = :model_name AND prediction = 'radikal'"), {'model_name': model_name}).scalar()
                non_radikal_predictions = db.session.execute(text("SELECT COUNT(*) FROM classification_results WHERE model_name = :model_name AND prediction = 'non-radikal'"), {'model_name': model_name}).scalar()
                
                metrics[model_name] = {
                    'total_predictions': total_predictions,
                    'radikal_predictions': radikal_predictions,
                    'non_radikal_predictions': non_radikal_predictions,
                    'radikal_percentage': (radikal_predictions / total_predictions * 100) if total_predictions > 0 else 0,
                    'non_radikal_percentage': (non_radikal_predictions / total_predictions * 100) if total_predictions > 0 else 0
                }
            
            return jsonify(metrics)
        except Exception as e:
            return jsonify({'error': f'Error retrieving model metrics: {str(e)}'}), 500
    
    @app.route('/api/model_performance', methods=['GET'])
    @login_required
    @active_user_required
    def get_model_performance():
        """Get model performance metrics API (alias for model_metrics)"""
        return get_model_metrics()
    
    # Helper functions
    def allowed_file(filename):
        """
        DEPRECATED: Use SecurityValidator.validate_file_upload() instead
        This function is kept for backward compatibility but should be replaced
        """
        return '.' in filename and \
               filename.rsplit('.', 1)[1].lower() in {'csv', 'xlsx', 'xls'}
    
    def update_statistics_simplified():
        """Simplified statistics update for use during classification to avoid database locks"""
        try:
            stats = DatasetStatistics.query.first()
            if not stats:
                stats = DatasetStatistics()
                db.session.add(stats)
            
            # Use raw SQL for faster counting with minimal locking
            # Count raw upload data
            stats.total_raw_upload = db.session.execute(
                text("SELECT COUNT(*) FROM raw_data WHERE dataset_id IS NOT NULL")
            ).scalar() or 0
            
            # Count raw scraper data
            stats.total_raw_scraper = db.session.execute(
                text("SELECT COUNT(*) FROM raw_data_scraper WHERE dataset_id IS NOT NULL")
            ).scalar() or 0
            
            # Count clean upload data using efficient EXISTS subquery
            stats.total_clean_upload = db.session.execute(
                text("""SELECT COUNT(*) FROM clean_data_upload cdu 
                WHERE EXISTS (SELECT 1 FROM raw_data rd WHERE rd.id = cdu.raw_data_id AND rd.dataset_id IS NOT NULL)""")
            ).scalar() or 0
            
            # Count clean scraper data using efficient EXISTS subquery
            stats.total_clean_scraper = db.session.execute(
                text("""SELECT COUNT(*) FROM clean_data_scraper cds 
                WHERE EXISTS (SELECT 1 FROM raw_data_scraper rds WHERE rds.id = cds.raw_data_scraper_id AND rds.dataset_id IS NOT NULL)""")
            ).scalar() or 0
            
            # Use efficient counting for classification results
            stats.total_classified = db.session.execute(
                text("SELECT COUNT(*) FROM classification_results")
            ).scalar() or 0
            
            stats.total_radikal = db.session.execute(
                text("SELECT COUNT(*) FROM classification_results WHERE prediction = 'radikal'")
            ).scalar() or 0
            
            stats.total_non_radikal = db.session.execute(
                text("SELECT COUNT(*) FROM classification_results WHERE prediction = 'non-radikal'")
            ).scalar() or 0
            
            db.session.commit()
            app.logger.info("Simplified statistics updated successfully with optimized queries")
            
        except Exception as e:
            db.session.rollback()
            app.logger.error(f"Error updating simplified statistics: {str(e)}")
            # Don't raise exception to avoid breaking classification process
    
    def update_statistics():
        """Update dataset statistics - only count data that belongs to existing datasets"""
        try:
            stats = DatasetStatistics.query.first()
            if not stats:
                stats = DatasetStatistics()
                db.session.add(stats)
            
            # Count only data that belongs to existing datasets
            stats.total_raw_upload = db.session.execute(
                text("SELECT COUNT(*) FROM raw_data WHERE dataset_id IS NOT NULL")
            ).scalar() or 0
            
            stats.total_raw_scraper = db.session.execute(
                text("SELECT COUNT(*) FROM raw_data_scraper WHERE dataset_id IS NOT NULL")
            ).scalar() or 0
            
            stats.total_clean_upload = db.session.execute(
                text("SELECT COUNT(*) FROM clean_data_upload WHERE dataset_id IS NOT NULL")
            ).scalar() or 0
            
            stats.total_clean_scraper = db.session.execute(
                text("SELECT COUNT(*) FROM clean_data_scraper WHERE raw_data_scraper_id IN (SELECT id FROM raw_data_scraper WHERE dataset_id IS NOT NULL)")
            ).scalar() or 0
            
            stats.total_classified = db.session.execute(
                text("""SELECT COUNT(*) FROM classification_results 
                WHERE (data_type = 'upload' AND data_id IN (SELECT id FROM clean_data_upload WHERE dataset_id IS NOT NULL))
                OR (data_type = 'scraper' AND data_id IN (SELECT id FROM clean_data_scraper WHERE raw_data_scraper_id IN (SELECT id FROM raw_data_scraper WHERE dataset_id IS NOT NULL)))""")
            ).scalar() or 0
            
            stats.total_radikal = db.session.execute(
                text("""SELECT COUNT(*) FROM classification_results 
                WHERE prediction = 'radikal'
                AND ((data_type = 'upload' AND data_id IN (SELECT id FROM clean_data_upload WHERE dataset_id IS NOT NULL))
                OR (data_type = 'scraper' AND data_id IN (SELECT id FROM clean_data_scraper WHERE raw_data_scraper_id IN (SELECT id FROM raw_data_scraper WHERE dataset_id IS NOT NULL))))""")
            ).scalar() or 0
            
            stats.total_non_radikal = db.session.execute(
                text("""SELECT COUNT(*) FROM classification_results 
                WHERE prediction = 'non-radikal'
                AND ((data_type = 'upload' AND data_id IN (SELECT id FROM clean_data_upload WHERE dataset_id IS NOT NULL))
                OR (data_type = 'scraper' AND data_id IN (SELECT id FROM clean_data_scraper WHERE raw_data_scraper_id IN (SELECT id FROM raw_data_scraper WHERE dataset_id IS NOT NULL))))""")
            ).scalar() or 0
            
            db.session.commit()
            app.logger.info("Statistics updated successfully")
            
        except Exception as e:
            db.session.rollback()
            app.logger.error(f"Error updating statistics: {str(e)}")
            import traceback
            app.logger.error(f"Statistics update traceback: {traceback.format_exc()}")
    

    

    
    # Admin Panel Routes
    @app.route('/admin_panel')
    @login_required
    @admin_required
    def admin_panel():
        """Admin panel for user management"""
        # Get filter parameters
        role_filter = request.args.get('role', '')
        status_filter = request.args.get('status', '')
        search_query = request.args.get('search', '')
        
        # Build query
        query = User.query
        
        if role_filter:
            query = query.filter(User.role == role_filter)
        
        if status_filter:
            is_active = status_filter == '1'
            query = query.filter(User.is_active == is_active)
        
        if search_query:
            query = query.filter(
                db.or_(
                    User.username.ilike(f'%{search_query}%'),
                    User.email.ilike(f'%{search_query}%')
                )
            )

        users = query.order_by(User.created_at.desc()).all()
        
        # Calculate statistics
        total_users = User.query.count()
        active_users = User.query.filter(User.is_active == True).count()
        admin_users = User.query.filter(User.role == 'admin').count()
        inactive_users = User.query.filter(User.is_active == False).count()
        
        return render_template('admin/admin_panel.html',
                             users=users,
                             total_users=total_users,
                             active_users=active_users,
                             admin_users=admin_users,
                             inactive_users=inactive_users,
                             current_time=datetime.utcnow())
    
    # Admin API Routes
    @app.route('/api/admin/users', methods=['POST'])
    @login_required
    @admin_required
    def create_user():
        """Create new user"""
        try:
            username = request.form.get('username')
            email = request.form.get('email')
            password = request.form.get('password')
            role = request.form.get('role', 'user')
            is_active = request.form.get('is_active') == 'true'
            
            # Validate input
            if not username or not email or not password:
                return jsonify({'success': False, 'message': 'Semua field wajib diisi'}), 400
            
            # Check if username or email already exists
            if User.query.filter_by(username=username).first():
                return jsonify({'success': False, 'message': 'Username sudah digunakan'}), 400
            
            if User.query.filter_by(email=email).first():
                return jsonify({'success': False, 'message': 'Email sudah digunakan'}), 400
            
            # Create new user
            new_user = User(
                username=username,
                email=email,
                password_hash=generate_password_hash(password),
                role=role,
                is_active=is_active,
                created_at=datetime.utcnow()
            )
            
            db.session.add(new_user)
            db.session.commit()
            
            return jsonify({'success': True, 'message': 'Pengguna berhasil dibuat'})
        
        except Exception as e:
            db.session.rollback()
            return jsonify({'success': False, 'message': f'Error: {str(e)}'}), 500
    
    @app.route('/api/admin/users/<int:user_id>', methods=['GET'])
    @login_required
    @admin_required
    def get_user_detail(user_id):
        """Get user detail with statistics"""
        try:
            user = User.query.get_or_404(user_id)
            
            # Get user statistics
            total_uploads = RawData.query.filter_by(uploaded_by=user_id).count()
            total_scraping = RawDataScraper.query.filter_by(scraped_by=user_id).count()
            
            # Get total classifications using subquery to avoid join issues
            upload_classifications = db.session.execute(text("""
                SELECT COUNT(*) FROM classification_results 
                WHERE data_type = 'upload' AND data_id IN (
                    SELECT cdu.id FROM clean_data_upload cdu 
                    WHERE cdu.raw_data_id IN (
                        SELECT rd.id FROM raw_data rd WHERE rd.uploaded_by = :user_id
                    )
                )
            """), {'user_id': user_id}).scalar()
            
            scraper_classifications = db.session.execute(text("""
                SELECT COUNT(*) FROM classification_results 
                WHERE data_type = 'scraper' AND data_id IN (
                    SELECT cds.id FROM clean_data_scraper cds 
                    WHERE cds.raw_data_scraper_id IN (
                        SELECT rds.id FROM raw_data_scraper rds WHERE rds.scraped_by = :user_id
                    )
                )
            """), {'user_id': user_id}).scalar()
            
            total_classifications = (upload_classifications or 0) + (scraper_classifications or 0)
            
            # Get recent activities from database
            from models import UserActivity
            activities = UserActivity.query.filter_by(user_id=user_id).order_by(UserActivity.created_at.desc()).limit(10).all()
            
            recent_activities = []
            for activity in activities:
                recent_activities.append({
                    'title': activity.action.replace('_', ' ').title(),
                    'description': activity.description,
                    'created_at': format_datetime(activity.created_at, 'default'),
                    'icon': activity.icon or 'fa-info-circle',
                    'color': activity.color or 'primary'
                })
            
            # If no activities found, add default activities
            if not recent_activities:
                recent_activities = [
                    {
                        'title': 'Login ke sistem',
                        'description': 'Pengguna berhasil login',
                        'created_at': format_datetime(user.last_login, 'default') if user.last_login else format_datetime(user.created_at, 'default'),
                        'icon': 'fa-sign-in-alt',
                        'color': 'success'
                    },
                    {
                        'title': 'Akun dibuat',
                        'description': 'Pengguna mendaftar ke sistem',
                        'created_at': format_datetime(user.created_at, 'default'),
                        'icon': 'fa-user-plus',
                        'color': 'info'
                    }
                ]
            
            return jsonify({
                'id': user.id,
                'username': user.username,
                'email': user.email,
                'role': user.role,
                'is_active': user.is_active,
                'created_at': format_datetime(user.created_at, 'default'),
            'last_login': format_datetime(user.last_login, 'default') if user.last_login else None,
                'stats': {
                    'total_uploads': total_uploads,
                    'total_scraping': total_scraping,
                    'total_classifications': total_classifications
                },
                'recent_activities': recent_activities
            })
        
        except Exception as e:
            return jsonify({'success': False, 'message': f'Error: {str(e)}'}), 500
    
    @app.route('/api/admin/users/<int:user_id>', methods=['PUT'])
    @login_required
    @admin_required
    def update_user(user_id):
        """Update user"""
        try:
            user = User.query.get_or_404(user_id)
            
            # Prevent admin from editing their own account
            if user.id == current_user.id:
                return jsonify({'success': False, 'message': 'Tidak dapat mengedit akun sendiri'}), 400
            
            username = request.form.get('username')
            email = request.form.get('email')
            password = request.form.get('password')
            role = request.form.get('role')
            is_active = request.form.get('is_active') == 'true'
            
            # Validate input
            if not username or not email:
                return jsonify({'success': False, 'message': 'Username dan email wajib diisi'}), 400
            
            # Check if username or email already exists (excluding current user)
            if User.query.filter(User.username == username, User.id != user_id).first():
                return jsonify({'success': False, 'message': 'Username sudah digunakan'}), 400
            
            if User.query.filter(User.email == email, User.id != user_id).first():
                return jsonify({'success': False, 'message': 'Email sudah digunakan'}), 400
            
            # Update user
            user.username = username
            user.email = email
            user.role = role
            user.is_active = is_active
            
            if password:
                user.password_hash = generate_password_hash(password)
            
            db.session.commit()
            
            return jsonify({'success': True, 'message': 'Pengguna berhasil diperbarui'})
        
        except Exception as e:
            db.session.rollback()
            return jsonify({'success': False, 'message': f'Error: {str(e)}'}), 500
    
    @app.route('/api/admin/users/<int:user_id>/toggle-status', methods=['POST'])
    @login_required
    @admin_required
    def toggle_user_status(user_id):
        """Toggle user active status"""
        try:
            user = User.query.get_or_404(user_id)
            
            # Prevent admin from deactivating their own account
            if user.id == current_user.id:
                return jsonify({'success': False, 'message': 'Tidak dapat mengubah status akun sendiri'}), 400
            
            is_active = request.form.get('is_active') == 'true'
            user.is_active = is_active
            
            db.session.commit()
            
            status_text = 'diaktifkan' if is_active else 'dinonaktifkan'
            return jsonify({'success': True, 'message': f'Pengguna berhasil {status_text}'})
        
        except Exception as e:
            db.session.rollback()
            return jsonify({'success': False, 'message': f'Error: {str(e)}'}), 500
    
    @app.route('/api/admin/users/<int:user_id>', methods=['DELETE'])
    @login_required
    @admin_required
    def delete_user(user_id):
        """Delete user"""
        try:
            user = User.query.get_or_404(user_id)
            
            # Prevent admin from deleting their own account
            if user.id == current_user.id:
                return jsonify({'success': False, 'message': 'Tidak dapat menghapus akun sendiri'}), 400
            
            # Delete related data first using subqueries to avoid JOIN issues
            # Delete classification results (using clean data IDs)
            db.session.execute(text("""
                DELETE FROM classification_results 
                WHERE data_type = 'upload' AND data_id IN (
                    SELECT cdu.id FROM clean_data_upload cdu 
                    WHERE cdu.raw_data_id IN (
                        SELECT rd.id FROM raw_data rd WHERE rd.uploaded_by = :user_id
                    )
                )
            """), {'user_id': user_id})
            
            db.session.execute(text("""
                DELETE FROM classification_results 
                WHERE data_type = 'scraper' AND data_id IN (
                    SELECT cds.id FROM clean_data_scraper cds 
                    WHERE cds.raw_data_scraper_id IN (
                        SELECT rds.id FROM raw_data_scraper rds WHERE rds.scraped_by = :user_id
                    )
                )
            """), {'user_id': user_id})
            
            # Delete clean data using subqueries
            db.session.execute(text("""
                DELETE FROM clean_data_upload 
                WHERE raw_data_id IN (
                    SELECT id FROM raw_data WHERE uploaded_by = :user_id
                )
            """), {'user_id': user_id})
            
            db.session.execute(text("""
                DELETE FROM clean_data_scraper 
                WHERE raw_data_scraper_id IN (
                    SELECT id FROM raw_data_scraper WHERE scraped_by = :user_id
                )
            """), {'user_id': user_id})
            
            # Delete raw data
            RawData.query.filter_by(uploaded_by=user_id).delete()
            RawDataScraper.query.filter_by(scraped_by=user_id).delete()
            
            # Delete user activities
            from models import UserActivity
            UserActivity.query.filter_by(user_id=user_id).delete()
            
            # Delete datasets created by user
            Dataset.query.filter_by(uploaded_by=user_id).delete()
            
            # Delete user
            db.session.delete(user)
            db.session.commit()
            
            return jsonify({'success': True, 'message': 'Pengguna berhasil dihapus'})
        
        except Exception as e:
            db.session.rollback()
            return jsonify({'success': False, 'message': f'Error: {str(e)}'}), 500

    # API Endpoints for external access (CSRF exempt)
    @app.route('/api/v1/scraping/start', methods=['POST'])
    @csrf.exempt
    def api_start_scraping():
        """API endpoint for starting scraping process - CSRF exempt for external API access"""
        try:
            # Check for API key authentication (optional - implement if needed)
            api_key = request.headers.get('X-API-Key')
            if not api_key:
                return jsonify({'success': False, 'message': 'API key required'}), 401
            
            # Validate API key (you can implement your own validation logic)
            # For now, we'll use a simple check against environment variable
            expected_api_key = os.getenv('WASKITA_API_KEY')
            if expected_api_key and api_key != expected_api_key:
                return jsonify({'success': False, 'message': 'Invalid API key'}), 401
            
            # Get JSON data
            data = request.get_json()
            if not data:
                return jsonify({'success': False, 'message': 'No JSON data provided'}), 400
            
            # Validate required fields
            required_fields = ['platform', 'keywords']
            for field in required_fields:
                if field not in data:
                    return jsonify({'success': False, 'message': f'Missing required field: {field}'}), 400
            
            platform = data.get('platform')
            keywords = data.get('keywords')
            start_date = data.get('start_date')
            end_date = data.get('end_date')
            max_results = data.get('max_results', 100)
            
            # Validate platform
            valid_platforms = ['twitter', 'facebook', 'instagram', 'tiktok']
            if platform not in valid_platforms:
                return jsonify({'success': False, 'message': f'Invalid platform. Must be one of: {", ".join(valid_platforms)}'}), 400
            
            # Create a system user for API requests (or use a specific API user)
            api_user_id = 1  # Assuming admin user ID is 1, or create a dedicated API user
            
            # Generate unique job ID
            job_id = str(uuid.uuid4())
            
            # Start scraping process
            processed_results, run_id = scrape_with_apify(
                platform=platform,
                keyword=keywords,
                date_from=start_date,
                date_to=end_date,
                max_results=max_results
            )
            
            return jsonify({
                'success': True,
                'message': 'Scraping started successfully',
                'job_id': job_id,
                'run_id': run_id,
                'platform': platform,
                'keywords': keywords,
                'max_results': max_results,
                'results_count': len(processed_results) if processed_results else 0,
                'preview_data': processed_results[:3] if processed_results else []  # Return first 3 results as preview
            })
                
        except Exception as e:
            return jsonify({'success': False, 'message': f'Error: {str(e)}'}), 500

    @app.route('/api/v1/scraping/progress/<run_id>', methods=['GET'])
    @csrf.exempt
    def api_get_scraping_progress(run_id):
        """API endpoint for getting scraping progress - CSRF exempt for external API access"""
        try:
            # Check for API key authentication
            api_key = request.headers.get('X-API-Key')
            if not api_key:
                return jsonify({'success': False, 'message': 'API key required'}), 401
            
            # Validate API key
            expected_api_key = os.getenv('WASKITA_API_KEY')
            if expected_api_key and api_key != expected_api_key:
                return jsonify({'success': False, 'message': 'Invalid API key'}), 401
            
            from utils import get_apify_run_progress
            
            # Get progress information from Apify API
            progress_info = get_apify_run_progress(run_id)
            
            # Add user-friendly status messages
            status_messages = {
                'READY': 'Mempersiapkan scraping...',
                'RUNNING': 'Sedang melakukan scraping data...',
                'SUCCEEDED': 'Scraping berhasil diselesaikan!',
                'FAILED': 'Scraping gagal, silakan coba lagi.',
                'ABORTED': 'Scraping dibatalkan.',
                'TIMED-OUT': 'Scraping timeout, waktu habis.',
                'ERROR': 'Terjadi kesalahan saat mengecek progress.'
            }
            
            progress_info['status_message'] = status_messages.get(
                progress_info['status'], 
                'Status tidak diketahui'
            )
            
            # Format time remaining
            if progress_info.get('estimated_time_remaining'):
                remaining_seconds = int(progress_info['estimated_time_remaining'])
                if remaining_seconds > 60:
                    minutes = remaining_seconds // 60
                    seconds = remaining_seconds % 60
                    progress_info['time_remaining_formatted'] = f"{minutes}m {seconds}s"
                else:
                    progress_info['time_remaining_formatted'] = f"{remaining_seconds}s"
            
            return jsonify({
                'success': True,
                'progress': progress_info
            })
            
        except Exception as e:
            return jsonify({
                'success': False,
                'message': f'Error getting progress: {str(e)}',
                'progress': {
                    'run_id': run_id,
                    'status': 'ERROR',
                    'progress_percentage': 0,
                    'status_message': 'Terjadi kesalahan saat mengecek progress.',
                    'error': str(e)
                }
            }), 500

    # Health Check API Endpoint
    @app.route('/api/health', methods=['GET'])
    def api_health():
        """
        Health check endpoint to verify if the application is running
        """
        try:
            # Test database connection
            db.session.execute(text('SELECT 1'))
            db_status = 'healthy'
        except Exception as e:
            db_status = f'unhealthy: {str(e)}'
        
        # Check if models are loaded
        models_status = 'loaded' if hasattr(app, 'models_loaded') and app.models_loaded else 'not_loaded'
        
        health_data = {
            'status': 'healthy' if db_status == 'healthy' else 'unhealthy',
            'timestamp': datetime.now().isoformat(),
            'version': '1.0.0',
            'database': db_status,
            'models': models_status,
            'uptime': str(datetime.now() - app.start_time) if hasattr(app, 'start_time') else 'unknown'
        }
        
        status_code = 200 if health_data['status'] == 'healthy' else 503
        return jsonify(health_data), status_code

    # Status API Endpoint
    @app.route('/api/status', methods=['GET'])
    def api_status():
        """
        Detailed status endpoint with application statistics
        """
        try:
            # Get database statistics
            total_users = User.query.count()
            active_users = User.query.filter_by(is_active=True).count()
            inactive_users = User.query.filter_by(is_active=False).count()
            
            # Get data statistics
            total_raw_data = RawData.query.count()
            total_scraper_data = RawDataScraper.query.count()
            total_classifications = ClassificationResult.query.count()
            
            # Get recent activity count (last 24 hours)
            from datetime import timedelta
            yesterday = datetime.now() - timedelta(days=1)
            recent_uploads = RawData.query.filter(RawData.created_at >= yesterday).count()
            recent_scraping = RawDataScraper.query.filter(RawDataScraper.created_at >= yesterday).count()
            recent_classifications = ClassificationResult.query.filter(ClassificationResult.created_at >= yesterday).count()
            
            status_data = {
                'application': {
                    'name': 'Waskita',
                    'version': '1.0.0',
                    'status': 'running',
                    'timestamp': datetime.now().isoformat()
                },
                'database': {
                    'status': 'connected',
                    'total_users': total_users,
                    'active_users': active_users,
                    'inactive_users': inactive_users
                },
                'data_statistics': {
                    'total_raw_data': total_raw_data,
                    'total_scraper_data': total_scraper_data,
                    'total_classifications': total_classifications
                },
                'recent_activity': {
                    'period': '24_hours',
                    'uploads': recent_uploads,
                    'scraping': recent_scraping,
                    'classifications': recent_classifications
                },
                'system': {
                    'models_loaded': hasattr(app, 'models_loaded') and app.models_loaded,
                    'email_service': 'configured' if app.config.get('MAIL_SERVER') else 'not_configured',
                    'scheduler_active': hasattr(app, 'scheduler') and app.scheduler.running if hasattr(app, 'scheduler') else False
                }
            }
            
            return jsonify(status_data), 200
            
        except Exception as e:
            error_data = {
                'application': {
                    'name': 'Waskita',
                    'version': '1.0.0',
                    'status': 'error',
                    'timestamp': datetime.now().isoformat()
                },
                'error': {
                    'message': str(e),
                    'type': type(e).__name__
                }
            }
            return jsonify(error_data), 500

    @app.route('/api/datasets/for-classification', methods=['GET'])
    @login_required
    def get_datasets_for_classification():
        """Get datasets that have unclassified clean data"""
        try:
            # Get all datasets with their statistics
            datasets_query = text("""
                WITH dataset_stats AS (
                    SELECT 
                        d.id,
                        d.name,
                        d.created_at,
                        u.username as created_by,
                        -- Count total data (raw + scraper)
                        COALESCE(rd_count.total, 0) + COALESCE(rs_count.total, 0) as total_data,
                        -- Count clean data
                        COALESCE(cd_count.total, 0) + COALESCE(cs_count.total, 0) as clean_data,
                        -- Count classified data
                        COALESCE(classified_upload.total, 0) + COALESCE(classified_scraper.total, 0) as classified_data
                    FROM datasets d
                    LEFT JOIN users u ON d.uploaded_by = u.id
                    -- Raw data upload count
                    LEFT JOIN (
                        SELECT dataset_id, COUNT(*) as total 
                        FROM raw_data 
                        GROUP BY dataset_id
                    ) rd_count ON d.id = rd_count.dataset_id
                    -- Raw scraper count
                    LEFT JOIN (
                        SELECT dataset_id, COUNT(*) as total 
                        FROM raw_data_scraper 
                        GROUP BY dataset_id
                    ) rs_count ON d.id = rs_count.dataset_id
                    -- Clean data upload count
                    LEFT JOIN (
                        SELECT rd.dataset_id, COUNT(*) as total 
                        FROM clean_data_upload cdu
                        JOIN raw_data rd ON cdu.raw_data_id = rd.id
                        GROUP BY rd.dataset_id
                    ) cd_count ON d.id = cd_count.dataset_id
                    -- Clean scraper count
                    LEFT JOIN (
                        SELECT rs.dataset_id, COUNT(*) as total 
                        FROM clean_data_scraper cds
                        JOIN raw_data_scraper rs ON cds.raw_data_scraper_id = rs.id
                        GROUP BY rs.dataset_id
                    ) cs_count ON d.id = cs_count.dataset_id
                    -- Classified upload count
                    LEFT JOIN (
                        SELECT rd.dataset_id, COUNT(DISTINCT cr.data_id) as total
                        FROM classification_results cr
                        JOIN clean_data_upload cdu ON cr.data_id = cdu.id AND cr.data_type = 'upload'
                        JOIN raw_data rd ON cdu.raw_data_id = rd.id
                        GROUP BY rd.dataset_id
                    ) classified_upload ON d.id = classified_upload.dataset_id
                    -- Classified scraper count
                    LEFT JOIN (
                        SELECT rs.dataset_id, COUNT(DISTINCT cr.data_id) as total
                        FROM classification_results cr
                        JOIN clean_data_scraper cds ON cr.data_id = cds.id AND cr.data_type = 'scraper'
                        JOIN raw_data_scraper rs ON cds.raw_data_scraper_id = rs.id
                        GROUP BY rs.dataset_id
                    ) classified_scraper ON d.id = classified_scraper.dataset_id
                )
                SELECT 
                    id,
                    name,
                    created_at,
                    created_by,
                    total_data,
                    clean_data,
                    classified_data,
                    (clean_data - classified_data) as unclassified_data
                FROM dataset_stats
                WHERE clean_data > 0 AND (clean_data - classified_data) > 0
                ORDER BY created_at DESC
            """)
            
            if not current_user.is_admin():
                datasets_query = text("""
                    WITH dataset_stats AS (
                        SELECT 
                            d.id,
                            d.name,
                            d.created_at,
                            u.username as created_by,
                            -- Count total data (raw + scraper)
                            COALESCE(rd_count.total, 0) + COALESCE(rs_count.total, 0) as total_data,
                            -- Count clean data
                            COALESCE(cd_count.total, 0) + COALESCE(cs_count.total, 0) as clean_data,
                            -- Count classified data
                            COALESCE(classified_upload.total, 0) + COALESCE(classified_scraper.total, 0) as classified_data
                        FROM datasets d
                        LEFT JOIN users u ON d.uploaded_by = u.id
                        -- Raw data upload count
                        LEFT JOIN (
                            SELECT dataset_id, COUNT(*) as total 
                            FROM raw_data 
                            WHERE uploaded_by = :user_id
                            GROUP BY dataset_id
                        ) rd_count ON d.id = rd_count.dataset_id
                        -- Raw scraper count
                        LEFT JOIN (
                            SELECT dataset_id, COUNT(*) as total 
                            FROM raw_data_scraper 
                            WHERE scraped_by = :user_id
                            GROUP BY dataset_id
                        ) rs_count ON d.id = rs_count.dataset_id
                        -- Clean data upload count
                        LEFT JOIN (
                            SELECT rd.dataset_id, COUNT(*) as total 
                            FROM clean_data_upload cdu
                            JOIN raw_data rd ON cdu.raw_data_id = rd.id
                            WHERE rd.uploaded_by = :user_id
                            GROUP BY rd.dataset_id
                        ) cd_count ON d.id = cd_count.dataset_id
                        -- Clean scraper count
                        LEFT JOIN (
                            SELECT rs.dataset_id, COUNT(*) as total 
                            FROM clean_data_scraper cds
                            JOIN raw_data_scraper rs ON cds.raw_data_scraper_id = rs.id
                            WHERE rs.scraped_by = :user_id
                            GROUP BY rs.dataset_id
                        ) cs_count ON d.id = cs_count.dataset_id
                        -- Classified upload count
                        LEFT JOIN (
                            SELECT rd.dataset_id, COUNT(DISTINCT cr.data_id) as total
                            FROM classification_results cr
                            JOIN clean_data_upload cdu ON cr.data_id = cdu.id AND cr.data_type = 'upload'
                            JOIN raw_data rd ON cdu.raw_data_id = rd.id
                            WHERE rd.uploaded_by = :user_id
                            GROUP BY rd.dataset_id
                        ) classified_upload ON d.id = classified_upload.dataset_id
                        -- Classified scraper count
                        LEFT JOIN (
                            SELECT rs.dataset_id, COUNT(DISTINCT cr.data_id) as total
                            FROM classification_results cr
                            JOIN clean_data_scraper cds ON cr.data_id = cds.id AND cr.data_type = 'scraper'
                            JOIN raw_data_scraper rs ON cds.raw_data_scraper_id = rs.id
                            WHERE rs.scraped_by = :user_id
                            GROUP BY rs.dataset_id
                        ) classified_scraper ON d.id = classified_scraper.dataset_id
                    )
                    SELECT 
                        id,
                        name,
                        created_at,
                        created_by,
                        total_data,
                        clean_data,
                        classified_data,
                        (clean_data - classified_data) as unclassified_data
                    FROM dataset_stats
                    WHERE clean_data > 0 AND (clean_data - classified_data) > 0
                    ORDER BY created_at DESC
                """)
                
                result = db.session.execute(datasets_query, {'user_id': current_user.id})
            else:
                result = db.session.execute(datasets_query)
            
            datasets = []
            for row in result:
                datasets.append({
                    'id': row.id,
                    'name': row.name,
                    'created_at': row.created_at.strftime('%d/%m/%Y %H:%M') if row.created_at else None,
                    'created_by': row.created_by,
                    'total_data': row.total_data or 0,
                    'clean_data': row.clean_data or 0,
                    'classified_data': row.classified_data or 0,
                    'unclassified_data': row.unclassified_data or 0
                })
            
            return jsonify({
                'success': True,
                'datasets': datasets
            })
            
        except Exception as e:
            return jsonify({
                'success': False,
                'message': f'Error loading datasets: {str(e)}'
            }), 500
    @app.route('/api/dataset/<int:dataset_id>/clean-data', methods=['GET'])
    @login_required
    def get_dataset_clean_data(dataset_id):
        """Get clean data from a specific dataset for classification"""
        try:
            app.logger.info(f"Getting clean data for dataset_id: {dataset_id}")
            
            # Check if dataset exists and user has access
            dataset = Dataset.query.get(dataset_id)
            if not dataset:
                app.logger.warning(f"Dataset {dataset_id} not found")
                return jsonify({'success': False, 'message': 'Dataset tidak ditemukan'}), 404
                
            app.logger.info(f"Dataset found: {dataset.name}, uploaded_by: {dataset.uploaded_by}, current_user: {current_user.id}")
                
            # Check permission dengan feedback yang jelas
            has_permission, message, http_status = check_permission_with_feedback(
                current_user, dataset.uploaded_by, 'view', 'clean data'
            )
            if not has_permission:
                app.logger.warning(f"User {current_user.id} doesn't have access to dataset {dataset_id}: {message}")
                return jsonify({'success': False, 'message': message}), http_status
            
            # Get clean data from upload
            clean_upload_query = text("""
                SELECT 
                    cdu.id, 
                    'upload' as data_type,
                    cdu.username, 
                    cdu.cleaned_content, 
                    cdu.url,
                    cdu.created_at
                FROM clean_data_upload cdu
                JOIN raw_data rd ON cdu.raw_data_id = rd.id
                LEFT JOIN classification_results cr ON cr.data_type = 'upload' AND cr.data_id = cdu.id
                WHERE rd.dataset_id = :dataset_id AND cr.id IS NULL
                ORDER BY cdu.created_at DESC
            """)
            
            # Get clean data from scraper
            clean_scraper_query = text("""
                SELECT 
                    cds.id, 
                    'scraper' as data_type,
                    cds.username, 
                    cds.cleaned_content, 
                    cds.url,
                    cds.created_at
                FROM clean_data_scraper cds
                JOIN raw_data_scraper rds ON cds.raw_data_scraper_id = rds.id
                LEFT JOIN classification_results cr ON cr.data_type = 'scraper' AND cr.data_id = cds.id
                WHERE rds.dataset_id = :dataset_id AND cr.id IS NULL
                ORDER BY cds.created_at DESC
            """)
            
            clean_upload_data = db.session.execute(clean_upload_query, {'dataset_id': dataset_id}).fetchall()
            clean_scraper_data = db.session.execute(clean_scraper_query, {'dataset_id': dataset_id}).fetchall()
            
            # Combine and format data
            clean_data = []
            
            for data in clean_upload_data:
                clean_data.append({
                    'id': data.id,
                    'data_type': data.data_type,
                    'username': data.username or '-',
                    'content': data.cleaned_content[:200] + ('...' if data.cleaned_content and len(data.cleaned_content) > 200 else ''),
                    'full_content': data.cleaned_content,
                    'url': data.url or '-',
                    'created_at': data.created_at.strftime('%d/%m/%Y %H:%M') if data.created_at else '-'
                })
                
            for data in clean_scraper_data:
                clean_data.append({
                    'id': data.id,
                    'data_type': data.data_type,
                    'username': data.username or '-',
                    'content': data.cleaned_content[:200] + ('...' if data.cleaned_content and len(data.cleaned_content) > 200 else ''),
                    'full_content': data.cleaned_content,
                    'url': data.url or '-',
                    'created_at': data.created_at.strftime('%d/%m/%Y %H:%M') if data.created_at else '-'
                })
            
            # Get platforms from the data
            platforms = set()
            for item in clean_data:
                if 'platform' in item:
                    platforms.add(item['platform'])
            
            return jsonify({
                'success': True,
                'dataset': {
                    'id': dataset.id,
                    'name': dataset.name,
                    'platforms': list(platforms) if platforms else ['unknown']
                },
                'data': clean_data,
                'total_items': len(clean_data)
            })
            
        except Exception as e:
            app.logger.error(f"Error in get_dataset_clean_data for dataset {dataset_id}: {str(e)}")
            app.logger.error(f"Exception type: {type(e).__name__}")
            import traceback
            app.logger.error(f"Traceback: {traceback.format_exc()}")
            return jsonify({
                'success': False,
                'message': f'Error loading clean data: {str(e)}'
            }), 500