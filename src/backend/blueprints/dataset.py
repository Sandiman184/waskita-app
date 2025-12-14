from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, current_app
from flask_login import login_required, current_user
from sqlalchemy import desc, text
from models.models import db, Dataset, RawData, RawDataScraper, CleanDataUpload, CleanDataScraper, ClassificationResult, ClassificationBatch
from utils.utils import active_user_required, check_permission_with_feedback, clean_text, check_cleaned_content_duplicate, get_jakarta_time, generate_activity_log
from utils.security_utils import generate_secure_filename, SecurityValidator, log_security_event
from utils.i18n import t
import os
import uuid
import threading
import pandas as pd
from datetime import datetime

from werkzeug.utils import secure_filename
import os

dataset_bp = Blueprint('dataset', __name__)

@dataset_bp.route('/dataset/<int:id>/details')
@login_required
def details(id):
    """Dataset details view with tabs"""
    try:
        dataset = Dataset.query.get_or_404(id)
        
        # Check permission
        if not current_user.is_admin() and dataset.uploaded_by != current_user.id:
            # Check if it's a scraper dataset owned by user
            is_owner = False
            if dataset.uploaded_by == current_user.id:
                is_owner = True
            else:
                # Check raw data ownership
                has_data = RawData.query.filter_by(dataset_id=dataset.id, uploaded_by=current_user.id).first()
                if has_data:
                    is_owner = True
                else:
                    has_scraper_data = RawDataScraper.query.filter_by(dataset_id=dataset.id, scraped_by=current_user.id).first()
                    if has_scraper_data:
                        is_owner = True
            
            if not is_owner:
                flash(t('You do not have permission to access this dataset'), 'error')
                return redirect(url_for('dataset.management_table'))

        # Pagination parameters
        per_page = 10
        raw_page = request.args.get('raw_page', 1, type=int)
        clean_page = request.args.get('clean_page', 1, type=int)
        classified_page = request.args.get('classified_page', 1, type=int)
        
        # Sorting parameters
        sort_by = request.args.get('sort_by', 'id', type=str)
        sort_order = request.args.get('sort_order', 'asc', type=str)
        
        # 1. Raw Data
        raw_upload_query = RawData.query.filter_by(dataset_id=dataset.id)
        raw_scraper_query = RawDataScraper.query.filter_by(dataset_id=dataset.id)
        
        total_raw_upload = raw_upload_query.count()
        total_raw_scraper = raw_scraper_query.count()
        total_raw_items = total_raw_upload + total_raw_scraper
        
        # Calculate pagination for combined view is complex, 
        # for simplicity we'll show uploads then scrapers, or just fetch all for now if not too large
        # But for proper pagination, we should probably just paginate them separately or combine in SQL.
        # Given the template iterates both, let's just paginate them individually but share the page number? 
        # Or better: just fetch what fits on the current page.
        
        # Simple approach: Fetch slice based on page
        # If page 1, take 0-10. If 10 < total_upload, take from upload.
        # If page > total_upload/10, take from scraper.
        
        # Let's use separate pagination for simplicity in backend, but frontend expects lists.
        # We will pass the paginated objects to frontend.
        
        raw_upload_pagination = raw_upload_query.paginate(page=raw_page, per_page=per_page, error_out=False)
        raw_scraper_pagination = raw_scraper_query.paginate(page=raw_page, per_page=per_page, error_out=False)
        
        # However, the template iterates BOTH in the same table. 
        # If we pass both paginations for the same page, we show 10 uploads AND 10 scrapers = 20 items.
        # That's acceptable.
        
        raw_upload_data = raw_upload_pagination.items
        raw_scraper_data = raw_scraper_pagination.items
        
        # 2. Clean Data
        clean_upload_query = CleanDataUpload.query.filter_by(dataset_id=dataset.id)
        
        # Join for CleanDataScraper to filter by dataset_id (which is in RawDataScraper)
        # But wait, CleanDataScraper model has dataset_id field? 
        # Let's check model definition or use join. 
        # In cleaning_service.py: clean_scraper_obj = CleanDataScraper(..., dataset_id=raw_scraper.dataset_id, ...)
        # So it likely has dataset_id.
        clean_scraper_query = CleanDataScraper.query.filter_by(dataset_id=dataset.id)
        
        total_clean_upload = clean_upload_query.count()
        total_clean_scraper = clean_scraper_query.count()
        total_clean_items = total_clean_upload + total_clean_scraper
        
        clean_upload_pagination = clean_upload_query.paginate(page=clean_page, per_page=per_page, error_out=False)
        clean_scraper_pagination = clean_scraper_query.paginate(page=clean_page, per_page=per_page, error_out=False)
        
        clean_upload_data = clean_upload_pagination.items
        clean_scraper_data = clean_scraper_pagination.items
        
        # 3. Lifecycle Data (Unified View)
        # We fetch all RawData and attach Clean/Classified info if available
        
        # Calculate totals for badges/stats (keep existing logic for stats)
        classified_upload_count_query = db.session.query(ClassificationResult).join(
            CleanDataUpload, ClassificationResult.data_id == CleanDataUpload.id
        ).filter(
            ClassificationResult.data_type == 'upload',
            CleanDataUpload.dataset_id == dataset.id
        )
        
        classified_scraper_count_query = db.session.query(ClassificationResult).join(
            CleanDataScraper, ClassificationResult.data_id == CleanDataScraper.id
        ).filter(
            ClassificationResult.data_type == 'scraper',
            CleanDataScraper.dataset_id == dataset.id
        )
        
        # Count distinct data IDs that are classified
        total_classified_upload = classified_upload_count_query.with_entities(ClassificationResult.data_id).distinct().count()
        total_classified_scraper = classified_scraper_count_query.with_entities(ClassificationResult.data_id).distinct().count()
        total_classified_items = total_classified_upload + total_classified_scraper

        # --- UPLOAD DATA (Raw based) ---
        lifecycle_upload_query = RawData.query.filter_by(dataset_id=dataset.id)
        
        # Apply sorting for uploads
        if sort_by == 'username':
            if sort_order == 'desc':
                lifecycle_upload_query = lifecycle_upload_query.order_by(desc(RawData.username))
            else:
                lifecycle_upload_query = lifecycle_upload_query.order_by(RawData.username)
        else: # Default by ID
            if sort_order == 'desc':
                lifecycle_upload_query = lifecycle_upload_query.order_by(desc(RawData.id))
            else:
                lifecycle_upload_query = lifecycle_upload_query.order_by(RawData.id)
        
        # Pagination for "Classified" tab (now Unified tab)
        classified_uploads_pagination = lifecycle_upload_query.paginate(page=classified_page, per_page=per_page, error_out=False)
        
        # --- SCRAPER DATA (Raw based) ---
        lifecycle_scraper_query = RawDataScraper.query.filter_by(dataset_id=dataset.id)
        
        # Apply sorting for scrapers
        if sort_by == 'username':
            if sort_order == 'desc':
                lifecycle_scraper_query = lifecycle_scraper_query.order_by(desc(RawDataScraper.username))
            else:
                lifecycle_scraper_query = lifecycle_scraper_query.order_by(RawDataScraper.username)
        else: # Default by ID
            if sort_order == 'desc':
                lifecycle_scraper_query = lifecycle_scraper_query.order_by(desc(RawDataScraper.id))
            else:
                lifecycle_scraper_query = lifecycle_scraper_query.order_by(RawDataScraper.id)
                
        classified_scrapers_pagination = lifecycle_scraper_query.paginate(page=classified_page, per_page=per_page, error_out=False)
        
        # Helper class for template
        class LifecycleItem:
            def __init__(self, **kwargs):
                self.__dict__.update(kwargs)
            def get(self, key, default=None):
                return self.__dict__.get(key, default)
            def __getitem__(self, key):
                return self.__dict__[key]

        # Helper to attach lifecycle info
        def attach_lifecycle_info(raw_items, dtype):
            enriched = []
            for item in raw_items:
                # Base info from Raw Data
                info = {
                    'id': item.id,
                    'username': item.username,
                    'url': item.url,
                    'content': item.content, # Raw content for table
                    'raw_content': item.content,
                    'created_at': item.created_at,
                    'cleaned_content': None,
                    'clean_id': None,
                    'models': {},
                    'status': 'raw',
                    'raw_data': item # For template access
                }
                
                # Find Clean Data
                clean_item = None
                if dtype == 'upload':
                    # RawData has backref clean_upload_data (list)
                    if item.clean_upload_data:
                         clean_item = item.clean_upload_data[0] # Take first
                else:
                    # RawDataScraper needs manual query or check if relationship exists
                    # Based on models.py, CleanDataScraper has raw_data_scraper_id
                    clean_item = CleanDataScraper.query.filter_by(raw_data_scraper_id=item.id).first()
                
                if clean_item:
                    info['cleaned_content'] = clean_item.cleaned_content
                    info['clean_id'] = clean_item.id
                    info['status'] = 'cleaned'
                    
                    # Find Classification Results
                    results = ClassificationResult.query.filter_by(
                        data_type=dtype,
                        data_id=clean_item.id
                    ).all()
                    
                    if results:
                        info['status'] = 'classified'
                        for res in results:
                            info['models'][res.model_name] = res
                
                enriched.append(LifecycleItem(**info))
            return enriched

        classified_upload_data = attach_lifecycle_info(classified_uploads_pagination.items, 'upload')
        classified_scraper_data = attach_lifecycle_info(classified_scrapers_pagination.items, 'scraper')
        
        
        # Get visible algorithms
        # visible_algorithms = current_app.config.get('VISIBLE_ALGORITHMS')
        classification_models = current_app.config.get('CLASSIFICATION_MODELS', {})
        
        # --- ENHANCEMENT: ONLY Include algorithms that have results for this dataset ---
        # Find all models that have results for this dataset
        
        # 1. Get clean data IDs for this dataset
        c_upload_ids_query = db.session.query(CleanDataUpload.id).filter_by(dataset_id=dataset.id)
        # Optimized: Use dataset_id in CleanDataScraper (populated in Task 1)
        c_scraper_ids_query = db.session.query(CleanDataScraper.id).filter_by(dataset_id=dataset.id)
        
        # 2. Get distinct model names from ClassificationResult for these data IDs
        # Union the checks for upload and scraper data
        used_models_query = db.session.query(ClassificationResult.model_name).distinct().filter(
            ((ClassificationResult.data_type == 'upload') & (ClassificationResult.data_id.in_(c_upload_ids_query))) |
            ((ClassificationResult.data_type == 'scraper') & (ClassificationResult.data_id.in_(c_scraper_ids_query)))
        )
        
        used_models = [m[0] for m in used_models_query.all()]
        
        # 3. Set visible_algorithms ONLY to used_models (Strict Filtering)
        # Sort based on config order if possible, otherwise alphabetical
        all_models = list(classification_models.keys())
        used_models.sort(key=lambda x: all_models.index(x) if x in all_models else 999)
        
        visible_algorithms = used_models


            
        return render_template('dataset/details.html',
                             dataset=dataset,
                             # Raw
                             raw_upload_data=raw_upload_data,
                             raw_scraper_data=raw_scraper_data,
                             raw_page=raw_page,
                             raw_total_pages=max(raw_upload_pagination.pages, raw_scraper_pagination.pages),
                             raw_upload_total_pages=raw_upload_pagination.pages,
                             raw_scraper_total_pages=raw_scraper_pagination.pages,
                             total_raw_items=total_raw_items,
                             
                             # Clean
                             clean_upload_data=clean_upload_data,
                             clean_scraper_data=clean_scraper_data,
                             clean_page=clean_page,
                             clean_total_pages=max(clean_upload_pagination.pages, clean_scraper_pagination.pages),
                             clean_upload_total_pages=clean_upload_pagination.pages,
                             clean_scraper_total_pages=clean_scraper_pagination.pages,
                             total_clean_items=total_clean_items,
                             
                             # Classified
                             classified_upload_data=classified_upload_data,
                             classified_scraper_data=classified_scraper_data,
                             classified_page=classified_page,
                             classified_total_pages=max(classified_uploads_pagination.pages, classified_scrapers_pagination.pages),
                             classified_upload_total_pages=classified_uploads_pagination.pages,
                             classified_scraper_total_pages=classified_scrapers_pagination.pages,
                             total_classified_items=total_classified_items,
                             
                             per_page=per_page,
                             visible_algorithms=visible_algorithms,
                             sort_by=sort_by,
                             sort_order=sort_order)
                             
    except Exception as e:
        flash(f'Error loading dataset details: {str(e)}', 'error')
        return redirect(url_for('dataset.management_table'))

