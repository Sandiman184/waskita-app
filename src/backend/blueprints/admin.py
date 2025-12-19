import threading
import uuid
import time
from flask import Blueprint, render_template, request, flash, redirect, url_for, jsonify, current_app, session
from flask_login import login_required, current_user
from sqlalchemy import text
from utils.utils import admin_required
from models.models import db, User, Dataset, RawData, RawDataScraper, ClassificationResult, DatasetStatistics, CleanDataUpload, CleanDataScraper, UserActivity, ManualClassificationHistory, ClassificationBatch, TrainingRun, TrainingMetric
from utils.training_utils import train_models
from utils.settings_utils import save_system_settings
import pandas as pd
import os
import shutil
import json
import io
import zipfile
from datetime import datetime
from flask import send_file
from urllib.parse import urlparse

from utils.i18n import t

admin_bp = Blueprint('admin', __name__)

# Global dictionary to store training tasks
# task_id -> {status, progress, message, results, error}
training_tasks = {}

# Global dictionary to store upload tasks
# upload_id -> {status, progress, message, error, timestamp}
upload_tasks = {}

def process_indobert_upload(upload_id, temp_dir, final_filename, user_id):
    """Background task to process uploaded IndoBERT model"""
    current_app.logger.info(f"Starting IndoBERT processing task: {upload_id}")
    try:
        if upload_id not in upload_tasks:
            current_app.logger.error(f"Upload ID {upload_id} not found in tasks")
            return

        upload_tasks[upload_id]['status'] = 'processing'
        upload_tasks[upload_id]['message'] = 'Assembling file chunks...'
        upload_tasks[upload_id]['progress'] = 10
        current_app.logger.info(f"Task {upload_id}: Assembling chunks...")

        # Assemble chunks
        assembled_file_path = os.path.join(temp_dir, final_filename)
        
        # Check temp dir
        if not os.path.exists(temp_dir):
             raise ValueError(f"Temporary directory not found: {temp_dir}")

        # Check cancellation
        if upload_tasks[upload_id].get('status') == 'cancelled':
             current_app.logger.warning(f"Task {upload_id}: Cancelled by user during chunk assembly")
             return

        with open(assembled_file_path, 'wb') as outfile:
            # List parts
            parts = sorted([f for f in os.listdir(temp_dir) if f.startswith('part_')], key=lambda x: int(x.split('_')[1]))
            total_parts = len(parts)
            current_app.logger.info(f"Task {upload_id}: Found {total_parts} chunks")
            
            if total_parts == 0:
                raise ValueError("No file chunks found")

            for i, part in enumerate(parts):
                # Check cancellation in loop
                if i % 5 == 0 and upload_tasks[upload_id].get('status') == 'cancelled':
                     current_app.logger.warning(f"Task {upload_id}: Cancelled by user during assembly")
                     return

                part_path = os.path.join(temp_dir, part)
                with open(part_path, 'rb') as infile:
                    outfile.write(infile.read())
                # Update progress during assembly (10-50%)
                if total_parts > 0:
                    progress = 10 + int((i / total_parts) * 40)
                    upload_tasks[upload_id]['progress'] = progress
        
        current_app.logger.info(f"Task {upload_id}: Assembly complete. Cleaning up chunks...")
        
        # Cleanup parts
        for part in parts:
            try:
                os.remove(os.path.join(temp_dir, part))
            except:
                pass

        upload_tasks[upload_id]['message'] = 'Validating ZIP file...'
        upload_tasks[upload_id]['progress'] = 60

        # Validate ZIP
        if not zipfile.is_zipfile(assembled_file_path):
            raise ValueError("Assembled file is not a valid ZIP")
            
        current_app.logger.info(f"Task {upload_id}: ZIP validation passed")

        upload_tasks[upload_id]['message'] = 'Extracting model files...'
        upload_tasks[upload_id]['progress'] = 70

        # Extract
        indobert_path = current_app.config.get('MODEL_INDOBERT_PATH')
        current_app.logger.info(f"Task {upload_id}: Extracting to {indobert_path}")
        
        # Clear existing directory
        if os.path.exists(indobert_path):
            shutil.rmtree(indobert_path)
        os.makedirs(indobert_path, exist_ok=True)
        
        with zipfile.ZipFile(assembled_file_path, 'r') as zip_ref:
            # Progress during extraction (70-90%)
            file_list = zip_ref.namelist()
            total_files = len(file_list)
            
            # Detect root folder (if all files are in a single top-level folder)
            root_folder = None
            if total_files > 0:
                first_file = file_list[0]
                if '/' in first_file:
                    potential_root = first_file.split('/')[0]
                    # Check if all files start with this folder
                    if all(f.startswith(potential_root + '/') for f in file_list if '/' in f):
                         root_folder = potential_root

            current_app.logger.info(f"Task {upload_id}: Root folder detected: {root_folder}")

            for i, file_info in enumerate(zip_ref.infolist()):
                # Check cancellation
                if i % 50 == 0 and upload_tasks[upload_id].get('status') == 'cancelled':
                     current_app.logger.warning(f"Task {upload_id}: Cancelled by user during extraction")
                     return

                # Skip directories
                if file_info.is_dir():
                    continue
                    
                filename = file_info.filename
                
                # Strip root folder if exists
                if root_folder and filename.startswith(root_folder + '/'):
                    target_filename = filename[len(root_folder) + 1:]
                else:
                    target_filename = filename
                
                # Skip invalid filenames (e.g. __MACOSX)
                if target_filename.startswith('__MACOSX') or target_filename.startswith('.'):
                    continue
                    
                # Construct target path
                target_path = os.path.join(indobert_path, target_filename)
                
                # Ensure directory exists
                os.makedirs(os.path.dirname(target_path), exist_ok=True)
                
                # Extract file
                with zip_ref.open(filename) as source, open(target_path, "wb") as target:
                    shutil.copyfileobj(source, target)

                if i % 10 == 0 and total_files > 0:
                     progress = 70 + int((i / total_files) * 20)
                     upload_tasks[upload_id]['progress'] = progress
        
        current_app.logger.info(f"Task {upload_id}: Extraction complete")

        # Final cleanup
        try:
            os.remove(assembled_file_path)
            os.rmdir(temp_dir)
        except Exception as cleanup_err:
            current_app.logger.warning(f"Task {upload_id}: Cleanup warning: {cleanup_err}")
            
        # Log activity
        try:
            activity = UserActivity(
                user_id=user_id,
                action='model_update',
                description='Updated IndoBERT model',
                details=f'Filename: {final_filename}',
                icon='fa-brain',
                color='success'
            )
            db.session.add(activity)
            db.session.commit()
            current_app.logger.info(f"Task {upload_id}: Activity logged")
        except Exception as log_err:
            current_app.logger.error(f"Failed to log upload activity: {log_err}")
            db.session.rollback()

        upload_tasks[upload_id]['status'] = 'completed'
        upload_tasks[upload_id]['progress'] = 100
        upload_tasks[upload_id]['message'] = 'Model successfully installed'
        current_app.logger.info(f"Task {upload_id}: Process completed successfully")
        
    except Exception as e:
        if upload_id in upload_tasks:
             # Don't overwrite cancelled status unless it's a real failure
             if upload_tasks[upload_id].get('status') != 'cancelled':
                upload_tasks[upload_id]['status'] = 'failed'
                upload_tasks[upload_id]['error'] = str(e)
        
        current_app.logger.error(f"IndoBERT upload processing failed: {e}", exc_info=True)
        # Cleanup
        try:
            if os.path.exists(temp_dir):
                shutil.rmtree(temp_dir)
        except:
            pass
    finally:
        # Final check: If cancelled, ensure temp dir is gone
        if upload_id in upload_tasks and upload_tasks[upload_id].get('status') == 'cancelled':
            try:
                if os.path.exists(temp_dir):
                    shutil.rmtree(temp_dir)
            except:
                pass
        
        # Ensure DB session is closed if created in thread
        db.session.remove()

