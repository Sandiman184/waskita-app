from flask import Blueprint, render_template, request, flash, redirect, url_for, jsonify, current_app, session
from flask_login import login_required, current_user
from sqlalchemy import text
from utils.utils import admin_required
from models.models import db, User, Dataset, RawData, RawDataScraper, ClassificationResult, DatasetStatistics, CleanDataUpload, CleanDataScraper, UserActivity, ManualClassificationHistory
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

from utils.i18n import t

admin_bp = Blueprint('admin', __name__)

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

@admin_bp.route('/admin/model/retrain', methods=['GET', 'POST'])
@login_required
@admin_required
def retrain_model():
    """Halaman retrain model"""
    if request.method == 'POST':
        action = request.form.get('action')
        
        if action == 'train':
            # Handle training logic
            # 1. Get dataset
            filename = request.form.get('filename')
            col_text = request.form.get('col_text')
            col_label = request.form.get('col_label')
            
            if not filename or not col_text or not col_label:
                flash('Please complete the training form', 'error')
                return redirect(url_for('admin.retrain_model'))
            
            temp_path = os.path.join(current_app.config['UPLOAD_FOLDER'], 'temp', filename)
            if not os.path.exists(temp_path):
                flash('Dataset file not found. Please upload again.', 'error')
                return redirect(url_for('admin.retrain_model'))
            
            try:
                df = pd.read_csv(temp_path)
                
                # Rename columns to match expected format
                df = df.rename(columns={
                    col_text: 'normalisasi_kalimat',
                    col_label: 'label'
                })
                
                # Train models
                word2vec_model = current_app.config.get('WORD2VEC_MODEL')
                if not word2vec_model:
                    flash('Word2Vec model not loaded. Please restart application.', 'error')
                    return redirect(url_for('admin.retrain_model'))
                    
                results = train_models(df, word2vec_model, save_models=False)
                
                # Store results in session for confirmation
                session['training_results'] = results
                session['training_filename'] = filename
                session['training_col_text'] = col_text
                session['training_col_label'] = col_label
                
                return render_template('admin/retrain.html', 
                                      results=results, 
                                      temp_mode=True, 
                                      mapping_mode=False, 
                                      last_results={})
                                      
            except Exception as e:
                flash(f'Training failed: {str(e)}', 'error')
                current_app.logger.error(f"Training error: {e}")
                return redirect(url_for('admin.retrain_model'))

        elif action == 'confirm_replace':
            # Re-run training with save_models=True
            filename = session.get('training_filename')
            col_text = session.get('training_col_text')
            col_label = session.get('training_col_label')
            
            if not filename:
                flash('Training session expired. Please repeat.', 'error')
                return redirect(url_for('admin.retrain_model'))
                
            temp_path = os.path.join(current_app.config['UPLOAD_FOLDER'], 'temp', filename)
            
            try:
                df = pd.read_csv(temp_path)
                df = df.rename(columns={
                    col_text: 'normalisasi_kalimat',
                    col_label: 'label'
                })
                
                word2vec_model = current_app.config.get('WORD2VEC_MODEL')
                
                # Use user_id for logging history
                user_id = current_user.id
                
                # Perform training
                results = train_models(df, word2vec_model, save_models=True, user_id=user_id, filename=filename, col_text=col_text, col_label=col_label)
                
                flash('Model successfully retrained and deployed to production!', 'success')
                
                # Clear session
                session.pop('training_results', None)
                session.pop('training_filename', None)
                session.pop('training_col_text', None)
                session.pop('training_col_label', None)
                
                # Clean up temp file
                try:
                    os.remove(temp_path)
                except:
                    pass
                    
            except Exception as e:
                flash(f'Failed to save model: {str(e)}', 'error')
            
            return redirect(url_for('admin.retrain_model'))
            
        elif 'file' in request.files:
            # Handle file upload
            file = request.files['file']
            if file.filename == '':
                flash('No file selected', 'error')
                return redirect(url_for('admin.retrain_model'))
                
            if file and file.filename.endswith('.csv'):
                try:
                    # Save to temp
                    temp_dir = os.path.join(current_app.config['UPLOAD_FOLDER'], 'temp')
                    os.makedirs(temp_dir, exist_ok=True)
                    
                    filename = f"train_{int(pd.Timestamp.now().timestamp())}_{file.filename}"
                    file_path = os.path.join(temp_dir, filename)
                    file.save(file_path)
                    
                    # Read headers
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

    return render_template('admin/retrain.html', 
                          results=None, 
                          temp_mode=False, 
                          mapping_mode=False, 
                          last_results={})

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
        
        # Simple parsing of connection string to get password
        # postgresql://user:password@host:port/dbname
        env = os.environ.copy()
        if 'PGPASSWORD' not in env and ':' in db_url and '@' in db_url:
            try:
                # Extract password roughly
                part1 = db_url.split('@')[0]
                if ':' in part1:
                    password = part1.split(':')[-1]
                    env['PGPASSWORD'] = password
            except:
                pass
        
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
            
            # Setup env for password
            env = os.environ.copy()
            if 'PGPASSWORD' not in env and ':' in db_url and '@' in db_url:
                try:
                    part1 = db_url.split('@')[0]
                    if ':' in part1:
                        password = part1.split(':')[-1]
                        env['PGPASSWORD'] = password
                except:
                    pass

            # Command to restore
            # psql "db_url" < file.sql
            # Note: on Windows shell=True with < redirection can be tricky.
            # Better to use stdin of Popen
            
            command = f'psql "{db_url}"'
            
            with open(temp_path, 'r') as f:
                process = subprocess.Popen(
                    command,
                    shell=True,
                    stdin=f,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    env=env
                )
                stdout, stderr = process.communicate()
            
            # Clean up
            try:
                os.remove(temp_path)
            except:
                pass
                
            if process.returncode != 0:
                current_app.logger.error(f"Restore failed: {stderr.decode('utf-8')}")
                raise Exception(f"Restore process failed: {stderr.decode('utf-8')}")
                
            flash('Database successfully restored from SQL', 'success')
            
        except Exception as e:
            flash(f"Failed to restore SQL: {str(e)}", 'error')
            current_app.logger.error(f"Restore error: {e}")

    return redirect(url_for('admin.database_management'))

