from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, current_app, send_file
from flask_login import login_required, current_user
from sqlalchemy import desc, func
from models.models import db, RawData, RawDataScraper, DatasetStatistics, CleanDataUpload, CleanDataScraper, ClassificationResult, UserActivity
from utils.utils import active_user_required, format_datetime
from datetime import datetime, timedelta
import calendar

main_bp = Blueprint('main', __name__)

class StatsDTO:
    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)

def get_current_user_stats(user):
    """Calculate stats dynamically for the current user"""
    if user.is_admin():
        # Count all
        total_raw_upload = RawData.query.filter(RawData.dataset_id.isnot(None)).count()
        total_raw_scraper = RawDataScraper.query.filter(RawDataScraper.dataset_id.isnot(None)).count()
        
        # Clean data
        total_clean_upload = CleanDataUpload.query.join(RawData).filter(RawData.dataset_id.isnot(None)).count()
        total_clean_scraper = CleanDataScraper.query.join(RawDataScraper).filter(RawDataScraper.dataset_id.isnot(None)).count()
        
        # Classification
        total_classified = ClassificationResult.query.count()
        total_radikal = ClassificationResult.query.filter(func.lower(ClassificationResult.prediction) == 'radikal').count()
        total_non_radikal = ClassificationResult.query.filter(func.lower(ClassificationResult.prediction) == 'non-radikal').count()
    else:
        # Count user specific
        total_raw_upload = RawData.query.filter_by(uploaded_by=user.id).filter(RawData.dataset_id.isnot(None)).count()
        total_raw_scraper = RawDataScraper.query.filter_by(scraped_by=user.id).filter(RawDataScraper.dataset_id.isnot(None)).count()
        
        # Clean data
        total_clean_upload = CleanDataUpload.query.filter_by(cleaned_by=user.id).count()
        total_clean_scraper = CleanDataScraper.query.filter_by(cleaned_by=user.id).count()
        
        # Classification
        total_classified = ClassificationResult.query.filter_by(classified_by=user.id).count()
        total_radikal = ClassificationResult.query.filter_by(classified_by=user.id).filter(func.lower(ClassificationResult.prediction) == 'radikal').count()
        total_non_radikal = ClassificationResult.query.filter_by(classified_by=user.id).filter(func.lower(ClassificationResult.prediction) == 'non-radikal').count()
        
    return StatsDTO(
        total_raw_upload=total_raw_upload,
        total_raw_scraper=total_raw_scraper,
        total_clean_upload=total_clean_upload,
        total_clean_scraper=total_clean_scraper,
        total_classified=total_classified,
        total_radikal=total_radikal,
        total_non_radikal=total_non_radikal
    )

@main_bp.route('/')
def index():
    if current_user.is_authenticated:
        return redirect(url_for('main.dashboard'))
    return redirect(url_for('auth.login'))

@main_bp.route('/health')
def health_check():
    return jsonify({'status': 'healthy'}), 200