@admin_bp.route('/admin/upload/init', methods=['POST'])
@login_required
@admin_required
def upload_init():
    """
    Initialize a chunked file upload session.
    
    This endpoint is part of the chunked upload mechanism designed to handle large file uploads
    (e.g., IndoBERT > 500MB, Word2Vec > 1GB) that exceed standard web server limits.
    
    Technical Details:
    - Creates a temporary directory in `UPLOAD_FOLDER/temp_chunks/<upload_id>`.
    - Returns a unique `upload_id` to be used in subsequent chunk uploads.
    - Used for both 'indobert' (.zip) and 'word2vec' (.joblib) model types.
    
    Returns:
        JSON: {'upload_id': str} on success, or error message.
    """
    filename = request.form.get('filename')
    model_type = request.form.get('model_type', 'indobert') # Default to indobert for backward compatibility
    
    if not filename:
        return jsonify({'error': 'Filename required'}), 400
        
    upload_id = str(uuid.uuid4())
    temp_dir = os.path.join(current_app.config['UPLOAD_FOLDER'], 'temp_chunks', upload_id)
    os.makedirs(temp_dir, exist_ok=True)
    
    upload_tasks[upload_id] = {
        'status': 'uploading',
        'progress': 0,
        'message': 'Upload initialized',
        'filename': filename,
        'model_type': model_type,
        'temp_dir': temp_dir,
        'timestamp': time.time()
    }
    
    return jsonify({'upload_id': upload_id})

@admin_bp.route('/admin/upload/chunk', methods=['POST'])
@login_required
@admin_required
def upload_chunk():
    """
    Handle the upload of a single file chunk.
    
    This function accepts a chunk of a file and saves it to the temporary directory
    associated with the `upload_id`.
    
    Mechanisms:
    - Frontend splits files into 2MB chunks (configurable).
    - Chunks are named `part_<index>`.
    - Supports retry logic on the frontend (up to 10 retries with exponential backoff).
    - Timeout per chunk is extended to handle network jitter.
    
    Args:
        upload_id (form): The ID of the upload session.
        chunk_index (form): The sequence number of the chunk (0-based).
        chunk (file): The file data for this chunk.
        
    Returns:
        JSON: {'success': True} on success.
    """
    upload_id = request.form.get('upload_id')
    chunk_index = request.form.get('chunk_index')
    chunk = request.files.get('chunk')
    
    if not upload_id or chunk_index is None or not chunk:
        current_app.logger.error(f"Missing parameters for upload_chunk: upload_id={upload_id}, chunk_index={chunk_index}, chunk={chunk}")
        return jsonify({'error': 'Missing parameters'}), 400
        
    if upload_id not in upload_tasks:
        current_app.logger.error(f"Invalid upload ID in upload_chunk: {upload_id}")
        return jsonify({'error': 'Invalid upload ID'}), 404
        
    task = upload_tasks[upload_id]
    chunk_path = os.path.join(task['temp_dir'], f'part_{chunk_index}')
    
    try:
        chunk.save(chunk_path)
        # current_app.logger.debug(f"Chunk {chunk_index} saved for {upload_id}")
    except Exception as e:
        current_app.logger.error(f"Failed to save chunk {chunk_index} for {upload_id}: {e}")
        return jsonify({'error': str(e)}), 500
    
    return jsonify({'success': True})

