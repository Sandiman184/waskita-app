from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, current_app, send_file
from flask_login import login_required, current_user
from sqlalchemy import text, desc
from models.models import db, Dataset, RawData, RawDataScraper, CleanDataUpload, CleanDataScraper, ClassificationResult, ManualClassificationHistory, ClassificationBatch
from utils.utils import active_user_required, check_permission_with_feedback, vectorize_text, classify_content, generate_activity_log, preprocess_for_model, check_dataset_permission
from utils.i18n import t
from datetime import datetime
import numpy as np
import pandas as pd
import io
import threading
import time

classification_bp = Blueprint('classification', __name__)

# Global dictionary to track progress
classification_progress = {}

@classification_bp.route('/classification')
@login_required
@active_user_required
def index():
    # Get clean data that hasn't been classified
    
    # Check if dataset_id parameter is provided
    dataset_id = request.args.get('dataset_id')
    selected_dataset = None
    classified_count = 0
    
    clean_upload_data = []
    clean_scraper_data = []
    
    if dataset_id:
        # Get specific dataset information
        selected_dataset = db.session.get(Dataset, dataset_id)
        
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
            
            # Count classified data logic
            classified_count = 0 # Placeholder
        else:
            clean_upload_data = []
            clean_scraper_data = []
    else:
        # Get all clean data
        clean_upload_data = CleanDataUpload.query.all()
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

    # Get Batch Classification History
    batch_query = ClassificationBatch.query
    if not current_user.is_admin():
        batch_query = batch_query.filter_by(created_by=current_user.id)
    
    batch_history = batch_query.order_by(desc(ClassificationBatch.started_at)).limit(20).all()
    
    return render_template('classification/index.html',
                         clean_upload_data=clean_upload_data,
                         clean_scraper_data=clean_scraper_data,
                         clean_upload_count=clean_upload_count,
                         clean_scraper_count=clean_scraper_count,
                         total_data_count=total_data_count,
                         selected_dataset=selected_dataset,
                         classified_count=classified_count,
                         batch_history=batch_history)

@classification_bp.route('/classification/classify')
@login_required
@active_user_required
def classify():
    """Manual classification page"""
    type = request.args.get('type', 'manual')
    
    # Get model status
    word2vec_model = current_app.config.get('WORD2VEC_MODEL')
    classification_models = current_app.config.get('CLASSIFICATION_MODELS', {})
    visible_algorithms = current_app.config.get('VISIBLE_ALGORITHMS')
    
    # If visible_algorithms is None (not configured), use all. If [], it means none selected.
    if visible_algorithms is None:
        visible_algorithms = list(classification_models.keys())
    
    word2vec_status = word2vec_model is not None
    word2vec_info = f"Vocabulary Size: {len(word2vec_model.wv.key_to_index)}" if word2vec_status else "Model not loaded"
    
    models_status = {}
    for name, model in classification_models.items():
        # Check if model is visible/active
        is_visible = True
        if visible_algorithms is not None and name not in visible_algorithms:
            is_visible = False
            
        models_status[name] = {
            'status': model is not None and is_visible,
            'info': 'Active' if model is not None and is_visible else ('Hidden' if not is_visible else 'Not loaded')
        }
    
    # Get classification results counts
    if current_user.is_admin():
        clean_upload_count = CleanDataUpload.query.count()
        clean_scraper_count = CleanDataScraper.query.count()
        radical_count = ClassificationResult.query.filter_by(prediction='Radikal').count()
        non_radical_count = ClassificationResult.query.filter_by(prediction='Non-Radikal').count()
    else:
        # Filter counts by user
        clean_upload_count = CleanDataUpload.query.filter_by(cleaned_by=current_user.id).count()
        clean_scraper_count = CleanDataScraper.query.filter_by(cleaned_by=current_user.id).count()
        radical_count = ClassificationResult.query.filter_by(prediction='Radikal', classified_by=current_user.id).count()
        non_radical_count = ClassificationResult.query.filter_by(prediction='Non-Radikal', classified_by=current_user.id).count()
    
    # NOTE: History fetching logic removed as requested.
    # Manual classification history is no longer displayed on this page.
    history = []
    
    return render_template('classification/classify.html',
                         type=type,
                         word2vec_status=word2vec_status,
                         word2vec_info=word2vec_info,
                         models_status=models_status,
                         clean_upload_count=clean_upload_count,
                         clean_scraper_count=clean_scraper_count,
                         radical_count=radical_count,
                         non_radical_count=non_radical_count,
                         history=history)