@main_bp.route('/dashboard')
@login_required
@active_user_required
def dashboard():
    # Get statistics
    stats = get_current_user_stats(current_user)
    
    # Get recent activities
    if current_user.is_admin():
        recent_activities = UserActivity.query.order_by(desc(UserActivity.created_at)).limit(10).all()
    else:
        recent_activities = UserActivity.query.filter_by(user_id=current_user.id).order_by(desc(UserActivity.created_at)).limit(10).all()
    
    # Format activities for display
    formatted_activities = []
    for activity in recent_activities:
        formatted_activities.append({
            'icon': activity.icon,
            'color': activity.color,
            'title': activity.action.replace('_', ' ').title(),
            'time': format_datetime(activity.created_at),
            'description': activity.description,
            'date': format_datetime(activity.created_at, '%d %b %Y')
        })
        
    # Get platform stats
    platform_stats = {}
    if current_user.is_admin():
        platform_stats = {
            'twitter_scraper': RawDataScraper.query.filter(func.lower(RawDataScraper.platform) == 'twitter', RawDataScraper.dataset_id.isnot(None)).count(),
            'tiktok_scraper': RawDataScraper.query.filter(func.lower(RawDataScraper.platform) == 'tiktok', RawDataScraper.dataset_id.isnot(None)).count(),
            'facebook_scraper': RawDataScraper.query.filter(func.lower(RawDataScraper.platform) == 'facebook', RawDataScraper.dataset_id.isnot(None)).count(),
            'total_upload': RawData.query.filter(RawData.dataset_id.isnot(None)).count()
        }
    else:
        platform_stats = {
            'twitter_scraper': RawDataScraper.query.filter(func.lower(RawDataScraper.platform) == 'twitter', RawDataScraper.scraped_by == current_user.id, RawDataScraper.dataset_id.isnot(None)).count(),
            'tiktok_scraper': RawDataScraper.query.filter(func.lower(RawDataScraper.platform) == 'tiktok', RawDataScraper.scraped_by == current_user.id, RawDataScraper.dataset_id.isnot(None)).count(),
            'facebook_scraper': RawDataScraper.query.filter(func.lower(RawDataScraper.platform) == 'facebook', RawDataScraper.scraped_by == current_user.id, RawDataScraper.dataset_id.isnot(None)).count(),
            'total_upload': RawData.query.filter(RawData.uploaded_by == current_user.id, RawData.dataset_id.isnot(None)).count()
        }
        
    # Check model status
    word2vec_model = current_app.config.get('WORD2VEC_MODEL')
    classification_models = current_app.config.get('CLASSIFICATION_MODELS', {})
    
    model_status = {
        'word2vec': 'Loaded' if word2vec_model else 'Not Loaded',
        'active_models_count': len([m for m in classification_models.values() if m is not None]),
        'database': 'Connected'
    }
    
    return render_template('dashboard.html', 
                         stats=stats, 
                         recent_activities=formatted_activities,
                         model_status=model_status,
                         platform_stats=platform_stats)

@main_bp.route('/profile')
@login_required
def profile():
    # Get basic stats using existing function
    stats = get_current_user_stats(current_user)
    
    # Map to what profile.html expects
    user_stats = {
        'total_uploads': stats.total_raw_upload + stats.total_raw_scraper,
        'manual_uploads': stats.total_raw_upload,
        'scraping_count': stats.total_raw_scraper,
        'cleaned_data': stats.total_clean_upload + stats.total_clean_scraper,
        'total_processed': stats.total_clean_upload + stats.total_clean_scraper, # Assuming processed means cleaned
        'total_classifications': stats.total_classified
    }
    
    # Get recent activities
    if current_user.is_admin():
        recent_activities = UserActivity.query.order_by(desc(UserActivity.created_at)).limit(5).all()
        all_activities_query = UserActivity.query
    else:
        recent_activities = UserActivity.query.filter_by(user_id=current_user.id).order_by(desc(UserActivity.created_at)).limit(5).all()
        all_activities_query = UserActivity.query.filter_by(user_id=current_user.id)
        
    formatted_activities = []
    for activity in recent_activities:
        formatted_activities.append({
            'icon': activity.icon,
            'color': activity.color,
            'title': activity.action.replace('_', ' ').title(),
            'time': format_datetime(activity.created_at),
            'description': activity.description,
            'date': format_datetime(activity.created_at, '%d %b %Y'),
            'type_color': activity.color # profile.html uses type_color
        })

    # Calculate Activity Statistics for Chart (Last 6 Months)
    end_date = datetime.utcnow()
    start_date = end_date - timedelta(days=180)
    
    activities_stats = all_activities_query.filter(UserActivity.created_at >= start_date).all()
    
    # Initialize buckets for last 6 months
    monthly_stats = {}
    for i in range(6):
        date = end_date - timedelta(days=30 * i)
        month_key = date.strftime('%b') # Jan, Feb, etc.
        monthly_stats[month_key] = {
            'upload': 0,
            'scraping': 0, 
            'cleaning': 0,
            'classification': 0
        }
    
    # Reverse to have chronological order (oldest to newest)
    month_labels = list(monthly_stats.keys())[::-1]
    
    # Fill with data
    for act in activities_stats:
        month_key = act.created_at.strftime('%b')
        if month_key in monthly_stats:
            action = act.action.lower()
            if 'upload' in action:
                monthly_stats[month_key]['upload'] += 1
            elif 'scraping' in action:
                monthly_stats[month_key]['scraping'] += 1
            elif 'cleaning' in action:
                monthly_stats[month_key]['cleaning'] += 1
            elif 'classification' in action:
                monthly_stats[month_key]['classification'] += 1
                
    # Prepare chart data
    upload_data = [monthly_stats[m]['upload'] for m in month_labels]
    scraping_data = [monthly_stats[m]['scraping'] for m in month_labels]
    cleaning_data = [monthly_stats[m]['cleaning'] for m in month_labels]
    classification_data = [monthly_stats[m]['classification'] for m in month_labels]
    
    activity_chart_data = {
        'labels': month_labels,
        'datasets': [
            {
                'label': 'Upload',
                'data': upload_data,
                'borderColor': '#007bff', # Primary
                'backgroundColor': 'rgba(0, 123, 255, 0.1)',
                'tension': 0.4
            },
            {
                'label': 'Scraping',
                'data': scraping_data,
                'borderColor': '#17c1e8', # Info
                'backgroundColor': 'rgba(23, 193, 232, 0.1)',
                'tension': 0.4
            },
            {
                'label': 'Cleaning',
                'data': cleaning_data,
                'borderColor': '#ffc107', # Warning
                'backgroundColor': 'rgba(255, 193, 7, 0.1)',
                'tension': 0.4
            },
            {
                'label': 'Classification',
                'data': classification_data,
                'borderColor': '#82d616', # Success
                'backgroundColor': 'rgba(130, 214, 22, 0.1)',
                'tension': 0.4
            }
        ]
    }

    return render_template('profile.html',
                          user_stats=user_stats,
                          recent_activities=formatted_activities,
                          activity_chart_data=activity_chart_data)