def process_generic_model_upload(upload_id, temp_dir, final_filename, model_type, user_id):
    """
    Background task to process uploaded generic model (Word2Vec, etc) after chunk assembly.
    
    This function is triggered after all chunks are uploaded. It performs the following:
    1.  **Assembly**: Combines `part_0`, `part_1`, ... into the final file.
    2.  **Validation**: Basic validation (existence of chunks).
    3.  **Installation**: 
        - Determines target path based on `model_type` from configuration.
        - Backs up/removes the old model.
        - Moves the assembled file to the target location.
    4.  **Cleanup**: Removes temporary chunks and directories.
    5.  **Logging**: Records the activity in `UserActivity`.
    
    Limits:
    - Supports files up to 10GB (configured via `MAX_CONTENT_LENGTH` and Nginx).
    
    Args:
        upload_id (str): The upload session ID.
        temp_dir (str): Path to temporary directory containing chunks.
        final_filename (str): Name of the final assembled file.
        model_type (str): Type of model (e.g., 'word2vec', 'svm').
        user_id (int): ID of the user performing the upload.
    """
    current_app.logger.info(f"Starting generic model processing task: {upload_id}, type: {model_type}")
    try:
        if upload_id not in upload_tasks:
            current_app.logger.error(f"Upload ID {upload_id} not found in tasks")
            return

        upload_tasks[upload_id]['status'] = 'processing'
        upload_tasks[upload_id]['message'] = 'Assembling file chunks...'
        upload_tasks[upload_id]['progress'] = 10
        
        # Assemble chunks
        assembled_file_path = os.path.join(temp_dir, final_filename)
        
        if not os.path.exists(temp_dir):
             raise ValueError(f"Temporary directory not found: {temp_dir}")
        
        # Check cancellation
        if upload_tasks[upload_id].get('status') == 'cancelled':
             return

        # Map model types to config paths
        model_paths = {
            'word2vec': current_app.config.get('WORD2VEC_MODEL_PATH'),
            'label_encoder': current_app.config.get('LABEL_ENCODER_PATH'),
            'naive_bayes': current_app.config.get('MODEL_NAIVE_BAYES_PATH'),
            'svm': current_app.config.get('MODEL_SVM_PATH'),
            'random_forest': current_app.config.get('MODEL_RANDOM_FOREST_PATH'),
            'logistic_regression': current_app.config.get('MODEL_LOGISTIC_REGRESSION_PATH'),
            'decision_tree': current_app.config.get('MODEL_DECISION_TREE_PATH'),
            'knn': current_app.config.get('MODEL_KNN_PATH')
        }
        
        target_path = model_paths.get(model_type)
        if not target_path:
            raise ValueError(f"Path for model {model_type} is not configured")

        # Ensure absolute path to avoid relative path issues
        if not os.path.isabs(target_path):
            target_path = os.path.abspath(target_path)
            
        current_app.logger.info(f"Task {upload_id}: Target path resolved to {target_path}")

        # Unload models if we are updating word2vec or classifiers to release locks
        if model_type == 'word2vec' or model_type in model_paths:
             current_app.logger.info(f"Unloading models before updating {model_type}...")
             if hasattr(current_app, 'unload_models'):
                 current_app.unload_models()
             else:
                 # Fallback if method not attached
                 current_app.config['WORD2VEC_MODEL'] = None
                 import gc
                 gc.collect()

        with open(assembled_file_path, 'wb') as outfile:
            parts = sorted([f for f in os.listdir(temp_dir) if f.startswith('part_')], key=lambda x: int(x.split('_')[1]))
            total_parts = len(parts)
            
            if total_parts == 0:
                raise ValueError("No file chunks found")

            for i, part in enumerate(parts):
                part_path = os.path.join(temp_dir, part)
                with open(part_path, 'rb') as infile:
                    outfile.write(infile.read())
                
                if total_parts > 0:
                    progress = 10 + int((i / total_parts) * 80) # 10-90%
                    upload_tasks[upload_id]['progress'] = progress
        
        # Cleanup parts
        for part in parts:
            try:
                os.remove(os.path.join(temp_dir, part))
            except:
                pass
                
        upload_tasks[upload_id]['message'] = 'Installing model...'
        upload_tasks[upload_id]['progress'] = 90
        
        # Move to target location
        os.makedirs(os.path.dirname(target_path), exist_ok=True)
        
        # Replace file logic with Pending Update Strategy for Windows
        # If immediate replacement fails, we queue it as a pending update.
        
        try:
            # Try immediate replacement first
            if os.path.exists(target_path):
                # Try simple remove
                try:
                    os.remove(target_path)
                except OSError:
                    # If remove fails, it's locked.
                    pass 
            
            # Try move
            shutil.move(assembled_file_path, target_path)
            
            # Reload models if successful
            current_app.logger.info("Reloading models after update...")
            if hasattr(current_app, 'load_models'):
                current_app.load_models()
                
            upload_tasks[upload_id]['message'] = 'Model successfully installed'
            
        except OSError as e:
            # Fallback: Pending Update
            current_app.logger.warning(f"Immediate model replacement failed: {e}. Queueing as pending update.")
            
            pending_path = target_path + '.pending'
            if os.path.exists(pending_path):
                try:
                    os.remove(pending_path)
                except:
                    pass
            
            shutil.move(assembled_file_path, pending_path)
            
            upload_tasks[upload_id]['message'] = 'Upload complete. PLEASE RESTART SERVER to apply changes.'
            # We mark as completed so the UI stops polling, but with a warning message.
        
        # Cleanup temp dir
        try:
            os.rmdir(temp_dir)
        except:
            pass
            
        # Log activity
        try:
            activity = UserActivity(
                user_id=user_id,
                action='model_update',
                description=f'Updated {model_type} model',
                details=f'Filename: {final_filename}',
                icon='fa-cubes',
                color='success'
            )
            db.session.add(activity)
            db.session.commit()
        except Exception as log_err:
            current_app.logger.error(f"Failed to log upload activity: {log_err}")
            db.session.rollback()

        upload_tasks[upload_id]['status'] = 'completed'
        upload_tasks[upload_id]['progress'] = 100
        upload_tasks[upload_id]['message'] = 'Model successfully installed'
        
    except Exception as e:
        if upload_id in upload_tasks:
             if upload_tasks[upload_id].get('status') != 'cancelled':
                upload_tasks[upload_id]['status'] = 'failed'
                upload_tasks[upload_id]['error'] = str(e)
        
        current_app.logger.error(f"Generic upload processing failed: {e}", exc_info=True)
        try:
            if os.path.exists(temp_dir):
                shutil.rmtree(temp_dir)
        except:
            pass
    finally:
        # Final cleanup for cancelled tasks
        if upload_id in upload_tasks and upload_tasks[upload_id].get('status') == 'cancelled':
            try:
                if os.path.exists(temp_dir):
                    shutil.rmtree(temp_dir)
            except:
                pass
        db.session.remove()

@admin_bp.route('/admin/upload/finish', methods=['POST'])
@login_required
@admin_required
def upload_finish():
    """
    Finalize the chunked upload process.
    
    Triggered when the frontend has successfully uploaded all chunks.
    This starts a background thread to process (assemble and install) the uploaded files.
    
    Process:
    1.  Verifies `upload_id`.
    2.  Updates status to 'pending_processing'.
    3.  Spawns a background thread running `process_indobert_upload` or `process_generic_model_upload`
        depending on the `model_type`.
    
    Returns:
        JSON: {'success': True} indicating processing has started.
    """
    upload_id = request.form.get('upload_id')
    if not upload_id or upload_id not in upload_tasks:
        return jsonify({'error': 'Invalid upload ID'}), 404
        
    task = upload_tasks[upload_id]
    
    # Race condition check: If already cancelled, do not proceed
    if task.get('status') == 'cancelled':
        return jsonify({'error': 'Upload cancelled'}), 400
        
    task['status'] = 'pending_processing'
    model_type = task.get('model_type', 'indobert')
    
    # Start background processing with app context
    app = current_app._get_current_object()
    user_id = current_user.id
    
    def thread_with_context(app, upload_id, temp_dir, filename, user_id, model_type):
        try:
            with app.app_context():
                if model_type == 'indobert':
                    process_indobert_upload(upload_id, temp_dir, filename, user_id)
                else:
                    process_generic_model_upload(upload_id, temp_dir, filename, model_type, user_id)
        except Exception as e:
            if upload_id in upload_tasks:
                upload_tasks[upload_id]['status'] = 'failed'
                upload_tasks[upload_id]['error'] = f"Thread Error: {str(e)}"
            app.logger.error(f"Background upload thread crashed: {e}", exc_info=True)
            
    thread = threading.Thread(target=thread_with_context,
                            args=(app, upload_id, task['temp_dir'], task['filename'], user_id, model_type))
    thread.start()
    
    return jsonify({'success': True})

@admin_bp.route('/admin/upload/cancel', methods=['POST'])
@login_required
@admin_required
def upload_cancel():
    """
    Cancel an ongoing upload task and clean up resources.
    """
    upload_id = request.form.get('upload_id')
    if not upload_id or upload_id not in upload_tasks:
        return jsonify({'error': 'Invalid upload ID'}), 404
    
    # Mark as cancelled
    # The background threads check this flag periodically and will abort
    upload_tasks[upload_id]['status'] = 'cancelled'
    upload_tasks[upload_id]['message'] = 'Upload cancelled by user'
    
    # Immediate cleanup if it was just uploading chunks (not yet processing)
    temp_dir = upload_tasks[upload_id].get('temp_dir')
    if temp_dir and os.path.exists(temp_dir):
        try:
            # We don't delete immediately if processing is active to avoid race conditions,
            # but if it's just 'uploading' state, we can zap it.
            # Actually, safe to leave for the thread to clean up if running,
            # or clean up now if no thread.
            pass 
        except Exception as e:
            current_app.logger.error(f"Failed to cleanup cancelled upload: {e}")
            
    return jsonify({'success': True, 'message': 'Upload cancelled'})