@dataset_bp.route('/dataset/management/table')
@login_required
def management_table():
    """Dataset management with table view"""
    try:
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 25, type=int)
        search = request.args.get('search', '', type=str)
        sort_by = request.args.get('sort_by', 'created_at', type=str)
        sort_order = request.args.get('sort_order', 'desc', type=str)
        
        query = Dataset.query
        
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
            
            all_user_dataset_ids = list(set(user_dataset_ids + scraper_dataset_ids))
            
            # Also include datasets created by user (if we had a created_by field in Dataset, but currently we rely on data ownership)
            # Assuming Dataset model has uploaded_by which refers to the creator
            query = query.filter(
                (Dataset.id.in_(all_user_dataset_ids)) | 
                (Dataset.uploaded_by == current_user.id)
            )
            
        if search:
            query = query.filter(Dataset.name.ilike(f'%{search}%'))
            
        # Filter out Aborted datasets (they should only appear in History until mapped)
        query = query.filter(Dataset.status != 'Aborted')
            
        if sort_order == 'desc':
            query = query.order_by(desc(getattr(Dataset, sort_by, Dataset.created_at)))
        else:
            query = query.order_by(getattr(Dataset, sort_by, Dataset.created_at))
            
        datasets = query.paginate(page=page, per_page=per_page, error_out=False)
        
        # Calculate stats for each dataset to be displayed in the table
        dataset_stats = []
        for ds in datasets.items:
            # Get counts
            raw_upload_count = RawData.query.filter_by(dataset_id=ds.id).count()
            raw_scraper_count = RawDataScraper.query.filter_by(dataset_id=ds.id).count()
            clean_upload_count = CleanDataUpload.query.filter_by(dataset_id=ds.id).count()
            clean_scraper_count = CleanDataScraper.query.filter_by(dataset_id=ds.id).count()
            
            clean_count = clean_upload_count + clean_scraper_count
            
            # Calculate classified count
            # Count classified upload data
            classified_upload_count = ClassificationResult.query.join(
                CleanDataUpload, ClassificationResult.data_id == CleanDataUpload.id
            ).filter(
                ClassificationResult.data_type == 'upload',
                CleanDataUpload.dataset_id == ds.id
            ).count()
            
            # Count classified scraper data
            classified_scraper_count = ClassificationResult.query.join(
                CleanDataScraper, ClassificationResult.data_id == CleanDataScraper.id
            ).filter(
                ClassificationResult.data_type == 'scraper',
                CleanDataScraper.dataset_id == ds.id
            ).count()
            
            classified_count = classified_upload_count + classified_scraper_count
            
            # Get a sample record for display (prioritize upload, then scraper)
            sample_content = '-'
            sample_username = '-'
            sample_url = '-'
            
            sample_upload = RawData.query.filter_by(dataset_id=ds.id).first()
            if sample_upload:
                sample_content = sample_upload.content
                sample_username = sample_upload.username
                sample_url = sample_upload.url or '-'
            else:
                sample_scraper = RawDataScraper.query.filter_by(dataset_id=ds.id).first()
                if sample_scraper:
                    sample_content = sample_scraper.content
                    sample_username = sample_scraper.username
                    sample_url = sample_scraper.url or '-'
            
            dataset_stats.append({
                'dataset': ds,
                'total_records': ds.total_records,
                'raw_upload_count': raw_upload_count,
                'raw_scraper_count': raw_scraper_count,
                'clean_count': clean_count,
                'classified_count': classified_count,
                'sample_content': sample_content,
                'sample_username': sample_username,
                'sample_url': sample_url
            })
        
        return render_template('dataset/management_table.html', 
                             dataset_stats=dataset_stats, 
                             pagination=datasets,
                             search=search,
                             sort_by=sort_by,
                             sort_order=sort_order,
                             per_page=per_page)
        
    except Exception as e:
        flash(f'Error loading datasets: {str(e)}', 'error')
        return redirect(url_for('main.dashboard'))

