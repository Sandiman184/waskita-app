from flask import Blueprint, jsonify, current_app, request
from datetime import datetime
import threading
import uuid
import pytz
from flask_login import login_required, current_user
from models.models import db, Dataset, User, RawData, RawDataScraper, CleanDataUpload, CleanDataScraper, ClassificationResult, UserActivity, ClassificationBatch
from sqlalchemy import desc, func
from services.apify_service import ApifyService
from utils.utils import get_jakarta_time, JAKARTA_TZ, admin_required, flatten_dict, generate_activity_log

api_bp = Blueprint('api', __name__)

@api_bp.route('/models-status')
def models_status():
    word2vec_model = current_app.config.get('WORD2VEC_MODEL')
    classification_models = current_app.config.get('CLASSIFICATION_MODELS', {})
    return jsonify({
        'word2vec_loaded': bool(word2vec_model),
        'classification_models_count': len([m for m in classification_models.values() if m is not None])
    })

@api_bp.route('/scraping/progress/<job_id>')
@login_required
def get_scraping_progress(job_id):
    try:
        # job_id is the Apify Run ID
        run_data = ApifyService.get_run_status(job_id)
        
        status = run_data.get('status')
        default_dataset_id = run_data.get('defaultDatasetId')
        
        # Try to extract stats
        stats = run_data.get('stats', {})
        options = run_data.get('options', {})
        
        # Calculate progress
        # If actor provides progress in meta field, use it. Otherwise guess based on status.
        progress_percentage = 0
        items_processed = 0
        
        # Try to get real item count from dataset
        if default_dataset_id:
            dataset_info = ApifyService.get_dataset_info(default_dataset_id)
            if dataset_info is not None:
                items_processed = dataset_info.get('itemCount', 0)
            else:
                # If fetching dataset info failed, fallback to requestsFinished as proxy
                items_processed = stats.get('requestsFinished', 0)
        else:
             items_processed = stats.get('requestsFinished', 0)
            
        # Try to get max items from meta_info if stored in dataset
        # But we don't have easy access to dataset object here without querying DB
        # However, we can try to guess from options or run inputs if available in run_data
        # For now, let's use a heuristic
        
        if status == 'SUCCEEDED':
            progress_percentage = 100
            # Ensure items_processed is at least requestsFinished if dataset info failed
            if items_processed == 0 and stats.get('requestsFinished', 0) > 0:
                items_processed = stats.get('requestsFinished', 0)
                
        elif status == 'RUNNING':
            # Use itemCount to estimate progress if we have a target
            # Since we don't have max_results easily available here (it's in the DB), 
            # we can either query DB or just use items_processed as a signal of life
            # Let's query the dataset to get max_results from meta_info
            # This is slightly expensive but accurate
            try:
                # Find dataset by external_id (run_id)
                dataset_record = Dataset.query.filter_by(external_id=job_id).first()
                if dataset_record and dataset_record.meta_info:
                    max_results = dataset_record.meta_info.get('max_results', 100)
                    if max_results > 0:
                        progress_percentage = min(99, int((items_processed / max_results) * 100))
                    else:
                        progress_percentage = 50 # Fallback
                else:
                    progress_percentage = 50 # Fallback
            except:
                progress_percentage = 50 # Fallback
                
            # Heuristic: if progress is 0 but we have requests finished, show at least 5%
            # Also try to estimate progress from requests if items count is lagging
            requests_finished = stats.get('requestsFinished', 0)
            
            if progress_percentage == 0 and requests_finished > 0:
                 # Try to calculate based on requests vs max_results
                 try:
                     dataset_record = Dataset.query.filter_by(external_id=job_id).first()
                     if dataset_record and dataset_record.meta_info:
                        max_results = dataset_record.meta_info.get('max_results', 100)
                        if max_results > 0:
                            progress_percentage = min(95, int((requests_finished / max_results) * 100))
                 except:
                     pass
                     
                 if progress_percentage == 0:
                    progress_percentage = 5
        elif status in ['FAILED', 'ABORTED', 'TIMED-OUT']:
            progress_percentage = 0
            
        # If finished, we can fetch columns and sample data
        sample_data = []
        columns = []
        
        # Update Dataset Record in Database to reflect real-time progress
        try:
            dataset = Dataset.query.filter_by(external_id=job_id).first()
            if dataset:
                # Update record count
                if items_processed > dataset.total_records:
                    dataset.total_records = items_processed
                
                # Update status based on Apify status
                if status == 'SUCCEEDED':
                    dataset.status = 'Raw'
                elif status in ['FAILED', 'TIMED-OUT']:
                    dataset.status = 'Failed'
                elif status == 'ABORTED':
                    dataset.status = 'Aborted'
                # If RUNNING, we leave it as is (likely 'Raw' from creation)
                
                db.session.commit()
        except Exception as db_e:
            current_app.logger.error(f"Error updating dataset progress in DB: {db_e}")

        if status == 'SUCCEEDED' and default_dataset_id:
            try:
                # Use limit=10 to fetch only a sample for column mapping and preview
                # This prevents timeouts on large datasets during progress checking
                items = ApifyService.get_dataset_items(default_dataset_id, limit=10)
                if items:
                    # Note: items_processed here is just the sample count if we used limit
                    # So we should NOT overwrite items_processed with len(items) if we used limit
                    # Use the count from dataset_info or stats instead (already calculated above)
                    
                    # Get columns from first item (flattened)
                    first_item = items[0]
                    # Deep flattening for columns using recursive function
                    flat_item = flatten_dict(first_item)
                    columns = list(flat_item.keys())
                    
                    # Flatten sample data as well for consistent preview
                    sample_data = [flatten_dict(item) for item in items[:5]]
                else:
                    # If items are empty but we expected some?
                    if items_processed > 0:
                         current_app.logger.warning(f"Apify status SUCCEEDED and items_processed={items_processed} but get_dataset_items returned empty.")
                    # Don't reset items_processed to 0 here because we might have failed to fetch sample 
                    # but we know from stats that items exist.
            except Exception as e:
                current_app.logger.error(f"Error fetching dataset items: {e}")
                # Don't fail the whole request, just return empty data
        
        return jsonify({
            'success': True,
            'data': {
                'status': status,
                'progress_percentage': progress_percentage,
                'items_processed': items_processed,
                'requests_handled': stats.get('requestsFinished', 0),
                'apify_dataset_id': default_dataset_id,
                'columns': columns,
                'sample_data': sample_data
            }
        })
    except Exception as e:
        current_app.logger.error(f"Error getting scraping progress: {str(e)}")
        return jsonify({'success': False, 'message': str(e)}), 500