@admin_bp.route('/admin/upload/status/<upload_id>')
@login_required
@admin_required
def upload_status(upload_id):
    if upload_id not in upload_tasks:
        return jsonify({'error': 'Not found'}), 404
    return jsonify(upload_tasks[upload_id])


@admin_bp.route('/admin/system/restart', methods=['POST'])
@login_required
@admin_required
def restart_server():
    """
    Restart the application server to reload models and apply changes.
    Works for both Flask Dev Server (reloader) and Gunicorn (worker restart).
    """
    try:
        current_app.logger.warning(f"Server restart initiated by user: {current_user.username}")
        
        # 1. Helper function to restart
        # Must pass app object explicitly because thread runs outside request context
        app = current_app._get_current_object()
        
        def do_restart(app_logger):
            import time
            import sys
            import os
            
            # Allow the response to be sent back to client first
            time.sleep(1)
            
            if os.environ.get('WERKZEUG_RUN_MAIN') == 'true':
                # Flask Development Server
                app_logger.info("Restarting Flask Dev Server...")
                try:
                    # Touch app.py to trigger reload
                    app_file = os.path.join(os.getcwd(), 'app.py')
                    if os.path.exists(app_file):
                        os.utime(app_file, None)
                    else:
                         sys.exit(0)
                except:
                    sys.exit(0)
            else:
                # Gunicorn / Production
                app_logger.info("Restarting Gunicorn Worker...")
                sys.exit(0)

        # 2. Run restart in a separate thread
        thread = threading.Thread(target=do_restart, args=(app.logger,))
        thread.start()
        
        return jsonify({'success': True, 'message': 'Server is restarting... Please wait about 5-10 seconds.'})
        
    except Exception as e:
        current_app.logger.error(f"Restart failed: {e}")
        return jsonify({'error': str(e)}), 500

@admin_bp.route('/admin/model/retrain/status/<task_id>')
@login_required
@admin_required
def get_training_status(task_id):
    task = training_tasks.get(task_id)
    if not task:
        return jsonify({'error': 'Task not found'}), 404
    return jsonify(task)

def run_training_async(app, task_id, df, word2vec_model, user_id, filename, col_text, col_label, save_models):
    """Background task for training"""
    with app.app_context():
        try:
            def progress_callback(message, percent):
                training_tasks[task_id]['message'] = message
                training_tasks[task_id]['progress'] = percent
            
            results = train_models(
                df=df,
                word2vec_model=word2vec_model,
                save_models=save_models,
                user_id=user_id,
                filename=filename,
                col_text=col_text,
                col_label=col_label,
                progress_callback=progress_callback
            )
            
            training_tasks[task_id]['status'] = 'completed'
            training_tasks[task_id]['progress'] = 100
            training_tasks[task_id]['message'] = 'Training completed successfully!'
            training_tasks[task_id]['results'] = results
            
            # If temp training (save_models=False), store needed data in task for retrieval
            if not save_models:
                 # We need to persist filename etc to session later when user confirms
                 # But we can't write to session from thread.
                 # The frontend will have to resend or we assume filename is valid.
                 pass
            
        except Exception as e:
            training_tasks[task_id]['status'] = 'error'
            training_tasks[task_id]['error'] = str(e)
            current_app.logger.error(f"Async training error: {e}")

@admin_bp.route('/admin')
@admin_bp.route('/admin/users')
@login_required
@admin_required
def user_management():
    """Halaman manajemen pengguna"""
    users = User.query.order_by(User.created_at.desc()).all()
    current_time = datetime.now()
    
    # Hitung statistik
    total_users = len(users)
    active_users = sum(1 for u in users if u.is_active)
    admin_users = sum(1 for u in users if u.role == 'admin')
    inactive_users = total_users - active_users
    
    return render_template('admin/admin_panel.html', 
                          users=users, 
                          current_time=current_time,
                          total_users=total_users,
                          active_users=active_users,
                          admin_users=admin_users,
                          inactive_users=inactive_users)