@dataset_bp.route('/api/dataset/<int:id>/clean', methods=['POST'])
@login_required
def clean_dataset(id):
    try:
        dataset = Dataset.query.get_or_404(id)
        
        # Check permission
        if not current_user.is_admin() and dataset.uploaded_by != current_user.id:
            return jsonify({'success': False, 'message': 'Permission denied'}), 403
            
        # Check if already cleaned
        if dataset.status == 'Cleaned':
             return jsonify({
                'success': True, 
                'already_cleaned': True,
                'message': 'Dataset is already cleaned',
                'cleaned_count': dataset.cleaned_records
            })

        # Import service here to avoid circular import
        from services.cleaning_service import process_bulk_cleaning
        
        # Generate task ID
        task_id = str(uuid.uuid4())
        
        # Initialize progress
        if 'CLEANING_PROGRESS' not in current_app.config:
            current_app.config['CLEANING_PROGRESS'] = {}
            
        current_app.config['CLEANING_PROGRESS'][task_id] = {
            'status': 'starting',
            'progress': 0,
            'current': 0,
            'total': 0,
            'ignored_count': 0,
            'message': 'Starting cleaning process...',
            'errors': []
        }
        
        # Run async cleaning for single dataset using the bulk service (it handles list of IDs)
        thread = threading.Thread(
            target=process_bulk_cleaning,
            args=(current_app._get_current_object(), [id], task_id, current_user.id)
        )
        thread.daemon = True
        thread.start()
        
        generate_activity_log(
            action='cleaning',
            description=f'Started cleaning process for dataset: {dataset.name}',
            user_id=current_user.id,
            icon='fa-broom',
            color='info'
        )

        return jsonify({
            'success': True,
            'message': 'Cleaning process started',
            'task_id': task_id
        })
        
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@dataset_bp.route('/dataset/bulk/clean', methods=['POST'])
@login_required
def bulk_clean_datasets():
    try:
        data = request.get_json()
        dataset_ids = data.get('dataset_ids', [])
        
        if not dataset_ids:
            return jsonify({'success': False, 'message': 'No datasets selected'}), 400
        
        # Generate task ID
        task_id = str(uuid.uuid4())
        
        # Initialize progress
        if 'CLEANING_PROGRESS' not in current_app.config:
            current_app.config['CLEANING_PROGRESS'] = {}
            
        current_app.config['CLEANING_PROGRESS'][task_id] = {
            'status': 'starting',
            'progress': 0,
            'current': 0,
            'total': 0,
            'message': 'Starting cleaning process...',
            'errors': []
        }
        
        # We need to import the background task function here or move it to a utils module to avoid circular imports
        # For now, let's assume we move process_bulk_cleaning to a service
        from services.cleaning_service import process_bulk_cleaning
        
        thread = threading.Thread(
            target=process_bulk_cleaning,
            args=(current_app._get_current_object(), dataset_ids, task_id, current_user.id)
        )
        thread.daemon = True
        thread.start()
        
        generate_activity_log(
            action='cleaning',
            description=f'Started bulk cleaning process for {len(dataset_ids)} datasets',
            user_id=current_user.id,
            icon='fa-broom',
            color='info'
        )

        return jsonify({
            'success': True,
            'message': 'Cleaning process started',
            'task_id': task_id
        })
        
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@dataset_bp.route('/dataset/bulk/clean/progress/<task_id>')
@login_required
def get_cleaning_progress(task_id):
    progress = current_app.config.get('CLEANING_PROGRESS', {}).get(task_id)
    
    if not progress:
        return jsonify({'status': 'error', 'message': 'Task not found'}), 404
        
    return jsonify(progress)