@main_bp.route('/dashboard/stats')
@login_required
def dashboard_stats():
    try:
        stats = get_current_user_stats(current_user)
        
        total_raw_upload = stats.total_raw_upload
        total_raw_scraper = stats.total_raw_scraper
        total_clean_upload = stats.total_clean_upload
        total_clean_scraper = stats.total_clean_scraper
        total_classified = stats.total_classified
        total_radikal = stats.total_radikal
        total_non_radikal = stats.total_non_radikal

        platform_stats = {}
        if current_user.is_admin():
            platform_stats = {
                'twitter_scraper': RawDataScraper.query.filter_by(platform='twitter').filter(RawDataScraper.dataset_id.isnot(None)).count(),
                'tiktok_scraper': RawDataScraper.query.filter_by(platform='tiktok').filter(RawDataScraper.dataset_id.isnot(None)).count(),
                'facebook_scraper': RawDataScraper.query.filter_by(platform='facebook').filter(RawDataScraper.dataset_id.isnot(None)).count(),
                'total_upload': RawData.query.filter(RawData.dataset_id.isnot(None)).count()
            }
        else:
            platform_stats = {
                'twitter_scraper': RawDataScraper.query.filter_by(platform='twitter', scraped_by=current_user.id).filter(RawDataScraper.dataset_id.isnot(None)).count(),
                'tiktok_scraper': RawDataScraper.query.filter_by(platform='tiktok', scraped_by=current_user.id).filter(RawDataScraper.dataset_id.isnot(None)).count(),
                'facebook_scraper': RawDataScraper.query.filter_by(platform='facebook', scraped_by=current_user.id).filter(RawDataScraper.dataset_id.isnot(None)).count(),
                'total_upload': RawData.query.filter(RawData.uploaded_by == current_user.id, RawData.dataset_id.isnot(None)).count()
            }
        
        radikal_percentage = 0
        non_radikal_percentage = 0
        if total_classified > 0:
            radikal_percentage = (total_radikal / total_classified) * 100
            non_radikal_percentage = (total_non_radikal / total_classified) * 100
        
        word2vec_model = current_app.config.get('WORD2VEC_MODEL')
        classification_models = current_app.config.get('CLASSIFICATION_MODELS', {})
        
        return jsonify({
            'success': True,
            'total_raw_upload': total_raw_upload,
            'total_raw_scraper': total_raw_scraper,
            'total_clean_upload': total_clean_upload,
            'total_clean_scraper': total_clean_scraper,
            'total_classified': total_classified,
            'total_radikal': total_radikal,
            'total_non_radikal': total_non_radikal,
            'radikal_percentage': round(radikal_percentage, 1),
            'non_radikal_percentage': round(non_radikal_percentage, 1),
            'platform_stats': platform_stats,
            'model_status': {
                'word2vec': 'Loaded' if word2vec_model else 'Error',
                'naive_bayes_count': len([m for m in classification_models.values() if m is not None]),
                'database': 'Connected'
            }
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': f'Error mapping data: {str(e)}'}), 500