@api_bp.route('/scraping/mapping-data/<dataset_id>')
@login_required
def get_scraping_mapping_data(dataset_id):
    try:
        # dataset_id might be the Apify Dataset ID (string) or Internal Dataset ID (int)
        apify_dataset_id = dataset_id
        
        # Check if it looks like an internal ID (integer)
        if str(dataset_id).isdigit():
             internal_id = int(dataset_id)
             dataset = Dataset.query.get(internal_id)
             if dataset and dataset.meta_info:
                 apify_dataset_id = dataset.meta_info.get('apify_dataset_id')
        
        if not apify_dataset_id:
             return jsonify({'success': False, 'message': 'Invalid Dataset ID'}), 400

        items = ApifyService.get_dataset_items(apify_dataset_id)
        
        sample_data = []
        columns = []
        
        if items:
            # Get columns from first item (flattened)
            first_item = items[0]
            # Deep flattening for columns using recursive function
            flat_item = flatten_dict(first_item)
            columns = list(flat_item.keys())
            
            # Flatten sample data as well for consistent preview
            sample_data = [flatten_dict(item) for item in items[:5]]
            
        return jsonify({
            'success': True,
            'columns': columns,
            'sample_data': sample_data,
            'apify_dataset_id': apify_dataset_id
        })
    except Exception as e:
        current_app.logger.error(f"Error fetching mapping data: {str(e)}")
        return jsonify({'success': False, 'message': str(e)}), 500