@dataset_bp.route('/dataset/upload', methods=['GET', 'POST'])
@login_required
def upload_file():
    """Upload new dataset"""
    if request.method == 'POST':
        if 'file' not in request.files:
            flash(t('No file selected'), 'error')
            return redirect(request.url)
        
        file = request.files['file']
        
        if file.filename == '':
            flash(t('No file selected'), 'error')
            return redirect(request.url)
            
        if file and (file.filename.endswith('.csv') or file.filename.endswith('.xlsx') or file.filename.endswith('.xls')):
            try:
                # Create dataset entry
                dataset_name = request.form.get('dataset_name')
                if not dataset_name:
                    dataset_name = file.filename
                
                # Create Dataset record
                new_dataset = Dataset(
                    name=dataset_name,
                    description=f"Dataset uploaded on {datetime.now().strftime('%Y-%m-%d %H:%M')}",
                    uploaded_by=current_user.id,
                    status='Raw'
                )
                db.session.add(new_dataset)
                db.session.flush() # Get ID
                
                # Get file size properly
                file.seek(0, os.SEEK_END)
                file_size_bytes = file.tell()
                file.seek(0)
                
                # Fallback if size is 0
                if file_size_bytes == 0:
                    try:
                        blob = file.read()
                        file_size_bytes = len(blob)
                        file.seek(0)
                    except:
                        pass
                
                # Process file
                if file.filename.endswith('.csv'):
                    try:
                        df = pd.read_csv(file)
                    except:
                        # Try with different encoding/separator
                        file.seek(0)
                        df = pd.read_csv(file, sep=';', encoding='latin1')
                else:
                    df = pd.read_excel(file)
                
                # Loose column mapping
                df.columns = [str(c).lower().strip() for c in df.columns]
                
                # Check if 'content' or 'text' or 'komentar' exists
                content_col = next((c for c in df.columns if c in ['content', 'text', 'tweet', 'comment', 'komentar', 'isi', 'text_original']), None)
                username_col = next((c for c in df.columns if c in ['username', 'user', 'author', 'pengguna', 'screen_name']), None)
                platform_col = next((c for c in df.columns if c in ['platform', 'source', 'sumber']), None)
                
                if not content_col:
                    flash(t('File must contain content/text/tweet/comment column'), 'error')
                    db.session.rollback()
                    return redirect(request.url)
                
                count = 0
                for _, row in df.iterrows():
                    # Skip empty content
                    if pd.isna(row[content_col]) or str(row[content_col]).strip() == '':
                        continue
                        
                    raw_data = RawData(
                        username=str(row[username_col]) if username_col and pd.notna(row[username_col]) else 'anonymous',
                        content=str(row[content_col]),
                        platform=str(row[platform_col]).lower() if platform_col and pd.notna(row[platform_col]) else 'unknown',
                        source_type='upload',
                        status='raw',
                        file_size=file_size_bytes, 
                        original_filename=file.filename,
                        dataset_id=new_dataset.id,
                        dataset_name=new_dataset.name,
                        uploaded_by=current_user.id
                    )
                    db.session.add(raw_data)
                    count += 1
                
                new_dataset.total_records = count
                db.session.commit()
                
                generate_activity_log(
                    action='upload',
                    description=f'Uploaded dataset: {new_dataset.name} ({count} records)',
                    user_id=current_user.id,
                    icon='fa-upload',
                    color='primary'
                )

                flash(t('Dataset uploaded successfully') + f'. {count} data added.', 'success')
                return redirect(url_for('dataset.management_table'))
                
            except Exception as e:
                db.session.rollback()
                flash(f"{t('Error processing file')}: {str(e)}", 'error')
                return redirect(request.url)
        else:
            flash(t('File format not supported. Use CSV or Excel.'), 'error')
            return redirect(request.url)

    return render_template('data/upload.html')