@admin_bp.route('/admin/model/retrain/delete/<int:run_id>')
@login_required
@admin_required
def delete_training_run(run_id):
    """Delete a training run and its associated metrics"""
    try:
        run = TrainingRun.query.get_or_404(run_id)
        db.session.delete(run)
        db.session.commit()
        flash(f'Training run from {run.finished_at.strftime("%Y-%m-%d")} successfully deleted', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Failed to delete training run: {str(e)}', 'error')
        current_app.logger.error(f"Delete training run error: {e}")
    return redirect(url_for('admin.retrain_model'))

@admin_bp.route('/admin/model/retrain/export/<int:run_id>')
@login_required
@admin_required
def export_training_run(run_id):
    run = TrainingRun.query.get_or_404(run_id)
    
    # Prepare data for CSV
    data = []
    for metric in run.metrics:
        # Base metrics
        row = {
            'Model': metric.model_name,
            'Accuracy': metric.accuracy,
            'Precision (Weighted)': metric.precision,
            'Recall (Weighted)': metric.recall,
            'F1-Score (Weighted)': metric.f1
        }
        
        # Add per-class details if available
        if metric.detail_metrics:
            details = metric.detail_metrics
            for cls in ['radikal', 'non-radikal']:
                if cls in details:
                    row[f'Precision {cls}'] = details[cls].get('precision')
                    row[f'Recall {cls}'] = details[cls].get('recall')
                    row[f'F1 {cls}'] = details[cls].get('f1-score')
        
        data.append(row)
        
    df = pd.DataFrame(data)
    
    # Export to CSV
    output = io.BytesIO()
    df.to_csv(output, index=False)
    output.seek(0)
    
    return send_file(
        output,
        mimetype='text/csv',
        as_attachment=True,
        download_name=f'training_results_{run_id}_{run.finished_at.strftime("%Y%m%d")}.csv'
    )

@admin_bp.route('/admin/classification/settings', methods=['GET', 'POST'])
@login_required
@admin_required
def classification_settings():
    """Halaman pengaturan klasifikasi"""
    if request.method == 'POST':
        action = request.form.get('action')
        
        if action == 'save_settings':
            # Simpan pengaturan
            try:
                threshold = float(request.form.get('classification_threshold', 0.5))
                algorithms = request.form.getlist('algorithms')
                
                if not algorithms:
                    flash('Please select at least one algorithm', 'error')
                    return redirect(url_for('admin.classification_settings'))

                # Simpan ke persistent settings
                settings = {
                    'CLASSIFICATION_THRESHOLD': threshold,
                    'VISIBLE_ALGORITHMS': algorithms
                }
                save_system_settings(settings)
                
                flash('Settings successfully saved!', 'success')
            except ValueError:
                flash('Invalid threshold value', 'error')
            
        elif action == 'upload_model':
            # Handle upload model
            if 'model_file' not in request.files:
                flash('No file selected', 'error')
            else:
                file = request.files['model_file']
                model_type = request.form.get('model_type')
                
                if file.filename == '':
                    flash('No file selected', 'error')
                else:
                    try:
                        # Map model types to config paths
                        model_paths = {
                            'word2vec': current_app.config.get('WORD2VEC_MODEL_PATH'),
                            'label_encoder': current_app.config.get('LABEL_ENCODER_PATH'),
                            'naive_bayes': current_app.config.get('MODEL_NAIVE_BAYES_PATH'),
                            'svm': current_app.config.get('MODEL_SVM_PATH'),
                            'random_forest': current_app.config.get('MODEL_RANDOM_FOREST_PATH'),
                            'logistic_regression': current_app.config.get('MODEL_LOGISTIC_REGRESSION_PATH'),
                            'decision_tree': current_app.config.get('MODEL_DECISION_TREE_PATH'),
                            'knn': current_app.config.get('MODEL_KNN_PATH')
                        }

                        if model_type == 'indobert':
                            if not file.filename.endswith('.zip'):
                                flash('IndoBERT file must be .zip format', 'error')
                            else:
                                # IndoBERT extraction logic
                                indobert_path = current_app.config.get('MODEL_INDOBERT_PATH')
                                
                                # Create temp file
                                temp_dir = os.path.join(current_app.config['UPLOAD_FOLDER'], 'temp')
                                os.makedirs(temp_dir, exist_ok=True)
                                temp_zip = os.path.join(temp_dir, 'temp_indobert.zip')
                                file.save(temp_zip)
                                
                                # Validate zip
                                if not zipfile.is_zipfile(temp_zip):
                                    flash('File is not a valid ZIP file', 'error')
                                    try:
                                        os.remove(temp_zip)
                                    except:
                                        pass
                                else:
                                    # Clear existing directory
                                    if os.path.exists(indobert_path):
                                        shutil.rmtree(indobert_path)
                                    os.makedirs(indobert_path, exist_ok=True)
                                    
                                    # Extract
                                    with zipfile.ZipFile(temp_zip, 'r') as zip_ref:
                                        zip_ref.extractall(indobert_path)
                                    
                                    try:
                                        os.remove(temp_zip)
                                    except:
                                        pass
                                        
                                    flash('IndoBERT model successfully updated', 'success')
                                    
                        elif model_type in model_paths:
                            # Generic file replacement
                            target_path = model_paths[model_type]
                            if not target_path:
                                flash(f'Path for model {model_type} is not configured', 'error')
                            else:
                                # Ensure directory exists
                                os.makedirs(os.path.dirname(target_path), exist_ok=True)
                                
                                # Save file
                                file.save(target_path)
                                flash(f'Model {model_type} successfully updated', 'success')
                            
                        else:
                            flash('Model type not recognized', 'error')
                            
                    except Exception as e:
                        flash(f'Failed to upload model: {str(e)}', 'error')
                        current_app.logger.error(f"Model upload error: {e}")
                    
        return redirect(url_for('admin.classification_settings'))
        
    # GET request
    # Mock config object for template
    config = {
        'classification_threshold': current_app.config.get('CLASSIFICATION_THRESHOLD', 0.5),
        'visible_algorithms': current_app.config.get('VISIBLE_ALGORITHMS', ['naive_bayes', 'svm', 'random_forest'])
    }
    
    # Mock all_models for template
    all_models = [
        {'key': 'naive_bayes', 'name': 'Naive Bayes'},
        {'key': 'svm', 'name': 'Support Vector Machine'},
        {'key': 'random_forest', 'name': 'Random Forest'},
        {'key': 'logistic_regression', 'name': 'Logistic Regression'},
        {'key': 'decision_tree', 'name': 'Decision Tree'},
        {'key': 'knn', 'name': 'K-Nearest Neighbors'},
        {'key': 'indobert', 'name': 'IndoBERT Fine Tuning'}
    ]
    
    return render_template('admin/classification_settings.html', config=config, all_models=all_models)

@admin_bp.route('/admin/model/retrain/history/delete', methods=['POST'])
@login_required
@admin_required
def delete_retrain_history():
    """Delete all training history"""
    try:
        # Import models inside function to ensure availability
        from models.models import TrainingMetric, TrainingRun
        
        # Delete metrics first (FK dependency)
        TrainingMetric.query.delete()
        
        # Delete runs
        TrainingRun.query.delete()
        
        # Reset sequences
        for table in ['training_metrics', 'training_runs']:
            try:
                db.session.execute(text(f"ALTER SEQUENCE {table}_id_seq RESTART WITH 1"))
            except:
                pass
                
        db.session.commit()
        flash('Training history cleared successfully', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Failed to clear history: {str(e)}', 'error')
        
    return redirect(url_for('admin.retrain_model'))

@admin_bp.route('/admin/model/retrain/finish/<task_id>')
@login_required
@admin_required
def retrain_finish(task_id):
    """Handle completion of async training"""
    task = training_tasks.get(task_id)
    if not task or task['status'] != 'completed':
        flash('Training task not found or not completed', 'error')
        return redirect(url_for('admin.retrain_model'))
    
    # Store results in session as expected by existing logic
    results = task['results']
    # Retrieve metadata stored in task (we need to add this to run_training_async)
    # Wait, I didn't store metadata in task yet. Let's rely on what we passed.
    
    # We need to pass filename etc back to session
    # Let's store it in task['metadata'] in the async starter
    meta = task.get('metadata', {})
    
    session['training_results'] = results
    session['training_filename'] = meta.get('filename')
    session['training_col_text'] = meta.get('col_text')
    session['training_col_label'] = meta.get('col_label')
    
    # Clean up task (optional, or expire later)
    # training_tasks.pop(task_id, None) 
    
    # Fetch training history
    history = TrainingRun.query.filter_by(is_applied=True).order_by(TrainingRun.finished_at.desc()).limit(20).all()
    
    # Format history for template
    formatted_history = []
    for run in history:
        metrics_dict = {}
        for metric in run.metrics:
            metrics_dict[metric.model_name] = {
                'accuracy': metric.accuracy,
                'precision': metric.precision,
                'recall': metric.recall,
                'f1': metric.f1,
                'detail_metrics': metric.detail_metrics,
                'confusion_matrix': metric.confusion_matrix
            }
        
        formatted_history.append({
            'id': run.id,
            'date': run.finished_at.strftime('%Y-%m-%d %H:%M:%S'),
            'filename': run.filename,
            'metrics': metrics_dict
        })
    
    return render_template('admin/retrain.html', 
                          results=results, 
                          temp_mode=True, 
                          mapping_mode=False, 
                          last_results=formatted_history)

def handle_train_request(is_ajax):
    """Handle training initiation logic"""
    filename = request.form.get('filename')
    col_text = request.form.get('col_text')
    col_label = request.form.get('col_label')
    
    if not filename or not col_text or not col_label:
        msg = 'Please complete the training form'
        if is_ajax: return jsonify({'error': msg}), 400
        flash(msg, 'error')
        return redirect(url_for('admin.retrain_model'))
    
    temp_path = os.path.join(current_app.config['UPLOAD_FOLDER'], 'temp', filename)
    if not os.path.exists(temp_path):
        msg = 'Dataset file not found. Please upload again.'
        if is_ajax: return jsonify({'error': msg}), 400
        flash(msg, 'error')
        return redirect(url_for('admin.retrain_model'))
    
    try:
        df = pd.read_csv(temp_path)
        
        # Dedupe columns
        df = df.loc[:, ~df.columns.duplicated()]
        
        # Column mapping logic
        if 'normalisasi_kalimat' in df.columns and col_text != 'normalisasi_kalimat':
            df = df.drop(columns=['normalisasi_kalimat'])
            
        if 'label' in df.columns and col_label != 'label':
            df = df.drop(columns=['label'])
        
        df = df.rename(columns={
            col_text: 'normalisasi_kalimat',
            col_label: 'label'
        })
        
        # Validate after rename
        if 'normalisasi_kalimat' not in df.columns or 'label' not in df.columns:
             raise ValueError(f"Renaming failed. Columns expected: 'normalisasi_kalimat', 'label'. Found: {list(df.columns)}")
        
        # Check Word2Vec
        word2vec_model = current_app.config.get('WORD2VEC_MODEL')
        if not word2vec_model:
            msg = 'Word2Vec model not loaded. Please restart application.'
            if is_ajax: return jsonify({'error': msg}), 400
            flash(msg, 'error')
            return redirect(url_for('admin.retrain_model'))
        
        # Start Async Training
        task_id = str(uuid.uuid4())
        training_tasks[task_id] = {
            'status': 'running',
            'progress': 0,
            'message': 'Initializing training...',
            'metadata': {
                'filename': filename,
                'col_text': col_text,
                'col_label': col_label
            }
        }
        
        app = current_app._get_current_object()
        
        thread = threading.Thread(target=run_training_async, args=(
            app, task_id, df, word2vec_model, current_user.id, filename, 'normalisasi_kalimat', 'label', False
        ))
        thread.start()
        
        if is_ajax:
            return jsonify({'task_id': task_id, 'status': 'started'})
        else:
            flash('Training started in background...', 'info')
            return render_template('admin/retrain_loading.html', task_id=task_id)
                              
    except Exception as e:
        msg = f'Training failed: {str(e)}'
        if is_ajax: return jsonify({'error': msg}), 500
        flash(msg, 'error')
        current_app.logger.error(f"Training error: {e}")
        return redirect(url_for('admin.retrain_model'))

def handle_confirm_replace():
    """Handle confirmation and model replacement logic"""
    filename = session.get('training_filename')
    col_text = session.get('training_col_text')
    col_label = session.get('training_col_label')
    
    if not filename:
        flash('Training session expired. Please repeat.', 'error')
        return redirect(url_for('admin.retrain_model'))
        
    temp_path = os.path.join(current_app.config['UPLOAD_FOLDER'], 'temp', filename)
    
    try:
        df = pd.read_csv(temp_path)
        df = df.loc[:, ~df.columns.duplicated()]
        
        if 'normalisasi_kalimat' in df.columns and col_text != 'normalisasi_kalimat':
            df = df.drop(columns=['normalisasi_kalimat'])
            
        if 'label' in df.columns and col_label != 'label':
            df = df.drop(columns=['label'])
            
        df = df.rename(columns={
            col_text: 'normalisasi_kalimat',
            col_label: 'label'
        })
        
        if 'normalisasi_kalimat' not in df.columns or 'label' not in df.columns:
             raise ValueError(f"Renaming failed. Columns expected: 'normalisasi_kalimat', 'label'. Found: {list(df.columns)}")
        
        word2vec_model = current_app.config.get('WORD2VEC_MODEL')
        user_id = current_user.id
        
        # Perform training using the STANDARDIZED column names
        # We renamed the columns in the dataframe to 'normalisasi_kalimat' and 'label' above
        results = train_models(df, word2vec_model, save_models=True, user_id=user_id, filename=filename, col_text='normalisasi_kalimat', col_label='label')
        
        flash('Model successfully retrained and deployed to production!', 'success')
        
        # Clear session
        session.pop('training_results', None)
        session.pop('training_filename', None)
        session.pop('training_col_text', None)
        session.pop('training_col_label', None)
        
        try:
            os.remove(temp_path)
        except:
            pass
            
    except Exception as e:
        flash(f'Failed to save model: {str(e)}', 'error')
    
    return redirect(url_for('admin.retrain_model'))

def handle_file_upload():
    """Handle CSV file upload logic"""
    file = request.files['file']
    if file.filename == '':
        flash('No file selected', 'error')
        return redirect(url_for('admin.retrain_model'))
        
    if file and file.filename.endswith('.csv'):
        try:
            temp_dir = os.path.join(current_app.config['UPLOAD_FOLDER'], 'temp')
            os.makedirs(temp_dir, exist_ok=True)
            
            filename = f"train_{int(pd.Timestamp.now().timestamp())}_{file.filename}"
            file_path = os.path.join(temp_dir, filename)
            file.save(file_path)
            
            df = pd.read_csv(file_path)
            headers = df.columns.tolist()
            
            return render_template('admin/retrain.html',
                                  results=None,
                                  temp_mode=False,
                                  mapping_mode=True,
                                  filename=filename,
                                  headers=headers,
                                  last_results={})
        except Exception as e:
            flash(f'Error reading file: {str(e)}', 'error')
            return redirect(url_for('admin.retrain_model'))
    else:
        flash('Only CSV files are allowed', 'error')
        return redirect(url_for('admin.retrain_model'))

@admin_bp.route('/admin/model/retrain', methods=['GET', 'POST'])
@login_required
@admin_required
def retrain_model():
    """Halaman retrain model - Refactored for better modularity"""
    if request.method == 'POST':
        action = request.form.get('action')
        # Debug logging
        is_ajax_check = request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.args.get('ajax')
        current_app.logger.info(f"Retrain POST: action={action}, ajax={is_ajax_check}, headers={request.headers.get('X-Requested-With')}, args={request.args}")
        
        if action == 'train':
            return handle_train_request(is_ajax_check)
        elif action == 'confirm_replace':
            return handle_confirm_replace()
        elif 'file' in request.files:
            return handle_file_upload()

    # Fetch training history
    history = TrainingRun.query.filter_by(is_applied=True).order_by(TrainingRun.finished_at.desc()).limit(20).all()
    
    # Format history for template
    formatted_history = []
    for run in history:
        metrics_dict = {}
        for metric in run.metrics:
            metrics_dict[metric.model_name] = {
                'accuracy': metric.accuracy,
                'precision': metric.precision,
                'recall': metric.recall,
                'f1': metric.f1,
                'detail_metrics': metric.detail_metrics,
                'confusion_matrix': metric.confusion_matrix
            }
        
        formatted_history.append({
            'id': run.id,
            'date': run.finished_at.strftime('%Y-%m-%d %H:%M:%S'),
            'filename': run.filename,
            'metrics': metrics_dict
        })

    return render_template('admin/retrain.html', 
                          results=None, 
                          temp_mode=False, 
                          mapping_mode=False, 
                          last_results=formatted_history)

@admin_bp.route('/admin/database', methods=['GET'])
@login_required
@admin_required
def database_management():
    """Halaman manajemen database"""
    # Calculate statistics
    users_count = User.query.count()
    datasets_count = Dataset.query.count()
    raw_data_count = RawData.query.count() + RawDataScraper.query.count()
    classifications_count = ClassificationResult.query.count()
    
    stats = {
        'users': users_count,
        'datasets': datasets_count,
        'raw_data': raw_data_count,
        'classifications': classifications_count
    }
    
    return render_template('admin/database.html', stats=stats)

import subprocess
import shlex

@admin_bp.route('/admin/database/backup', methods=['GET'])
@login_required
@admin_required
def database_backup():
    """Backup database to SQL using pg_dump"""
    try:
        # Get database URL
        db_url = current_app.config['SQLALCHEMY_DATABASE_URI']
        
        # Prepare timestamp
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"backup_waskita_{timestamp}.sql"
        
        # Use subprocess to call pg_dump
        # Note: This assumes pg_dump is in PATH or we need to specify full path
        # Also assumes .pgpass is set up or password is in DB URL
        
        # Parse DB URL for pg_dump (if needed, but pg_dump handles connection strings)
        # However, subprocess environment might need PGPASSWORD
        
        # Parse database URL for robust parameter extraction
        parsed = urlparse(db_url)
        
        # Setup env for password and other connection params
        env = os.environ.copy()
        env['PGPASSWORD'] = parsed.password or ''
        # pg_dump can take connection string, but setting PGPASSWORD is safer for some versions
        
        command = f'pg_dump "{db_url}" --clean --if-exists --no-owner --no-acl'
        
        # Execute pg_dump
        process = subprocess.Popen(
            command,
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env
        )
        
        stdout, stderr = process.communicate()
        
        if process.returncode != 0:
            current_app.logger.error(f"Backup failed: {stderr.decode('utf-8')}")
            raise Exception(f"Backup process failed: {stderr.decode('utf-8')}")
            
        # Return file
        mem = io.BytesIO(stdout)
        mem.seek(0)
        
        return send_file(
            mem,
            as_attachment=True,
            download_name=filename,
            mimetype='application/sql'
        )

    except Exception as e:
        flash(f'Failed to backup SQL: {str(e)}', 'error')
        current_app.logger.error(f"Backup error: {e}")
        return redirect(url_for('admin.database_management'))

@admin_bp.route('/admin/database/restore', methods=['POST'])
@login_required
@admin_required
def database_restore():
    """Restore database from SQL file using psql"""
    if 'file' not in request.files:
        flash('No file selected', 'error')
        return redirect(url_for('admin.database_management'))
        
    file = request.files['file']
    if file.filename == '':
        flash('No file selected', 'error')
        return redirect(url_for('admin.database_management'))
        
    if file:
        try:
            # Check extension
            if not file.filename.endswith('.sql'):
                flash('File must be .sql format', 'error')
                return redirect(url_for('admin.database_management'))

            # Save uploaded file temporarily
            temp_path = os.path.join(current_app.config['UPLOAD_FOLDER'], 'temp_restore.sql')
            file.save(temp_path)
            
            # Get database URL
            db_url = current_app.config['SQLALCHEMY_DATABASE_URI']
            
            # Parse database URL for robust parameter extraction
            parsed = urlparse(db_url)
            
            # Setup env for password and other connection params
            env = os.environ.copy()
            env['PGPASSWORD'] = parsed.password or ''
            env['PGUSER'] = parsed.username or 'postgres'
            env['PGHOST'] = parsed.hostname or 'localhost'
            env['PGPORT'] = str(parsed.port or 5432)
            # Remove leading slash from path for database name
            db_name = parsed.path.lstrip('/')
            env['PGDATABASE'] = db_name
            
            # Ensure psql doesn't prompt for password and fails fast
            env['PGCONNECT_TIMEOUT'] = '10'

            # Terminate other connections to the database to prevent deadlocks
            # WARNING: This kills all other sessions, including the web app's own pool if shared
            try:
                # Close current session to release its own connection
                db.session.remove()
                
                # Kill other connections using a separate psql command or SQLAlchemy
                # Using subprocess psql to avoid transaction block issues in current session
                kill_cmd = [
                    'psql',
                    '-h', parsed.hostname or 'localhost',
                    '-p', str(parsed.port or 5432),
                    '-U', parsed.username or 'postgres',
                    '-d', 'postgres', # Connect to 'postgres' db to kill connections to target db
                    '-c', f"SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = '{db_name}' AND pid <> pg_backend_pid();"
                ]
                
                # We need to set PGPASSWORD for this command too
                kill_env = env.copy()
                
                current_app.logger.info(f"Terminating active connections to {db_name}...")
                subprocess.run(kill_cmd, env=kill_env, check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                
            except Exception as kill_err:
                current_app.logger.warning(f"Failed to kill existing connections: {kill_err}")

            # Command to restore using psql directly with file argument
            # This avoids shell=True and stdin piping issues on Windows which can cause slowness/hanging
            host = parsed.hostname or 'localhost'
            port = str(parsed.port or 5432)
            user = parsed.username or 'postgres'
            
            # Prepare command as list for safety and direct execution
            command = [
                'psql',
                '-h', host,
                '-p', port,
                '-U', user,
                '-d', db_name,
                # '-v', 'ON_ERROR_STOP=1', # Temporarily disabled to debug partial restores
                '-w',  # Never prompt for password
                '-f', temp_path
            ]
            
            current_app.logger.info(f"Starting database restore for {db_name} using file: {temp_path}")
            
            process = subprocess.Popen(
                command,
                shell=False, # Safer and avoids shell injection/parsing issues
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=env
            )
            
            try:
                # Add timeout (e.g., 10 minutes for large dumps)
                stdout, stderr = process.communicate(timeout=600)
            except subprocess.TimeoutExpired:
                process.kill()
                stdout, stderr = process.communicate()
                current_app.logger.error("Restore process timed out")
                raise Exception("Restore process timed out after 10 minutes")
            
            # Clean up
            try:
                os.remove(temp_path)
            except:
                pass
            
            # Always log output for debugging
            stdout_output = stdout.decode('utf-8')
            stderr_output = stderr.decode('utf-8')
            
            if stdout_output:
                current_app.logger.info(f"Restore STDOUT: {stdout_output[:1000]}...")
            if stderr_output:
                current_app.logger.warning(f"Restore STDERR: {stderr_output[:1000]}...")

            if process.returncode != 0:
                # Filter out harmless warnings or specific errors we want to ignore
                if "unrecognized configuration parameter \"transaction_timeout\"" in stderr_output:
                     current_app.logger.warning("Ignored transaction_timeout error during restore")
                else:
                    current_app.logger.error(f"Restore failed with code {process.returncode}")
                    # Don't raise exception immediately if we want to allow partial success, 
                    # but usually return code != 0 means something went wrong.
                    # For now, let's trust the return code unless it's just the timeout warning.
                    if "transaction_timeout" not in stderr_output:
                        raise Exception(f"Restore process failed: {stderr_output}")
                
            flash('Database successfully restored from SQL', 'success')
            current_app.logger.info("Database restore completed successfully")
            
        except Exception as e:
            flash(f"Failed to restore SQL: {str(e)}", 'error')
            current_app.logger.error(f"Restore error: {e}")

    return redirect(url_for('admin.database_management'))

@admin_bp.route('/admin/logs/backup', methods=['GET'])
@login_required
@admin_required
def logs_backup():
    """Backup logs (ZIP)"""
    try:
        # Increase timeout for this specific route if possible, or ensure client handles it.
        # Nginx timeout is the usual culprit for 504.
        # But we can try to be efficient.
        
        # Define logs directory
        if os.path.exists('/app/logs'):
            log_dir = '/app/logs'
        else:
            log_dir = current_app.config.get('LOG_FOLDER')
            if not log_dir:
                 basedir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
                 log_dir = os.path.join(basedir, 'logs')
        
        current_app.logger.info(f"Backup Logs: Looking in {log_dir}")
        
        if not os.path.exists(log_dir):
            flash(f'Logs directory not found at {log_dir}', 'error')
            return redirect(url_for('admin.database_management'))

        # Stream the response instead of buffering in memory if files are large
        # But ZipFile needs seekable stream usually, or we use a generator.
        # For simplicity and Nginx compatibility, let's just use send_file but warn about size.
        
        mem = io.BytesIO()
        with zipfile.ZipFile(mem, 'w', zipfile.ZIP_DEFLATED) as zf:
            target_logs = ['waskita.log', 'security.log', 'audit.log', 'app.log']
            found_count = 0
            
            # Add target logs
            for log_file in target_logs:
                file_path = os.path.join(log_dir, log_file)
                if os.path.exists(file_path):
                    try:
                        # Limit file size added to zip to avoid timeout/memory issues
                        # e.g., tail last 50MB if file is huge
                        file_size = os.path.getsize(file_path)
                        if file_size > 50 * 1024 * 1024: # 50MB
                            # Add warning file
                            zf.writestr(f"{log_file}_truncated.txt", f"File {log_file} is too large ({file_size} bytes). Skipping full content to prevent timeout.")
                        else:
                            zf.write(file_path, arcname=log_file)
                        found_count += 1
                    except Exception as zip_err:
                        current_app.logger.error(f"Failed to zip {log_file}: {zip_err}")

            # Auto-discover other .log files
            for root, dirs, files in os.walk(log_dir):
                for file in files:
                    if file.endswith('.log') or '.log.' in file:
                        if file not in target_logs:
                            try:
                                file_path = os.path.join(root, file)
                                file_size = os.path.getsize(file_path)
                                if file_size <= 50 * 1024 * 1024: # 50MB limit per file
                                    zf.write(file_path, arcname=file)
                                    found_count += 1
                            except Exception:
                                pass
            
            if found_count == 0:
                flash(f'No log files found in {log_dir}', 'warning')
                return redirect(url_for('admin.database_management'))

        mem.seek(0)
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        
        return send_file(
            mem,
            as_attachment=True,
            download_name=f"waskita_logs_{timestamp}.zip",
            mimetype='application/zip'
        )
    except Exception as e:
        flash(f'Failed to backup logs: {str(e)}', 'error')
        current_app.logger.error(f"Log backup error: {e}", exc_info=True)
        return redirect(url_for('admin.database_management'))

@admin_bp.route('/admin/logs/reset', methods=['POST'])
@login_required
@admin_required
def logs_reset():
    """Reset logs"""
    try:
        # 1. Clear Database Logs
        UserActivity.query.delete()
        
        # Reset sequence
        try:
            db.session.execute(text("ALTER SEQUENCE user_activities_id_seq RESTART WITH 1"))
        except Exception as seq_err:
             current_app.logger.warning(f"Could not reset sequence for user_activities: {seq_err}")
             
        db.session.commit()
        
        # 2. Clear File Logs
        # Define logs directory
        if os.path.exists('/app/logs'):
            log_dir = '/app/logs'
        else:
            log_dir = current_app.config.get('LOG_FOLDER')
            if not log_dir:
                 basedir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
                 log_dir = os.path.join(basedir, 'logs')
                 
        target_logs = ['waskita.log', 'security.log', 'audit.log', 'app.log']
        cleared_files = []
        
        if os.path.exists(log_dir):
            for log_file in target_logs:
                file_path = os.path.join(log_dir, log_file)
                if os.path.exists(file_path):
                    try:
                        # Truncate file
                        with open(file_path, 'w') as f:
                            f.truncate(0)
                        cleared_files.append(log_file)
                    except Exception as f_err:
                        current_app.logger.error(f"Failed to clear {log_file}: {f_err}")
        
        flash(f'Logs successfully reset (DB cleared, {len(cleared_files)} files truncated)', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f"Failed to reset logs: {str(e)}", 'error')
    return redirect(url_for('admin.database_management'))

@admin_bp.route('/admin/database/reset', methods=['POST'])
@login_required
@admin_required
def database_reset():
    """Reset database (delete all data except users)"""
    try:
        # Delete all data from tables (except User)
        # Order matters due to foreign keys
        
        # 1. Delete training metrics (must be before TrainingRun)
        try:
            from models.models import TrainingMetric
            TrainingMetric.query.delete()
        except:
            pass # Maybe model not imported or table not exists
            
        # 2. Delete training runs
        try:
            TrainingRun.query.delete()
        except:
            pass
            
        # 3. Delete classification results
        ClassificationResult.query.delete()
        
        # 4. Delete clean data
        CleanDataUpload.query.delete()
        CleanDataScraper.query.delete()
        
        # 5. Delete raw data
        RawData.query.delete()
        RawDataScraper.query.delete()
        
        # 6. Delete classification batches (must be before datasets)
        ClassificationBatch.query.delete()
        
        # 7. Delete datasets
        Dataset.query.delete()
        
        # 8. Delete user activities (optional, but good for full reset)
        UserActivity.query.delete()

        # 9. Delete manual history
        ManualClassificationHistory.query.delete()

        # 10. Delete OTP Registration History
        try:
            from models.models_otp import RegistrationRequest, AdminNotification, OTPEmailLog
            # Delete dependent tables first
            AdminNotification.query.delete()
            OTPEmailLog.query.delete()
            # Delete main table
            RegistrationRequest.query.delete()
        except Exception as e:
            current_app.logger.error(f"Error resetting OTP tables: {e}")
        
        # 11. Reset statistics
        DatasetStatistics.query.delete()
            
        # Reset sequences
        tables = [
            'classification_results', 'clean_data_upload', 'clean_data_scraper',
            'raw_data', 'raw_data_scraper', 'classification_batches', 'datasets', 'user_activities',
            'dataset_statistics', 'manual_classification_history', 'training_runs', 'training_metrics',
            'registration_requests', 'admin_notifications', 'otp_email_logs'
        ]
        
        for table in tables:
            try:
                db.session.execute(text(f"ALTER SEQUENCE {table}_id_seq RESTART WITH 1"))
            except Exception as seq_err:
                 # Sequence might not exist or name might be different, log but continue
                 current_app.logger.warning(f"Could not reset sequence for {table}: {seq_err}")

        db.session.commit()
        
        flash('Database successfully reset (User data remains safe)', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f"Failed to reset database: {str(e)}", 'error')
        
    return redirect(url_for('admin.database_management'))