@api_bp.route('/scraping/history')
@login_required
def get_scraping_history():
    search = request.args.get('search', '')
    
    query = Dataset.query.filter(Dataset.name.like('Scraping%'))
    
    if not current_user.is_admin():
        query = query.filter(Dataset.uploaded_by == current_user.id)
        
    if search:
        query = query.filter(Dataset.name.ilike(f'%{search}%'))
        
    query = query.order_by(desc(Dataset.created_at))
    datasets = query.limit(20).all()
    
    # Indonesian month mapping
    MONTHS_ID = {
        1: 'Januari', 2: 'Februari', 3: 'Maret', 4: 'April', 5: 'Mei', 6: 'Juni',
        7: 'Juli', 8: 'Agustus', 9: 'September', 10: 'Oktober', 11: 'November', 12: 'Desember'
    }
    
    history = []
    for ds in datasets:
        parts = ds.name.replace('Scraping ', '').split(' - ')
        platform = parts[0] if len(parts) > 0 else 'Unknown'
        keywords = parts[1] if len(parts) > 1 else 'Unknown'
        
        dt_jakarta = None
        scraped_date_formatted = '-'
        scraped_time_formatted = '-'
        
        if ds.created_at:
            if ds.created_at.tzinfo is None:
                dt_jakarta = pytz.utc.localize(ds.created_at).astimezone(JAKARTA_TZ)
            else:
                dt_jakarta = ds.created_at.astimezone(JAKARTA_TZ)
                
            day = dt_jakarta.day
            month = MONTHS_ID.get(dt_jakarta.month, dt_jakarta.strftime('%B'))
            year = dt_jakarta.year
            scraped_date_formatted = f"{day} {month} {year}"
            scraped_time_formatted = dt_jakarta.strftime('%H:%M WIB')
        
        history.append({
            'id': ds.id,
            'platform': platform,
            'keywords': keywords,
            'created_at': dt_jakarta.strftime('%d/%m/%Y %H:%M') if dt_jakarta else '-',
            'total_records': ds.total_records,
            'results_count': ds.total_records, # Add alias to match frontend expectation
            'status': ds.status,
            'scraped_by': ds.user.username if ds.user else 'Unknown',
            'scraped_date_formatted': scraped_date_formatted,
            'scraped_time_formatted': scraped_time_formatted,
            'scraped_at': dt_jakarta.isoformat() if dt_jakarta else '-'
        })
    
    return jsonify({'success': True, 'history': history})