@dataset_bp.route('/upload_data', methods=['GET', 'POST'])
@login_required
def upload_data_legacy():
    # If this is a GET request, it might be a redirect from a failed POST or direct access
    # We should return the upload page HTML in this case, BUT if the client expected JSON
    # (AJAX request), this will cause "Error 200" parsererror.
    # To fix this, we should check if it's an AJAX request.
    if request.method == 'GET':
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
             return jsonify({'success': False, 'message': 'Method GET not allowed for AJAX'}), 405
        return render_template('data/upload.html')
        
    # POST request handling
    try:
        if 'file' not in request.files:
            return jsonify({'success': False, 'message': 'No file selected'}), 400
        file = request.files['file']
        if file.filename == '':
            return jsonify({'success': False, 'message': 'No file selected'}), 400
        if not (file.filename.endswith('.csv') or file.filename.endswith('.xlsx') or file.filename.endswith('.xls')):
            return jsonify({'success': False, 'message': 'File format not supported. Use CSV or Excel.'}), 400
            
        dataset_name = request.form.get('dataset_name') or file.filename
        
        # Get file size properly
        file.seek(0, os.SEEK_END)
        file_size_bytes = file.tell()
        file.seek(0)
        
        # Fallback if size is 0
        if file_size_bytes == 0:
            try:
                blob = file.read()
                file_size_bytes = len(blob)
                file.seek(0)
            except:
                pass
        
        # Read file
        if file.filename.endswith('.csv'):
            try:
                df = pd.read_csv(file)
            except:
                file.seek(0)
                df = pd.read_csv(file, sep=';', encoding='latin1')
        else:
            df = pd.read_excel(file)
            
        # Normalize columns
        df.columns = [str(c).lower().strip() for c in df.columns]
        
        # Check for required columns
        content_col = next((c for c in df.columns if c in ['content', 'text', 'tweet', 'comment', 'komentar', 'isi', 'text_original']), None)
        username_col = next((c for c in df.columns if c in ['username', 'user', 'author', 'pengguna', 'screen_name']), None)
        platform_col = next((c for c in df.columns if c in ['platform', 'source', 'sumber']), None)
        
        # If no content column found, offer mapping
        if not content_col:
            # Save file to temp storage for persistence
            filename = secure_filename(file.filename)
            temp_dir = os.path.join(current_app.config['UPLOAD_FOLDER'], 'temp')
            os.makedirs(temp_dir, exist_ok=True)
            
            # Generate unique filename to avoid collision
            unique_filename = f"{uuid.uuid4().hex}_{filename}"
            file_path = os.path.join(temp_dir, unique_filename)
            
            # Reset file pointer and save
            file.seek(0)
            file.save(file_path)
            
            # Create dataset with 'Pending Mapping' status
            pending_dataset = Dataset(
                name=dataset_name,
                description=f"Dataset uploaded on {get_jakarta_time().strftime('%Y-%m-%d %H:%M')}",
                uploaded_by=current_user.id,
                status='Pending Mapping',
                file_path=file_path,
                total_records=0
            )
            db.session.add(pending_dataset)
            db.session.commit()
            
            sample = df.head(5).fillna('').to_dict(orient='records')
            
            return jsonify({
                'success': True, 
                'show_mapping': True, 
                'columns': list(df.columns), 
                'sample_data': sample, 
                'filename': file.filename,
                'dataset_id': pending_dataset.id
            })
            
        # Create dataset
        new_dataset = Dataset(
            name=dataset_name,
            description=f"Dataset uploaded on {get_jakarta_time().strftime('%Y-%m-%d %H:%M')}",
            uploaded_by=current_user.id,
            status='Raw'
        )
        db.session.add(new_dataset)
        db.session.flush()
        
        count = 0
        for _, row in df.iterrows():
            if pd.isna(row[content_col]) or str(row[content_col]).strip() == '':
                continue
            
            # Safe extraction
            username_val = str(row[username_col]) if username_col and pd.notna(row[username_col]) else 'anonymous'
            content_val = str(row[content_col])
            url_val = str(row['url']) if 'url' in df.columns and pd.notna(row['url']) else None
            platform_val = str(row[platform_col]).lower() if platform_col and pd.notna(row[platform_col]) else 'unknown'
            
            raw_data = RawData(
                username=username_val,
                content=content_val,
                url=url_val,
                platform=platform_val,
                source_type='upload',
                status='raw',
                file_size=file_size_bytes,
                original_filename=file.filename,
                dataset_id=new_dataset.id,
                dataset_name=new_dataset.name,
                uploaded_by=current_user.id
            )
            db.session.add(raw_data)
            count += 1
            
        new_dataset.total_records = count
        db.session.commit()
        
        generate_activity_log(
            action='upload',
            description=f'Uploaded dataset: {new_dataset.name} ({count} records)',
            user_id=current_user.id,
            icon='fa-upload',
            color='primary'
        )

        return jsonify({'success': True, 'count': count, 'dataset_id': new_dataset.id})
        
    except Exception as e:
        db.session.rollback()
        # Log error
        current_app.logger.error(f"Upload error: {str(e)}")
        return jsonify({'success': False, 'message': f'Server Error: {str(e)}'}), 500