@admin_bp.route('/admin/logs/backup', methods=['GET'])
@login_required
@admin_required
def logs_backup():
    """Backup logs"""
    try:
        # Helper to serialize query results
        def serialize_query(query_results):
            return [{c.name: getattr(item, c.name).isoformat() if hasattr(getattr(item, c.name), 'isoformat') else getattr(item, c.name) 
                     for c in item.__table__.columns} for item in query_results]

        data = serialize_query(UserActivity.query.all())

        mem = io.BytesIO()
        mem.write(json.dumps(data, indent=2).encode('utf-8'))
        mem.seek(0)

        filename = f"backup_logs_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        
        return send_file(
            mem,
            as_attachment=True,
            download_name=filename,
            mimetype='application/json'
        )
    except Exception as e:
        flash(f'Failed to backup logs: {str(e)}', 'error')
        return redirect(url_for('admin.database_management'))

@admin_bp.route('/admin/logs/reset', methods=['POST'])
@login_required
@admin_required
def logs_reset():
    """Reset logs"""
    try:
        UserActivity.query.delete()
        
        # Reset sequence
        try:
            db.session.execute(text("ALTER SEQUENCE user_activities_id_seq RESTART WITH 1"))
        except Exception as seq_err:
             current_app.logger.warning(f"Could not reset sequence for user_activities: {seq_err}")
             
        db.session.commit()
        flash('Logs successfully reset', 'success')
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
        
        # 1. Delete classification results
        ClassificationResult.query.delete()
        
        # 2. Delete clean data
        CleanDataUpload.query.delete()
        CleanDataScraper.query.delete()
        
        # 3. Delete raw data
        RawData.query.delete()
        RawDataScraper.query.delete()
        
        # 4. Delete datasets
        Dataset.query.delete()
        
        # 5. Delete user activities (optional, but good for full reset)
        UserActivity.query.delete()

        # 6. Delete manual history
        ManualClassificationHistory.query.delete()
        
        # 7. Reset statistics
        DatasetStatistics.query.delete()
            
        # Reset sequences
        tables = [
            'classification_results', 'clean_data_upload', 'clean_data_scraper',
            'raw_data', 'raw_data_scraper', 'datasets', 'user_activities',
            'dataset_statistics', 'manual_classification_history'
        ]
        
        for table in tables:
            try:
                db.session.execute(text(f"ALTER SEQUENCE {table}_id_seq RESTART WITH 1"))
            except Exception as seq_err:
                 current_app.logger.warning(f"Could not reset sequence for {table}: {seq_err}")

        db.session.commit()
        
        flash('Database successfully reset (User data remains safe)', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f"Failed to reset database: {str(e)}", 'error')
        
    return redirect(url_for('admin.database_management'))