@classification_bp.route('/api/classify_manual_text', methods=['POST'])
@login_required
def classify_manual_text():
    """Classify manual text input"""
    try:
        data = request.get_json()
        text_input = data.get('text')
        
        if not text_input:
            return jsonify({'success': False, 'message': 'Text input cannot be empty'}), 400
            
        # Get models
        word2vec_model = current_app.config.get('WORD2VEC_MODEL')
        classification_models = current_app.config.get('CLASSIFICATION_MODELS', {})
        visible_algorithms = current_app.config.get('VISIBLE_ALGORITHMS')
        classification_threshold = current_app.config.get('CLASSIFICATION_THRESHOLD', 0.5)
        
        # If no visible algorithms set (None), use all
        if visible_algorithms is None:
            visible_algorithms = list(classification_models.keys())
        elif len(visible_algorithms) == 0:
            # If explicit empty list (which shouldn't happen if user wants to classify), fallback to all or handle warning
            # But let's assume we want to use what's configured. If empty, maybe user disabled all.
            # But for "testing I show all", user implies they enabled all in settings.
            # Let's ensure we use the intersection of configured visible and loaded models
            pass
            
        # Filter models - use ALL configured models regardless of visibility settings for manual test IF needed?
        # User said "pastikan fungsi pemilihan pada model klasifikasi di menu ai model manegement juga di terapkan"
        # So we MUST respect visible_algorithms.
        
        # However, user also said "karena kebetulan untuk menguji saya tampilkan semua"
        # This implies they enabled all in the settings.
        
        # Logic: Only use models that are BOTH in visible_algorithms AND loaded successfully
        active_models = {k: v for k, v in classification_models.items() if k in visible_algorithms and v is not None}
        
        # If active_models is empty but we have models loaded, it might be a config issue.
        # Fallback: if active_models empty but classification_models not empty, use all loaded (safety net)
        if not active_models and classification_models:
             current_app.logger.warning("No active models found in visible_algorithms, falling back to all loaded models")
             active_models = {k: v for k, v in classification_models.items() if v is not None}
        
        results = []
        
        # Vectorize for conventional models
        # Use RAW text, let vectorize_text handle preprocessing (which calls preprocess_for_model)
        # This ensures CONSISTENCY with the new pipeline (Stemming + No Slang Norm for vectors)
        text_vector = vectorize_text(text_input, word2vec_model)
        
        # Also get the preprocessed text for display
        from utils.utils import preprocess_for_model
        preprocessed_text = preprocess_for_model(text_input)
        
        current_app.logger.info(f"Classifying manual text with {len(active_models)} models: {list(active_models.keys())}")
        
        for model_name, model in active_models.items():
            # Determine text to use
            # IndoBERT uses Preprocessed Text to match training data
            current_text_input = text_input
            if model_name == 'indobert':
                current_text_input = preprocessed_text
            
            # Note: classify_content signature is (text_vector, model, text=None)
            prediction, probabilities = classify_content(text_vector, model, text=current_text_input)
            
            # Ensure probabilities are python floats
            prob_rad = float(probabilities[1]) if len(probabilities) > 1 else 0.0
            prob_non = float(probabilities[0]) if len(probabilities) > 0 else 0.0
            
            # Apply Threshold Logic
            if prob_rad >= classification_threshold:
                prediction = 'Radikal'
            else:
                prediction = 'Non-Radikal'

            results.append({
                'model_name': model_name,
                'prediction': prediction,
                'probability_radikal': prob_rad,
                'probability_non_radikal': prob_non
            })
            
            # Save history of manual classification
            try:
                history_entry = ManualClassificationHistory(
                    text_input=text_input,
                    model_name=model_name,
                    prediction=prediction,
                    probability_radikal=prob_rad,
                    probability_non_radikal=prob_non,
                    classified_by=current_user.id
                )
                db.session.add(history_entry)
                current_app.logger.info(f"Added manual history for {model_name}: {prediction}")
            except Exception as e:
                current_app.logger.error(f"Failed to save manual history: {e}")
        
        db.session.commit()
        current_app.logger.info("Committed manual classification history")
            
        return jsonify({
            'success': True,
            'text': text_input,
            'preprocessed_text': preprocessed_text,
            'results': results
        })
        
    except Exception as e:
        current_app.logger.error(f"Error manual classification: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500

@classification_bp.route('/classification/results')
@login_required
@active_user_required
def results():
    """Classification results page"""
    
    # Get visible algorithms
    visible_algorithms = current_app.config.get('VISIBLE_ALGORITHMS')
    classification_models = current_app.config.get('CLASSIFICATION_MODELS', {})
    
    # If no visible algorithms set (None), use all
    if visible_algorithms is None:
        visible_algorithms = list(classification_models.keys())
        
    # Get all classification results with pagination
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', type=int)
    if not per_page:
        per_page = current_user.get_preferences().get('items_per_page', 20)
    
    # Identify the dataset to show
    dataset_id_param = request.args.get('dataset_id')
    target_dataset = None
    
    if dataset_id_param:
        target_dataset = db.session.get(Dataset, dataset_id_param)
        # Verify permission
        if target_dataset and not check_dataset_permission(target_dataset, current_user):
            flash(t('You do not have permission to access this dataset'), 'error')
            return redirect(url_for('classification.results'))
    
    # If no specific dataset requested, or requested one not found, use latest
    if not target_dataset:
        target_dataset = Dataset.query.filter_by(status='Classified').order_by(desc(Dataset.updated_at)).first()
    
    # Base query
    query = ClassificationResult.query
    
    # Filter by user if not admin
    if not current_user.is_admin():
        query = query.filter_by(classified_by=current_user.id)
        
    # Filter by target dataset if available
    if target_dataset:
        # Get IDs of clean data for this dataset
        clean_upload_ids = db.session.query(CleanDataUpload.id).filter_by(dataset_id=target_dataset.id).all()
        clean_upload_ids = [i[0] for i in clean_upload_ids]
        
        clean_scraper_ids = db.session.query(CleanDataScraper.id).join(
            RawDataScraper, CleanDataScraper.raw_data_scraper_id == RawDataScraper.id
        ).filter(RawDataScraper.dataset_id == target_dataset.id).all()
        clean_scraper_ids = [i[0] for i in clean_scraper_ids]
        
        # Apply filter to query
        query = query.filter(
            ((ClassificationResult.data_type == 'upload') & (ClassificationResult.data_id.in_(clean_upload_ids))) |
            ((ClassificationResult.data_type == 'scraper') & (ClassificationResult.data_id.in_(clean_scraper_ids)))
        )

        # Update visible_algorithms to ONLY include models used in this dataset (Strict Filtering)
        used_models_query = db.session.query(ClassificationResult.model_name).distinct().filter(
            ((ClassificationResult.data_type == 'upload') & (ClassificationResult.data_id.in_(clean_upload_ids))) |
            ((ClassificationResult.data_type == 'scraper') & (ClassificationResult.data_id.in_(clean_scraper_ids)))
        )
        used_models = [m[0] for m in used_models_query.all()]
        
        # Sort used_models based on global config order if possible
        all_models = list(classification_models.keys())
        used_models.sort(key=lambda x: all_models.index(x) if x in all_models else 999)
        
        # Override visible_algorithms with strict used_models
        visible_algorithms = used_models


    # Filter by visible algorithms (Admin preference)
    if visible_algorithms is not None:
        query = query.filter(ClassificationResult.model_name.in_(visible_algorithms))
        
    # Order by latest
    query = query.order_by(desc(ClassificationResult.classified_at))
    
    # Paginate
    pagination = query.paginate(page=page, per_page=per_page, error_out=False)
    results = pagination.items
    
    # Calculate statistics (based on filtered query)
    total_classifications = pagination.total
    total_data_items = db.session.query(db.func.count(db.distinct(ClassificationResult.data_id))).filter(
        ClassificationResult.id.in_([r.id for r in query.all()]) # Reuse filters from query
    ).scalar() if total_classifications > 0 else 0
    
    # Calculate per-model stats
    model_stats = {}
    
    # Only show stats for visible algorithms
    model_names = visible_algorithms
    
    # Recalculate total_radikal and total_non_radikal based only on visible algorithms AND filtered dataset
    total_radikal = 0
    total_non_radikal = 0
        
    for name in model_names:
        # We need to apply the same dataset filters to these counts
        sub_query = query.filter_by(model_name=name)
        
        rad = sub_query.filter_by(prediction='Radikal').count()
        non = sub_query.filter_by(prediction='Non-Radikal').count()
        
        model_stats[name] = {'radikal': rad, 'non_radikal': non}
        
        total_radikal += rad
        total_non_radikal += non
    
    # Recalculate total_classifications based on visible models
    # (Should match pagination.total if query was correctly filtered by model_name)
    total_classifications = total_radikal + total_non_radikal
    
    # Prepare datasets list with aggregated results
    datasets = []
    
    # Only show the target dataset
    classified_datasets = [target_dataset] if target_dataset else []
    
    for ds in classified_datasets:
        # Count items
        total_items = ds.classified_records or 0
        
        data_items = []
        
        # Fetch clean upload data
        upload_items = CleanDataUpload.query.filter_by(dataset_id=ds.id).limit(50).all() # Limit for performance
        
        for item in upload_items:
            # Get results for this item
            item_results = ClassificationResult.query.filter_by(data_type='upload', data_id=item.id).all()
            if not item_results: continue
            
            models_result = {}
            for res in item_results:
                if res.model_name in visible_algorithms:
                    models_result[res.model_name] = {
                        'prediction': res.prediction,
                        'probability_radikal': res.probability_radikal,
                        'probability_non_radikal': res.probability_non_radikal
                    }
            
            data_items.append({
                'data_id': item.id,
                'username': item.username,
                'content': item.cleaned_content,
                'original_content': item.content,
                'url': item.url,
                'data_type': 'Upload',
                'models': models_result,
                'created_at': item.created_at
            })
            
        # Fetch clean scraper data
        # Need to join with RawDataScraper to filter by dataset_id
        scraper_items = db.session.query(CleanDataScraper).join(
            RawDataScraper, CleanDataScraper.raw_data_scraper_id == RawDataScraper.id
        ).filter(RawDataScraper.dataset_id == ds.id).limit(50).all()
        
        for item in scraper_items:
            # Get results for this item
            item_results = ClassificationResult.query.filter_by(data_type='scraper', data_id=item.id).all()
            if not item_results: continue
            
            models_result = {}
            for res in item_results:
                if res.model_name in visible_algorithms:
                    models_result[res.model_name] = {
                        'prediction': res.prediction,
                        'probability_radikal': res.probability_radikal,
                        'probability_non_radikal': res.probability_non_radikal
                    }
            
            # For scraper data, we need to get some fields from raw_data_scraper relationship if not present in clean model
            # Assuming CleanDataScraper has raw_data_scraper relationship
            username = item.raw_data_scraper.username if item.raw_data_scraper else 'N/A'
            url = item.raw_data_scraper.url if item.raw_data_scraper else None
            original_content = item.raw_data_scraper.content if item.raw_data_scraper else item.content
            
            data_items.append({
                'data_id': item.id,
                'username': username,
                'content': item.cleaned_content,
                'original_content': original_content,
                'url': url,
                'data_type': 'Scraper',
                'models': models_result,
                'created_at': item.created_at
            })
            
        datasets.append({
            'id': ds.id,
            'dataset_name': ds.name,
            'name': ds.name,
            'total_items': total_items,
            'data_items': data_items
        })
    
    return render_template('classification/results.html',
                         results=results,
                         pagination=pagination,
                         total_classifications=total_classifications,
                         total_data_items=total_data_items,
                         total_radikal=total_radikal,
                         total_non_radikal=total_non_radikal,
                         model_stats=model_stats,
                         datasets=datasets,
                         visible_algorithms=visible_algorithms)

@classification_bp.route('/classification/batch')
@login_required
@active_user_required
def batch():
    dataset_id = request.args.get('dataset_id')
    if not dataset_id:
        flash(t('Please select a dataset first'), 'warning')
        return redirect(url_for('classification.index'))
    return render_template('classification/batch.html')

@classification_bp.route('/api/datasets/for-classification')
@login_required
def get_datasets_for_classification():
    try:
        # Filter datasets that are cleaned (status='Cleaned')
        # Users should only select datasets that are ready for classification
        query = Dataset.query.filter(Dataset.status == 'Cleaned')
        
        if not current_user.is_admin():
            # Filter by ownership (uploaded_by)
            query = query.filter(Dataset.uploaded_by == current_user.id)
            
        datasets = query.order_by(desc(Dataset.updated_at)).all()
        
        result = []
        for ds in datasets:
            result.append({
                'id': ds.id,
                'name': ds.name,
                'status': ds.status,
                'total_records': ds.total_records,
                'created_at': ds.created_at.strftime('%Y-%m-%d %H:%M')
            })
            
        return jsonify({'success': True, 'datasets': result})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@classification_bp.route('/api/dataset/<int:id>/clean-data')
@login_required
def get_clean_data(id):
    try:
        dataset = db.session.get(Dataset, id)
        if not dataset:
            return jsonify({'success': False, 'message': 'Dataset not found'}), 404
            
        clean_uploads = CleanDataUpload.query.filter_by(dataset_id=id).all()
        # For scraper, we need to join
        clean_scrapers = db.session.query(CleanDataScraper).join(
            RawDataScraper, CleanDataScraper.raw_data_scraper_id == RawDataScraper.id
        ).filter(RawDataScraper.dataset_id == id).all()
        
        data = []
        for item in clean_uploads:
            data.append({
                'id': item.id,
                'data_type': 'upload',
                'username': item.username,
                'content': item.cleaned_content,
                'full_content': item.raw_data.content if item.raw_data else item.content,
                'url': item.url
            })
            
        for item in clean_scrapers:
            data.append({
                'id': item.id,
                'data_type': 'scraper',
                'username': item.username,
                'content': item.cleaned_content,
                'full_content': item.raw_data_scraper.content if item.raw_data_scraper else item.content,
                'url': item.url
            })
            
        return jsonify({'success': True, 'data': data})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

def process_classification_background(app, dataset_id, user_id):
    with app.app_context():
        try:
            # Update progress
            classification_progress[dataset_id] = {
                'status': 'Processing',
                'processed_items': 0,
                'total_items': 0,
                'progress_percentage': 0
            }
            
            dataset = db.session.get(Dataset, dataset_id)
            if not dataset:
                return

            # Get clean data
            clean_uploads = CleanDataUpload.query.filter_by(dataset_id=dataset_id).all()
            clean_scrapers = db.session.query(CleanDataScraper).join(
                RawDataScraper, CleanDataScraper.raw_data_scraper_id == RawDataScraper.id
            ).filter(RawDataScraper.dataset_id == dataset_id).all()
            
            total_items = len(clean_uploads) + len(clean_scrapers)
            classification_progress[dataset_id]['total_items'] = total_items
            
            if total_items == 0:
                classification_progress[dataset_id]['status'] = 'Completed'
                classification_progress[dataset_id]['progress_percentage'] = 100
                return

            # Get models
            word2vec_model = current_app.config.get('WORD2VEC_MODEL')
            classification_models = current_app.config.get('CLASSIFICATION_MODELS', {})
            visible_algorithms = current_app.config.get('VISIBLE_ALGORITHMS')
            classification_threshold = current_app.config.get('CLASSIFICATION_THRESHOLD', 0.5)
            
            # If no visible algorithms set (None), use all
            if visible_algorithms is None:
                visible_algorithms = list(classification_models.keys())
            
            # Filter models
            active_models = {k: v for k, v in classification_models.items() if k in visible_algorithms and v is not None}
            
            # Create Batch Record
            batch_record = ClassificationBatch(
                dataset_id=dataset_id,
                dataset_name=dataset.name,
                models_used=list(active_models.keys()),
                total_items=total_items,
                status='processing',
                created_by=user_id
            )
            db.session.add(batch_record)
            db.session.commit()
            
            processed = 0
            
            # Use a mutable object to track totals across the inner function
            batch_stats = {'radikal': 0, 'non_radikal': 0}
            
            # Helper function
            def process_item(item, data_type, raw_content):
                # Vectorize (for conventional models)
                text_vector = vectorize_text(item.cleaned_content, word2vec_model)
                
                for model_name, model in active_models.items():
                    # Double check if model is still in visible algorithms
                    if model_name not in visible_algorithms:
                        continue

                    # For IndoBERT, use preprocessed text to match training data
                    if model_name == 'indobert':
                         text_input = preprocess_for_model(raw_content)
                    else:
                         # For logging/other purposes if needed, though they use vector
                         text_input = item.cleaned_content
                    
                    # Classify
                    prediction, probabilities = classify_content(text_vector, model, text_input)
                    
                    # Ensure probabilities are python floats, not numpy types
                    prob_rad = float(probabilities[1]) if len(probabilities) > 1 else 0.0
                    prob_non = float(probabilities[0]) if len(probabilities) > 0 else 0.0

                    # Apply Threshold Logic
                    if prob_rad >= classification_threshold:
                        prediction = 'Radikal'
                    else:
                        prediction = 'Non-Radikal'
                    
                    # Update stats
                    if prediction.lower() == 'radikal':
                        batch_stats['radikal'] += 1
                    else:
                        batch_stats['non_radikal'] += 1
                    
                    # Save result
                    
                    result = ClassificationResult(
                        data_type=data_type,
                        data_id=item.id,
                        model_name=model_name,
                        prediction=prediction,
                        probability_radikal=prob_rad,
                        probability_non_radikal=prob_non,
                        classified_by=user_id
                    )
                    db.session.add(result)
            
            # Process Uploads
            for item in clean_uploads:
                raw_content = item.raw_data.content if item.raw_data else item.content
                process_item(item, 'upload', raw_content)
                processed += 1
                classification_progress[dataset_id]['processed_items'] = processed
                classification_progress[dataset_id]['progress_percentage'] = int((processed / total_items) * 100)
                
            # Process Scrapers
            for item in clean_scrapers:
                raw_content = item.raw_data_scraper.content if item.raw_data_scraper else item.content
                process_item(item, 'scraper', raw_content)
                processed += 1
                classification_progress[dataset_id]['processed_items'] = processed
                classification_progress[dataset_id]['progress_percentage'] = int((processed / total_items) * 100)

            dataset.status = 'Classified'
            dataset.classified_records = total_items
            
            # Update Batch Record
            batch_record.status = 'completed'
            batch_record.completed_at = datetime.utcnow()
            batch_record.total_radikal = batch_stats['radikal']
            batch_record.total_non_radikal = batch_stats['non_radikal']
            
            db.session.commit()
            
            classification_progress[dataset_id]['status'] = 'Completed'
            classification_progress[dataset_id]['progress_percentage'] = 100
            
            generate_activity_log(
                action='classification',
                description=f'Completed classification for dataset: {dataset.name}',
                user_id=user_id,
                icon='fa-brain',
                color='purple'
            )
            
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Error classification background: {e}")
            classification_progress[dataset_id]['status'] = 'Error'
            # Update batch record if it exists
            if 'batch_record' in locals():
                batch_record.status = 'error'
                db.session.commit()

@classification_bp.route('/api/classification/start', methods=['POST'])
@login_required
def start_classification_api():
    data = request.get_json()
    dataset_id = data.get('dataset_id')
    
    if not dataset_id:
        return jsonify({'success': False, 'message': 'Dataset ID required'}), 400
        
    try:
        dataset_id = int(dataset_id)
    except ValueError:
        return jsonify({'success': False, 'message': 'Invalid dataset ID format'}), 400
        
    # Start thread
    thread = threading.Thread(target=process_classification_background, args=(current_app._get_current_object(), dataset_id, current_user.id))
    thread.start()
    
    return jsonify({'success': True, 'message': 'Classification started'})

@classification_bp.route('/api/classification/status/<dataset_id>')
@login_required
def classification_status_api(dataset_id):
    try:
        dataset_id = int(dataset_id)
        # Check memory progress first
        progress = classification_progress.get(dataset_id)
        if progress:
            # If total_items is 0, try to fetch from DB to correct it if the process is just starting
            if progress['total_items'] == 0:
                dataset = db.session.get(Dataset, dataset_id)
                if dataset:
                    # Logic to count total items if not yet set in progress
                    clean_uploads_count = CleanDataUpload.query.filter_by(dataset_id=dataset_id).count()
                    clean_scrapers_count = db.session.query(CleanDataScraper).join(
                        RawDataScraper, CleanDataScraper.raw_data_scraper_id == RawDataScraper.id
                    ).filter(RawDataScraper.dataset_id == dataset_id).count()
                    progress['total_items'] = clean_uploads_count + clean_scrapers_count

            return jsonify({
                'success': True,
                'dataset': {
                    'status': 'Classified' if progress['status'] == 'Completed' else 'Processing',
                    'total_items': progress['total_items'],
                    'processed_items': progress['processed_items'],
                    'progress_percentage': progress['progress_percentage']
                }
            })
        
        # Fallback to DB
        dataset = db.session.get(Dataset, dataset_id)
        if not dataset:
             return jsonify({'success': False, 'message': 'Dataset not found'}), 404
             
        # Calculate total items if not stored (though classified_records should store it)
        total_items = dataset.classified_records or 0
        if total_items == 0:
            # Try to calculate if classified_records is empty but status is done
             clean_uploads_count = CleanDataUpload.query.filter_by(dataset_id=dataset_id).count()
             clean_scrapers_count = db.session.query(CleanDataScraper).join(
                 RawDataScraper, CleanDataScraper.raw_data_scraper_id == RawDataScraper.id
             ).filter(RawDataScraper.dataset_id == dataset_id).count()
             total_items = clean_uploads_count + clean_scrapers_count
             
        return jsonify({
            'success': True,
            'dataset': {
                'status': dataset.status,
                'total_items': total_items,
                'processed_items': total_items if dataset.status == 'Classified' else 0,
                'progress_percentage': 100 if dataset.status == 'Classified' else 0
            }
        })
    except ValueError:
        return jsonify({'success': False, 'message': 'Invalid dataset ID'}), 400

@classification_bp.route('/api/classification/reset-latest', methods=['POST'])
@login_required
def reset_latest_api():
    data = request.get_json()
    dataset_id = data.get('dataset_id')
    if dataset_id:
        try:
            dataset_id = int(dataset_id)
            # Delete existing results for this dataset to avoid duplication
            clean_uploads = CleanDataUpload.query.filter_by(dataset_id=dataset_id).all()
            upload_ids = [c.id for c in clean_uploads]
            
            clean_scrapers = db.session.query(CleanDataScraper).join(
                RawDataScraper, CleanDataScraper.raw_data_scraper_id == RawDataScraper.id
            ).filter(RawDataScraper.dataset_id == dataset_id).all()
            scraper_ids = [c.id for c in clean_scrapers]
            
            if upload_ids:
                ClassificationResult.query.filter(
                    ClassificationResult.data_type == 'upload',
                    ClassificationResult.data_id.in_(upload_ids)
                ).delete(synchronize_session=False)
                
            if scraper_ids:
                ClassificationResult.query.filter(
                    ClassificationResult.data_type == 'scraper',
                    ClassificationResult.data_id.in_(scraper_ids)
                ).delete(synchronize_session=False)
                
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Error resetting results: {e}")
            return jsonify({'success': False, 'message': str(e)}), 500
            
    return jsonify({'success': True})

@classification_bp.route('/api/classification/latest-results')
@login_required
def latest_results_api():
    # Return stats for all results or specific dataset
    dataset_id = request.args.get('dataset_id')
    
    query = ClassificationResult.query
    if dataset_id:
        # Filter by dataset_id
        # Need to join with CleanData to filter by dataset_id
        # This is complex because ClassificationResult is linked to CleanDataUpload/Scraper
        
        # Get IDs of clean data for this dataset
        clean_upload_ids = db.session.query(CleanDataUpload.id).filter_by(dataset_id=dataset_id).all()
        clean_upload_ids = [i[0] for i in clean_upload_ids]
        
        clean_scraper_ids = db.session.query(CleanDataScraper.id).join(
            RawDataScraper, CleanDataScraper.raw_data_scraper_id == RawDataScraper.id
        ).filter(RawDataScraper.dataset_id == dataset_id).all()
        clean_scraper_ids = [i[0] for i in clean_scraper_ids]
        
        query = query.filter(
            ((ClassificationResult.data_type == 'upload') & (ClassificationResult.data_id.in_(clean_upload_ids))) |
            ((ClassificationResult.data_type == 'scraper') & (ClassificationResult.data_id.in_(clean_scraper_ids)))
        )

    total_classifications = query.count()
    total_radikal = query.filter_by(prediction='Radikal').count()
    total_non_radikal = query.filter_by(prediction='Non-Radikal').count()
    
    # Calculate model stats
    model_stats = {}
    
    # Get distinct models actually present in the filtered results
    # This ensures we only show models used for THIS dataset if filtered
    model_names = [r[0] for r in query.with_entities(ClassificationResult.model_name).distinct().all()]
    
    # Filter by visible algorithms if set (None check)
    if visible_algorithms is not None:
        model_names = [m for m in model_names if m in visible_algorithms]
    
    for i, name in enumerate(model_names):
        rad = query.filter_by(model_name=name, prediction='Radikal').count()
        non = query.filter_by(model_name=name, prediction='Non-Radikal').count()
        stats = {'radikal': rad, 'non_radikal': non, 'name': name}
        model_stats[name] = stats
        
        # Map to model1, model2, model3 for frontend compatibility
        if i < 3:
            model_stats[f'model{i+1}'] = stats
            
    # Fallback structure for frontend if fewer than 3 models
    if 'model1' not in model_stats: model_stats['model1'] = {'radikal': 0, 'non_radikal': 0, 'name': 'Model 1'}
    if 'model2' not in model_stats: model_stats['model2'] = {'radikal': 0, 'non_radikal': 0, 'name': 'Model 2'}
    if 'model3' not in model_stats: model_stats['model3'] = {'radikal': 0, 'non_radikal': 0, 'name': 'Model 3'}

    # Calculate unique documents count and majority vote stats
    # Group by data_type and data_id
    from sqlalchemy import func, case
    
    # Subquery to count votes per document
    vote_query = query.with_entities(
        ClassificationResult.data_type,
        ClassificationResult.data_id,
        func.sum(case((ClassificationResult.prediction == 'Radikal', 1), else_=0)).label('rad_votes'),
        func.sum(case((ClassificationResult.prediction == 'Non-Radikal', 1), else_=0)).label('non_rad_votes')
    ).group_by(ClassificationResult.data_type, ClassificationResult.data_id).subquery()
    
    # Query the subquery
    # We want to count how many documents are majority radical vs non-radical
    # Tie-breaking: If votes are equal, we can default to 'non-radikal' or 'radikal'.
    # Here assuming Radikal if rad_votes > non_rad_votes, else Non-Radikal.
    
    # Note: SQLite/Postgres compatibility check. This standard SQL should work.
    
    # Count total unique documents
    total_unique_docs = db.session.query(vote_query).count()
    
    # Count majority radical
    # We need to filter the subquery results
    # Since we can't easily filter on the subquery columns in all ORM versions without defining them,
    # let's iterate or use a simpler approach if the dataset is small. 
    # But for 1000+ items, SQL is better.
    
    total_radikal_docs = db.session.query(vote_query).filter(vote_query.c.rad_votes > vote_query.c.non_rad_votes).count()
    total_non_radikal_docs = total_unique_docs - total_radikal_docs
    
    return jsonify({
        'success': True,
        'results': {
            'total_classifications': total_unique_docs, # Show unique documents count
            'total_predictions': total_classifications, # Show total predictions (raw)
            'total_radikal': total_radikal_docs,
            'radikal_percentage': round(total_radikal_docs/total_unique_docs*100, 1) if total_unique_docs else 0,
            'total_non_radikal': total_non_radikal_docs,
            'non_radikal_percentage': round(total_non_radikal_docs/total_unique_docs*100, 1) if total_unique_docs else 0,
            'model_stats': model_stats,
            'model_count': len(model_names),
            'models': [model_stats[name] for name in model_names]
        }
    })

@classification_bp.route('/api/classify_selected_datasets', methods=['POST'])
@login_required
def classify_selected_datasets():
    """Classify multiple selected datasets"""
    try:
        data = request.get_json()
        dataset_ids = data.get('dataset_ids', [])
        
        if not dataset_ids:
            return jsonify({'success': False, 'message': 'No datasets selected'}), 400
    
        processed_count = 0
        already_classified_count = 0
        no_clean_data_count = 0
        errors = []
        
        # Get models
        word2vec_model = current_app.config.get('WORD2VEC_MODEL')
        classification_models = current_app.config.get('CLASSIFICATION_MODELS', {})
        visible_algorithms = current_app.config.get('VISIBLE_ALGORITHMS')
        classification_threshold = current_app.config.get('CLASSIFICATION_THRESHOLD', 0.5)
        
        # If no visible algorithms set (None), use all
        if visible_algorithms is None:
            visible_algorithms = list(classification_models.keys())
            
        # Filter models
        active_models = {k: v for k, v in classification_models.items() if k in visible_algorithms and v is not None}
        
        # First pass: Validate all datasets
        datasets_to_process = []
        uncleaned_datasets = []
        
        for dataset_id in dataset_ids:
            dataset = db.session.get(Dataset, dataset_id)
            if not dataset:
                errors.append(f'Dataset ID {dataset_id} not found')
                continue

            # Check permission
            has_permission, message, http_status = check_permission_with_feedback(
                current_user, dataset.uploaded_by, 'classify', 'dataset'
            )
            if not has_permission:
                errors.append(message)
                continue
            
            # Check if dataset has clean data
            clean_uploads_count = CleanDataUpload.query.join(
                RawData, CleanDataUpload.raw_data_id == RawData.id
            ).filter(RawData.dataset_id == dataset_id).count()
            
            clean_scrapers_count = db.session.query(CleanDataScraper).join(
                RawDataScraper, CleanDataScraper.raw_data_scraper_id == RawDataScraper.id
            ).filter(RawDataScraper.dataset_id == dataset_id).count()
            
            total_clean_data = clean_uploads_count + clean_scrapers_count
            
            if total_clean_data == 0:
                uncleaned_datasets.append(dataset.name)
            else:
                datasets_to_process.append((dataset, total_clean_data))
                
        # If there are any uncleaned datasets, stop everything and return specific error
        if uncleaned_datasets:
            message = "Bulk classification failed because some datasets have not been cleaned:\n"
            message += "\n".join([f"- {name}" for name in uncleaned_datasets])
            message += "\n\nPlease clean these datasets first."
            return jsonify({'success': False, 'message': message}), 400
            
        # Process valid datasets
        for dataset, total_clean_data in datasets_to_process:
            dataset_id = dataset.id
            try:
                # Fetch data again (or could have stored it, but IDs are safer)
                clean_uploads = CleanDataUpload.query.join(
                    RawData, CleanDataUpload.raw_data_id == RawData.id
                ).filter(RawData.dataset_id == dataset_id).all()
                
                clean_scrapers = db.session.query(CleanDataScraper).join(
                    RawDataScraper, CleanDataScraper.raw_data_scraper_id == RawDataScraper.id
                ).filter(RawDataScraper.dataset_id == dataset_id).all()
                
                # Create Batch Record
                batch_record = ClassificationBatch(
                    dataset_id=dataset_id,
                    dataset_name=dataset.name,
                    models_used=list(active_models.keys()),
                    total_items=total_clean_data,
                    status='processing',
                    created_by=current_user.id
                )
                db.session.add(batch_record)
                
                batch_stats = {'radikal': 0, 'non_radikal': 0}

                # Process Clean Data Uploads
                for item in clean_uploads:
                    # Vectorize
                    text_vector = vectorize_text(item.cleaned_content, word2vec_model)
                    
                    # Classify with active models
                    for model_name, model in active_models.items():
                        # Double check if model is still in visible algorithms
                        if model_name not in visible_algorithms:
                            continue
                        
                        # Determine text to use
                        text_input = item.cleaned_content
                        # For IndoBERT, use preprocessed text to match training data (Stemmed + Stopwords removed)
                        if model_name == 'indobert':
                            # Get raw content
                            raw_content_val = item.raw_data.content if item.raw_data else item.content
                            # Apply preprocessing including stemming
                            text_input = preprocess_for_model(raw_content_val)
                            
                        prediction, probabilities = classify_content(text_vector, model, text_input)
                        
                        # Ensure probabilities are python floats, not numpy types
                        prob_rad = float(probabilities[1]) if len(probabilities) > 1 else 0.0
                        prob_non = float(probabilities[0]) if len(probabilities) > 0 else 0.0

                        # Apply Threshold Logic
                        if prob_rad >= classification_threshold:
                            prediction = 'Radikal'
                        else:
                            prediction = 'Non-Radikal'
                        
                        # Update stats
                        if prediction.lower() == 'radikal':
                            batch_stats['radikal'] += 1
                        else:
                            batch_stats['non_radikal'] += 1
                        
                        # Save result
                        
                        result = ClassificationResult(
                            data_type='upload',
                            data_id=item.id,
                            model_name=model_name,
                            prediction=prediction,
                            probability_radikal=prob_rad,
                            probability_non_radikal=prob_non,
                            classified_by=current_user.id
                        )
                        db.session.add(result)

                # Process Clean Data Scraper
                for item in clean_scrapers:
                    # Vectorize
                    text_vector = vectorize_text(item.cleaned_content, word2vec_model)
                    
                    # Classify with active models
                    for model_name, model in active_models.items():
                        # Double check if model is still in visible algorithms
                        if model_name not in visible_algorithms:
                            continue
                        
                        # Determine text to use
                        text_input = item.cleaned_content
                        # For IndoBERT, use preprocessed text to match training data (Stemmed + Stopwords removed)
                        if model_name == 'indobert':
                             # Get raw content
                             raw_content_val = item.raw_data_scraper.content if item.raw_data_scraper else item.content
                             # Apply preprocessing including stemming
                             text_input = preprocess_for_model(raw_content_val)

                        prediction, probabilities = classify_content(text_vector, model, text_input)
                        
                        # Ensure probabilities are python floats, not numpy types
                        prob_rad = float(probabilities[1]) if len(probabilities) > 1 else 0.0
                        prob_non = float(probabilities[0]) if len(probabilities) > 0 else 0.0

                        # Apply Threshold Logic
                        if prob_rad >= classification_threshold:
                            prediction = 'Radikal'
                        else:
                            prediction = 'Non-Radikal'
                        
                        # Update stats
                        if prediction.lower() == 'radikal':
                            batch_stats['radikal'] += 1
                        else:
                            batch_stats['non_radikal'] += 1
                        
                        # Save result
                        
                        result = ClassificationResult(
                            data_type='scraper',
                            data_id=item.id,
                            model_name=model_name,
                            prediction=prediction,
                            probability_radikal=prob_rad,
                            probability_non_radikal=prob_non,
                            classified_by=current_user.id
                        )
                        db.session.add(result)
                
                # Update dataset status
                dataset.status = 'Classified'
                dataset.classified_records = total_clean_data
                
                # Update Batch Record
                batch_record.status = 'completed'
                batch_record.completed_at = datetime.utcnow()
                batch_record.total_radikal = batch_stats['radikal']
                batch_record.total_non_radikal = batch_stats['non_radikal']
                
                processed_count += 1
                
            except Exception as e:
                errors.append(f'Error in dataset {dataset_id}: {str(e)}')
                if 'batch_record' in locals():
                    batch_record.status = 'error'
                continue
        
        db.session.commit()
        
        if processed_count > 0:
            generate_activity_log(
                 action='classification',
                 description=f'Completed bulk classification for {processed_count} datasets',
                 user_id=current_user.id,
                 icon='fa-brain',
                 color='purple'
             )
        
        return jsonify({
            'success': True, 
            'processed': processed_count,
            'already_classified': already_classified_count,
            'no_clean_data': no_clean_data_count,
            'message': 'Process completed',
            'errors': errors
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': f'Error: {str(e)}'}), 500

@classification_bp.route('/api/export/classification-results', methods=['POST'])
@login_required
@active_user_required
def export_classification_results():
    try:
        data = request.get_json()
        export_format = data.get('format', 'csv')
        dataset_id = data.get('dataset_id')
        
        # Get visible algorithms
        visible_algorithms = current_app.config.get('VISIBLE_ALGORITHMS')
        classification_models = current_app.config.get('CLASSIFICATION_MODELS', {})
        
        # If no visible algorithms set (None), use all
        if visible_algorithms is None:
            visible_algorithms = list(classification_models.keys())
            
        # Determine datasets to fetch
        target_datasets = []
        if dataset_id:
            ds = db.session.get(Dataset, dataset_id)
            if ds:
                # Check permission
                if not current_user.is_admin() and ds.uploaded_by != current_user.id:
                    return jsonify({'success': False, 'message': 'Permission denied'}), 403
                target_datasets.append(ds)
        else:
            # Fetch all datasets available to user
            query = Dataset.query.filter(Dataset.status == 'Classified')
            if not current_user.is_admin():
                query = query.filter(Dataset.uploaded_by == current_user.id)
            target_datasets = query.order_by(desc(Dataset.updated_at)).all()
            
        export_data = []
        
        for ds in target_datasets:
            # Fetch clean upload data
            clean_uploads = CleanDataUpload.query.filter_by(dataset_id=ds.id).all()
            
            # Fetch clean scraper data
            clean_scrapers = db.session.query(CleanDataScraper).join(
                RawDataScraper, CleanDataScraper.raw_data_scraper_id == RawDataScraper.id
            ).filter(RawDataScraper.dataset_id == ds.id).all()
            
            # Combine items
            items = []
            for item in clean_uploads:
                items.append({
                    'id': item.id,
                    'type': 'upload',
                    'username': item.username,
                    'content': item.cleaned_content,
                    'original_content': item.raw_data.content if item.raw_data else item.content,
                    'url': item.url,
                    'created_at': item.created_at
                })
                
            for item in clean_scrapers:
                items.append({
                    'id': item.id,
                    'type': 'scraper',
                    'username': item.username,
                    'content': item.cleaned_content,
                    'original_content': item.raw_data_scraper.content if item.raw_data_scraper else item.content,
                    'url': item.url,
                    'created_at': item.created_at
                })
                
            # Fetch all results for these items
            if not items:
                continue
                
            upload_ids = [i['id'] for i in items if i['type'] == 'upload']
            scraper_ids = [i['id'] for i in items if i['type'] == 'scraper']
            
            results_query = ClassificationResult.query.filter(
                ((ClassificationResult.data_type == 'upload') & (ClassificationResult.data_id.in_(upload_ids))) |
                ((ClassificationResult.data_type == 'scraper') & (ClassificationResult.data_id.in_(scraper_ids)))
            )
            
            # Filter by visible algorithms
            if visible_algorithms:
                results_query = results_query.filter(ClassificationResult.model_name.in_(visible_algorithms))
                
            all_results = results_query.all()
            
            # Map results to items
            # Key: f"{data_type}_{data_id}" -> {model_name: result}
            results_map = {}
            for res in all_results:
                key = f"{res.data_type}_{res.data_id}"
                if key not in results_map:
                    results_map[key] = {}
                results_map[key][res.model_name] = res
                
            # Build export rows
            for item in items:
                row = {
                    'Dataset': ds.name,
                    'Username': item['username'],
                    'Content': item['content'],
                    'Original Content': item['original_content'],
                    'URL': item['url'],
                    'Data Type': item['type'],
                    'Date': item['created_at'].strftime('%Y-%m-%d %H:%M:%S') if item['created_at'] else ''
                }
                
                key = f"{item['type']}_{item['id']}"
                item_results = results_map.get(key, {})
                
                # Only add data for models that actually have results AND are visible
                for model_name, res in item_results.items():
                    if model_name in visible_algorithms:
                        model_col = model_name.replace('_', ' ').title()
                        row[f'{model_col} Prediction'] = res.prediction
                        row[f'{model_col} Probability'] = f"{max(res.probability_radikal, res.probability_non_radikal):.4f}"
                        
                export_data.append(row)
                
        if not export_data:
            return jsonify({'success': False, 'message': 'No data to export'}), 404
            
        # Create DataFrame
        df = pd.DataFrame(export_data)
        
        # Reorder columns to match visible_algorithms order and ensure consistent structure
        base_columns = ['Dataset', 'Username', 'Content', 'Original Content', 'URL', 'Data Type', 'Date']
        
        # Identify dynamic model columns present in the dataframe
        dynamic_cols = [c for c in df.columns if c not in base_columns]
        
        # Sort dynamic columns based on visible_algorithms order
        def get_model_sort_key(col_name):
            # Map column name back to model index
            for i, model in enumerate(visible_algorithms):
                display_name = model.replace('_', ' ').title()
                if col_name.startswith(display_name):
                    # Prioritize Prediction then Probability
                    is_prob = 'Probability' in col_name
                    return i * 10 + (1 if is_prob else 0)
            return 999

        dynamic_cols.sort(key=get_model_sort_key)
        
        # Final column list
        final_cols = base_columns + dynamic_cols
        
        # Reindex to enforce order (only includes columns that actually have data)
        df = df[final_cols]
        
        # Fill NaNs with '-' for cleaner look (or empty string if preferred, but - implies "not applicable/missing")
        df.fillna('-', inplace=True)
        
        # Export
        output = io.BytesIO()
        if export_format == 'csv':
            df.to_csv(output, index=False, encoding='utf-8-sig') # utf-8-sig for Excel compatibility
            mimetype = 'text/csv'
            filename = f'classification_results_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv'
        else: # excel
            # Try using openpyxl
            try:
                with pd.ExcelWriter(output, engine='openpyxl') as writer:
                    df.to_excel(writer, index=False, sheet_name='Results')
                mimetype = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
                filename = f'classification_results_{datetime.now().strftime("%Y%m%d_%H%M%S")}.xlsx'
            except ImportError:
                 # Fallback to CSV if openpyxl is missing
                 current_app.logger.warning("openpyxl not found, falling back to CSV")
                 output = io.BytesIO()
                 df.to_csv(output, index=False, encoding='utf-8-sig')
                 mimetype = 'text/csv'
                 filename = f'classification_results_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv'
        
        output.seek(0)
        
        return send_file(
            output,
            mimetype=mimetype,
            as_attachment=True,
            download_name=filename
        )
        
    except Exception as e:
        current_app.logger.error(f"Export error: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500