@dataset_bp.route('/process_column_mapping', methods=['POST'])
@login_required
def process_column_mapping():
    data = request.get_json() or {}
    dataset_id = data.get('dataset_id')
    content_column = data.get('content_column')
    username_column = data.get('username_column')
    url_column = data.get('url_column')
    
    # Try to load from DB first (Persistent way)
    dataset = None
    df = None
    filename = "unknown"
    file_size_bytes = 0
    
    if dataset_id:
        dataset = Dataset.query.get(dataset_id)
        if dataset and dataset.uploaded_by == current_user.id and dataset.file_path and os.path.exists(dataset.file_path):
            try:
                if dataset.file_path.endswith('.csv'):
                    try:
                        df = pd.read_csv(dataset.file_path)
                    except:
                        df = pd.read_csv(dataset.file_path, sep=';', encoding='latin1')
                else:
                    df = pd.read_excel(dataset.file_path)
                
                # Normalize columns
                df.columns = [str(c).lower().strip() for c in df.columns]
                filename = os.path.basename(dataset.file_path).split('_', 1)[1] if '_' in os.path.basename(dataset.file_path) else os.path.basename(dataset.file_path)
                file_size_bytes = os.path.getsize(dataset.file_path)
            except Exception as e:
                return jsonify({'success': False, 'message': f'Error reading saved file: {str(e)}'}), 500
        else:
            return jsonify({'success': False, 'message': 'Dataset or file not found'}), 404
            
    # Fallback to legacy session (In-memory) - for backward compatibility or if DB load fails
    if df is None:
        store = current_app.config.setdefault('UPLOAD_SESSIONS', {})
        sess = store.get(current_user.id)
        if not sess:
            return jsonify({'success': False, 'message': 'Upload session not found'}), 400
        df = sess['df']
        filename = sess.get('filename')
        dataset_name = sess.get('dataset_name') or filename
        
        # Create new dataset since we didn't find one in DB
        dataset = Dataset(
            name=dataset_name,
            description=f"Dataset uploaded on {get_jakarta_time().strftime('%Y-%m-%d %H:%M')}",
            uploaded_by=current_user.id,
            status='Raw'
        )
        db.session.add(dataset)
        db.session.flush()

    if not content_column or content_column not in df.columns:
        return jsonify({'success': False, 'message': 'Invalid content column'}), 400
        
    count = 0
    for _, row in df.iterrows():
        v = row[content_column]
        if pd.isna(v) or str(v).strip() == '':
            continue
        un = str(row[username_column]) if username_column and username_column in df.columns and pd.notna(row[username_column]) else 'anonymous'
        urlv = str(row[url_column]) if url_column and url_column in df.columns and pd.notna(row[url_column]) else None
        raw_data = RawData(
            username=un,
            content=str(v),
            url=urlv,
            platform='unknown',
            source_type='upload',
            status='raw',
            file_size=file_size_bytes,
            original_filename=filename,
            dataset_id=dataset.id,
            dataset_name=dataset.name,
            uploaded_by=current_user.id
        )
        db.session.add(raw_data)
        count += 1
        
    dataset.total_records = count
    dataset.status = 'Raw' # Update status from 'Pending Mapping'
    db.session.commit()
    
    generate_activity_log(
        action='upload',
        description=f'Uploaded dataset: {dataset.name} ({count} records) via mapping',
        user_id=current_user.id,
        icon='fa-upload',
        color='primary'
    )

    # Cleanup session
    try:
        store = current_app.config.get('UPLOAD_SESSIONS', {})
        if current_user.id in store:
            del store[current_user.id]
    except:
        pass
        
    return jsonify({'success': True, 'message': 'Data successfully processed', 'dataset_id': dataset.id, 'total_records': count})