@api_bp.route('/profile/edit', methods=['POST'])
@login_required
def edit_profile():
    try:
        full_name = request.form.get('full_name')
        email = request.form.get('email')
        bio = request.form.get('bio')
        
        if not email:
            return jsonify({'success': False, 'message': 'Email is required'}), 400
            
        # Check if email is taken by another user
        existing_user = User.query.filter_by(email=email).first()
        if existing_user and existing_user.id != current_user.id:
            return jsonify({'success': False, 'message': 'Email already in use'}), 400
            
        current_user.full_name = full_name
        current_user.email = email
        current_user.bio = bio
        
        db.session.commit()
        
        generate_activity_log(
            action='profile_update',
            description='Updated profile information',
            user_id=current_user.id,
            icon='fa-user-edit',
            color='info'
        )
        
        return jsonify({'success': True, 'message': 'Profile updated successfully'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500

@api_bp.route('/profile/change-password', methods=['POST'])
@login_required
def change_password():
    try:
        current_password = request.form.get('current_password')
        new_password = request.form.get('new_password')
        
        if not current_password or not new_password:
            return jsonify({'success': False, 'message': 'All fields are required'}), 400
            
        if not current_user.check_password(current_password):
            return jsonify({'success': False, 'message': 'Incorrect current password'}), 400
            
        current_user.set_password(new_password)
        # current_user.password_changed_at = datetime.utcnow()
        
        db.session.commit()
        
        generate_activity_log(
            action='password_change',
            description='Changed account password',
            user_id=current_user.id,
            icon='fa-key',
            color='warning'
        )
        
        return jsonify({'success': True, 'message': 'Password changed successfully'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500

@api_bp.route('/profile/save-preferences', methods=['POST'])
@login_required
def save_preferences():
    try:
        preferences = {
            'language': request.form.get('language'),
            'timezone': request.form.get('timezone'),
            'items_per_page': request.form.get('items_per_page', type=int),
            'default_dataset': request.form.get('default_dataset'),
            'email_notifications': request.form.get('email_notifications') == 'true',
            'auto_refresh': request.form.get('auto_refresh') == 'true',
            'dark_mode': request.form.get('dark_mode') == 'true',
            'auto_classify': request.form.get('auto_classify') == 'true',
            'show_probability': request.form.get('show_probability') == 'true',
            'compact_view': request.form.get('compact_view') == 'true'
        }
        
        # Update user preferences
        # Assuming User model has a preferences field (JSON/JSONB)
        # We need to make sure we don't overwrite existing preferences that are not in the form
        # But here we seem to be sending all of them.
        
        current_prefs = current_user.get_preferences()
        current_prefs.update(preferences)
        
        # If the model field is 'preferences', we assign it back
        current_user.preferences = current_prefs
        db.session.commit()
        
        return jsonify({'success': True, 'message': 'Preferences saved successfully'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500

@api_bp.route('/scraping/abort/<job_id>', methods=['POST'])
@login_required
def abort_scraping(job_id):
    try:
        # Try to abort the Apify run
        ApifyService.abort_run(job_id)
        
        # Find the associated dataset
        dataset = Dataset.query.filter_by(external_id=job_id).first()
        
        if dataset:
            # Check if there is data in Apify
            apify_dataset_id = None
            if dataset.meta_info:
                apify_dataset_id = dataset.meta_info.get('apify_dataset_id')
            
            item_count = 0
            if apify_dataset_id:
                try:
                    # Get info to check item count without fetching all items
                    info = ApifyService.get_dataset_info(apify_dataset_id)
                    if info:
                        item_count = info.get('itemCount', 0)
                except Exception as e:
                    current_app.logger.error(f"Error checking dataset info during abort: {e}")
            
            # Update dataset with found items
            if item_count > 0:
                dataset.total_records = item_count
                dataset.status = 'Aborted' # Mark as aborted but with data
                db.session.commit()
                return jsonify({'success': True, 'message': f'Scraping aborted. Found {item_count} items.'})
            
            # If no items found, still keep the record for history, but mark as Aborted
            dataset.total_records = 0
            dataset.status = 'Aborted'
            db.session.commit()
            return jsonify({'success': True, 'message': 'Scraping process cancelled.'})
            
        return jsonify({'success': True, 'message': 'Scraping aborted'})
    except Exception as e:
        current_app.logger.error(f"Error aborting scraping: {str(e)}")
        return jsonify({'success': False, 'message': str(e)}), 500

@api_bp.route('/scraper/<int:id>/delete', methods=['DELETE'])
@login_required
def delete_scraper(id):
    try:
        dataset = Dataset.query.get(id)
        if not dataset:
            return jsonify({'success': False, 'message': 'Data scraping not found'}), 404
            
        if not current_user.is_admin() and dataset.uploaded_by != current_user.id:
            return jsonify({'success': False, 'message': 'Unauthorized'}), 403
            
        # Manual Cascade Delete
        
        # 1. Clean Data Upload & Classification Results
        clean_uploads = CleanDataUpload.query.filter_by(dataset_id=dataset.id).all()
        if clean_uploads:
            clean_upload_ids = [c.id for c in clean_uploads]
            ClassificationResult.query.filter(
                ClassificationResult.data_type == 'upload',
                ClassificationResult.data_id.in_(clean_upload_ids)
            ).delete(synchronize_session=False)
            for item in clean_uploads:
                db.session.delete(item)
            
        # 2. Clean Data Scraper & Classification Results
        clean_scrapers = CleanDataScraper.query.filter_by(dataset_id=dataset.id).all()
        if clean_scrapers:
            clean_scraper_ids = [c.id for c in clean_scrapers]
            ClassificationResult.query.filter(
                ClassificationResult.data_type == 'scraper',
                ClassificationResult.data_id.in_(clean_scraper_ids)
            ).delete(synchronize_session=False)
            for item in clean_scrapers:
                db.session.delete(item)
                
        # 3. Raw Data Scraper
        raw_scrapers = RawDataScraper.query.filter_by(dataset_id=dataset.id).all()
        for item in raw_scrapers:
            db.session.delete(item)

        # 4. Classification Batch
        ClassificationBatch.query.filter_by(dataset_id=dataset.id).delete(synchronize_session=False)
            
        # 5. Dataset
        db.session.delete(dataset)
        db.session.commit()
        
        generate_activity_log(
            action='delete',
            description=f'Deleted scraping dataset: {dataset.name}',
            user_id=current_user.id,
            icon='fa-trash',
            color='danger'
        )
        
        return jsonify({'success': True, 'message': 'Data scraping berhasil dihapus'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500

@api_bp.route('/dataset/<int:id>', methods=['DELETE'])
@login_required
def delete_dataset(id):
    try:
        dataset = Dataset.query.get(id)
        if not dataset:
            return jsonify({'success': False, 'message': 'Dataset not found'}), 404
            
        if not current_user.is_admin() and dataset.uploaded_by != current_user.id:
            return jsonify({'success': False, 'message': 'Unauthorized'}), 403
            
        # Manual Cascade Delete
        
        # 1. Clean Data Upload & Classification Results
        clean_uploads = CleanDataUpload.query.filter_by(dataset_id=dataset.id).all()
        if clean_uploads:
            clean_upload_ids = [c.id for c in clean_uploads]
            ClassificationResult.query.filter(
                ClassificationResult.data_type == 'upload',
                ClassificationResult.data_id.in_(clean_upload_ids)
            ).delete(synchronize_session=False)
            for item in clean_uploads:
                db.session.delete(item)
            
        # 2. Clean Data Scraper & Classification Results
        clean_scrapers = CleanDataScraper.query.filter_by(dataset_id=dataset.id).all()
        if clean_scrapers:
            clean_scraper_ids = [c.id for c in clean_scrapers]
            ClassificationResult.query.filter(
                ClassificationResult.data_type == 'scraper',
                ClassificationResult.data_id.in_(clean_scraper_ids)
            ).delete(synchronize_session=False)
            for item in clean_scrapers:
                db.session.delete(item)
                
        # 3. Raw Data
        raw_data = RawData.query.filter_by(dataset_id=dataset.id).all()
        for item in raw_data:
            db.session.delete(item)

        # 4. Raw Data Scraper (Safety check)
        RawDataScraper.query.filter_by(dataset_id=dataset.id).delete(synchronize_session=False)

        # 5. Classification Batch
        ClassificationBatch.query.filter_by(dataset_id=dataset.id).delete(synchronize_session=False)
            
        # 6. Dataset
        db.session.delete(dataset)
        db.session.commit()
        
        generate_activity_log(
            action='delete',
            description=f'Deleted dataset: {dataset.name}',
            user_id=current_user.id,
            icon='fa-trash',
            color='danger'
        )
        
        return jsonify({'success': True, 'message': 'Dataset berhasil dihapus'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500

@api_bp.route('/dataset/statistics')
@login_required
def dataset_statistics():
    """API endpoint for dataset statistics"""
    try:
        from models.models import DatasetStatistics
        
        # Calculate statistics manually for now or use the cached model
        # For simplicity and accuracy, let's query directly
        
        # Get all relevant datasets for the user
        query = Dataset.query
        if not current_user.is_admin():
            query = query.filter(Dataset.uploaded_by == current_user.id)
            
        datasets = query.all()
        
        # Filter raw vs clean vs classified
        raw_count = sum(1 for d in datasets if d.status == 'Mentah')
        clean_count = sum(1 for d in datasets if d.status == 'Dibersihkan')
        classified_count = sum(1 for d in datasets if d.status == 'Terklasifikasi')
        
        # Pie chart data
        pie_data = {
            'labels': ['Mentah', 'Dibersihkan', 'Terklasifikasi'],
            'values': [raw_count, clean_count, classified_count],
            'colors': ['#dc3545', '#ffc107', '#28a745']
        }
        
        # Bar chart data (top 5 platforms)
        platforms = {}
        for d in datasets:
            # Try to guess platform from name or check content
            name = d.name.lower()
            if 'twitter' in name:
                platforms['Twitter'] = platforms.get('Twitter', 0) + d.total_records
            elif 'facebook' in name:
                platforms['Facebook'] = platforms.get('Facebook', 0) + d.total_records
            elif 'instagram' in name:
                platforms['Instagram'] = platforms.get('Instagram', 0) + d.total_records
            elif 'tiktok' in name:
                platforms['TikTok'] = platforms.get('TikTok', 0) + d.total_records
            else:
                platforms['Lainnya'] = platforms.get('Lainnya', 0) + d.total_records
                
        bar_data = {
            'labels': list(platforms.keys()),
            'values': list(platforms.values())
        }
        
        data = {
            'pie_chart': pie_data,
            'bar_chart': bar_data
        }
        return jsonify({'success': True, 'data': data})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@api_bp.route('/scraping/statistics')
@login_required
def scraping_statistics():
    """API endpoint for scraping statistics"""
    try:
        query = Dataset.query.filter(Dataset.name.like('Scraping%'))
        
        if not current_user.is_admin():
            query = query.filter(Dataset.uploaded_by == current_user.id)
            
        datasets = query.all()
        total = len(datasets)
        twitter = sum(1 for ds in datasets if 'Scraping Twitter' in ds.name)
        facebook = sum(1 for ds in datasets if 'Scraping Facebook' in ds.name)
        instagram = sum(1 for ds in datasets if 'Scraping Instagram' in ds.name)
        tiktok = sum(1 for ds in datasets if 'Scraping Tiktok' in ds.name or 'Scraping TikTok' in ds.name)
        return jsonify({
            'success': True,
            'total': total,
            'twitter': twitter,
            'facebook': facebook,
            'instagram': instagram,
            'tiktok': tiktok
        })
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@api_bp.route('/recent-uploads')
@login_required
def get_recent_uploads():
    try:
        page = request.args.get('page', 1, type=int)
        limit = request.args.get('limit', 5, type=int)
        
        query = Dataset.query.filter(~Dataset.name.like('Scraping%'))
        
        if not current_user.is_admin():
            query = query.filter(Dataset.uploaded_by == current_user.id)
            
        # Total count for pagination
        total_count = query.count()
        
        # Get data
        query = query.order_by(desc(Dataset.created_at))
        datasets = query.paginate(page=page, per_page=limit, error_out=False).items
        
        data = []
        for ds in datasets:
            # Convert to Jakarta time
            if ds.created_at.tzinfo is None:
                dt_jakarta = pytz.utc.localize(ds.created_at).astimezone(JAKARTA_TZ)
            else:
                dt_jakarta = ds.created_at.astimezone(JAKARTA_TZ)
                
            data.append({
                'dataset_name': ds.name,
                'records_count': ds.total_records,
                'status': ds.status,
                'username': ds.user.username if ds.user else 'Unknown',
                'created_date': dt_jakarta.strftime('%d %b %Y'),
                'created_time': dt_jakarta.strftime('%H:%M WIB'),
                'dataset_id': ds.id
            })
            
        return jsonify({
            'success': True,
            'data': data,
            'pagination': {
                'page': page,
                'limit': limit,
                'total': total_count
            }
        })
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@api_bp.route('/admin/users/<int:id>', methods=['GET'])
@login_required
@admin_required
def get_user_details(id):
    try:
        user = User.query.get(id)
        if not user:
            return jsonify({'success': False, 'message': 'User tidak ditemukan'}), 404
            
        # Stats
        total_uploads = Dataset.query.filter_by(uploaded_by=id).filter(~Dataset.name.like('Scraping%')).count()
        total_scraping = Dataset.query.filter_by(uploaded_by=id).filter(Dataset.name.like('Scraping%')).count()
        total_classifications = ClassificationResult.query.filter_by(classified_by=id).count()
        
        # Recent activities
        recent_activities = []
        activities = UserActivity.query.filter_by(user_id=id).order_by(desc(UserActivity.created_at)).limit(5).all()
        for act in activities:
            dt_jakarta = act.created_at
            if dt_jakarta.tzinfo is None:
                dt_jakarta = pytz.utc.localize(dt_jakarta).astimezone(JAKARTA_TZ)
            else:
                dt_jakarta = dt_jakarta.astimezone(JAKARTA_TZ)
                
            recent_activities.append({
                'created_at': dt_jakarta.strftime('%d/%m/%Y %H:%M WIB'),
                'icon': act.icon or 'fa-circle',
                'color': act.color or 'primary',
                'title': act.action,
                'description': act.description
            })
            
        dt_created = user.created_at
        if dt_created:
             if dt_created.tzinfo is None:
                dt_created = pytz.utc.localize(dt_created).astimezone(JAKARTA_TZ)
             else:
                dt_created = dt_created.astimezone(JAKARTA_TZ)

        dt_last_login = user.last_login
        if dt_last_login:
             if dt_last_login.tzinfo is None:
                dt_last_login = pytz.utc.localize(dt_last_login).astimezone(JAKARTA_TZ)
             else:
                dt_last_login = dt_last_login.astimezone(JAKARTA_TZ)
                
        data = {
            'id': user.id,
            'username': user.username,
            'email': user.email,
            'role': user.role,
            'is_active': user.is_active,
            'created_at': dt_created.strftime('%d/%m/%Y %H:%M WIB') if dt_created else '-',
            'last_login': dt_last_login.strftime('%d/%m/%Y %H:%M WIB') if dt_last_login else 'Belum pernah',
            'stats': {
                'total_uploads': total_uploads,
                'total_scraping': total_scraping,
                'total_classifications': total_classifications
            },
            'recent_activities': recent_activities
        }
        
        return jsonify(data)
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@api_bp.route('/upload-statistics')
@login_required
def upload_statistics():
    """API endpoint for upload page statistics"""
    try:
        # Base query for datasets (excluding scraping)
        dataset_query = Dataset.query.filter(~Dataset.name.like('Scraping%'))
        
        # Base query for raw data (source_type='upload')
        raw_data_query = RawData.query.filter_by(source_type='upload')
        
        if not current_user.is_admin():
            dataset_query = dataset_query.filter(Dataset.uploaded_by == current_user.id)
            raw_data_query = raw_data_query.filter(RawData.uploaded_by == current_user.id)
            
        # 1. Total Uploads (Datasets)
        total_uploads = dataset_query.count()
        
        # 2. Total Records (Raw Data rows)
        total_records = raw_data_query.count()
        
        # 3. Today's Uploads
        # Use Jakarta time to determine "today"
        now_jakarta = get_jakarta_time()
        start_of_day_jakarta = now_jakarta.replace(hour=0, minute=0, second=0, microsecond=0)
        # Convert to UTC for database query (since DB stores in UTC)
        start_of_day_utc = start_of_day_jakarta.astimezone(pytz.utc).replace(tzinfo=None)
        
        today_uploads = dataset_query.filter(Dataset.created_at >= start_of_day_utc).count()
        
        # 4. Average File Size (Average of files, not rows)
        # Group by dataset_id to get one size per dataset
        file_sizes_query = db.session.query(RawData.file_size).filter(
            RawData.source_type == 'upload'
        )
        
        if not current_user.is_admin():
            file_sizes_query = file_sizes_query.filter(RawData.uploaded_by == current_user.id)
            
        file_sizes_query = file_sizes_query.group_by(RawData.dataset_id, RawData.file_size)
        
        # Execute and get list of sizes
        sizes = [r[0] for r in file_sizes_query.all() if r[0] is not None]
        
        avg_file_size = 0
        if sizes:
            avg_file_size = sum(sizes) / len(sizes)
        
        # Convert to KB
        avg_file_size_kb = round(avg_file_size / 1024, 2)
        
        return jsonify({
            'success': True,
            'data': {
                'total': total_uploads,
                'totalRecords': total_records,
                'todayUploads': today_uploads,
                'avgFileSize': avg_file_size_kb
            }
        })
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500