@dataset_bp.route('/dataset/bulk/delete', methods=['POST'])
@login_required
def bulk_delete_datasets():
    try:
        data = request.get_json()
        dataset_ids = data.get('dataset_ids', [])
        
        if not dataset_ids:
            return jsonify({'success': False, 'message': 'No datasets selected'}), 400
        
        # Filter datasets allowed to be deleted
        query = Dataset.query.filter(Dataset.id.in_(dataset_ids))
        if not current_user.is_admin():
            query = query.filter(Dataset.uploaded_by == current_user.id)
            
        datasets = query.all()
        
        if not datasets:
            return jsonify({'success': False, 'message': 'Datasets not found or permission denied'}), 404
            
        count = 0
        errors = []
        
        for ds in datasets:
            try:
                # Manual Cascade Delete to ensure no orphaned data
                
                # 1. Clean Data Upload & Classification Results
                clean_uploads = CleanDataUpload.query.filter_by(dataset_id=ds.id).all()
                if clean_uploads:
                    clean_upload_ids = [c.id for c in clean_uploads]
                    # Delete associated classification results
                    ClassificationResult.query.filter(
                        ClassificationResult.data_type == 'upload',
                        ClassificationResult.data_id.in_(clean_upload_ids)
                    ).delete(synchronize_session=False)
                    
                    # Delete clean data
                    for item in clean_uploads:
                        db.session.delete(item)
                    
                # 2. Clean Data Scraper & Classification Results
                clean_scrapers = CleanDataScraper.query.filter_by(dataset_id=ds.id).all()
                if clean_scrapers:
                    clean_scraper_ids = [c.id for c in clean_scrapers]
                    # Delete associated classification results
                    ClassificationResult.query.filter(
                        ClassificationResult.data_type == 'scraper',
                        ClassificationResult.data_id.in_(clean_scraper_ids)
                    ).delete(synchronize_session=False)
                    
                    # Delete clean data
                    for item in clean_scrapers:
                        db.session.delete(item)
                
                # 3. Raw Data
                RawData.query.filter_by(dataset_id=ds.id).delete(synchronize_session=False)
                
                # 4. Raw Data Scraper
                RawDataScraper.query.filter_by(dataset_id=ds.id).delete(synchronize_session=False)

                # 5. Classification Batch
                ClassificationBatch.query.filter_by(dataset_id=ds.id).delete(synchronize_session=False)
                
                # 6. Finally delete the dataset
                db.session.delete(ds)
                count += 1
            except Exception as e:
                errors.append(f"Error deleting dataset {ds.id}: {str(e)}")
                
        if count > 0:
            db.session.commit()
            
            generate_activity_log(
                action='delete',
                description=f'Deleted {count} datasets',
                user_id=current_user.id,
                icon='fa-trash',
                color='danger'
            )
            
        return jsonify({
            'success': True,
            'processed': count,
            'errors': errors,
            'message': f'{count} datasets successfully deleted'
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500
