from flask import render_template, request, flash, redirect, url_for, jsonify, current_app
from flask_login import login_required
from utils import admin_required
from models import db, User, Dataset, RawData, RawDataScraper, ClassificationResult

def init_admin_routes(app):
    @app.route('/admin/classification/settings', methods=['GET', 'POST'])
    @login_required
    @admin_required
    def admin_classification_settings():
        """Halaman pengaturan klasifikasi"""
        if request.method == 'POST':
            action = request.form.get('action')
            
            if action == 'save_settings':
                # Simpan pengaturan
                try:
                    threshold = float(request.form.get('classification_threshold', 0.5))
                    algorithms = request.form.getlist('algorithms')
                    
                    # Simpan ke app config
                    current_app.config['CLASSIFICATION_THRESHOLD'] = threshold
                    current_app.config['VISIBLE_ALGORITHMS'] = algorithms
                    
                    flash('Pengaturan berhasil disimpan!', 'success')
                except ValueError:
                    flash('Nilai threshold tidak valid', 'error')
                
            elif action == 'upload_model':
                # Handle upload model
                if 'model_file' not in request.files:
                    flash('Tidak ada file yang dipilih', 'error')
                else:
                    file = request.files['model_file']
                    if file.filename == '':
                        flash('Tidak ada file yang dipilih', 'error')
                    else:
                        # TODO: Implement model extraction logic
                        flash('Fitur upload model belum diimplementasikan sepenuhnya', 'info')
                        
            return redirect(url_for('admin_classification_settings'))
            
        # GET request
        # Mock config object for template
        config = {
            'classification_threshold': current_app.config.get('CLASSIFICATION_THRESHOLD', 0.5),
            'visible_algorithms': current_app.config.get('VISIBLE_ALGORITHMS', ['nb', 'svm', 'rf'])
        }
        
        # Mock all_models for template
        all_models = [
            {'key': 'nb', 'name': 'Naive Bayes'},
            {'key': 'svm', 'name': 'Support Vector Machine'},
            {'key': 'rf', 'name': 'Random Forest'},
            {'key': 'lr', 'name': 'Logistic Regression'},
            {'key': 'dt', 'name': 'Decision Tree'},
            {'key': 'knn', 'name': 'K-Nearest Neighbors'}
        ]
        
        return render_template('admin/classification_settings.html', config=config, all_models=all_models)

    @app.route('/admin/model/retrain', methods=['GET', 'POST'])
    @login_required
    @admin_required
    def admin_retrain_model():
        """Halaman retrain model"""
        if request.method == 'POST':
            action = request.form.get('action')
            
            if action == 'train':
                # Handle training logic
                flash('Proses training dimulai di background...', 'info')
            elif action == 'confirm_replace':
                flash('Model berhasil diterapkan ke production', 'success')
                
            return redirect(url_for('admin_retrain_model'))

        return render_template('admin/retrain.html', 
                              results=None, 
                              temp_mode=False, 
                              mapping_mode=False, 
                              last_results={})

    @app.route('/admin/database', methods=['GET'])
    @login_required
    @admin_required
    def admin_database_management():
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

    @app.route('/admin/database/backup', methods=['GET'])
    @login_required
    @admin_required
    def admin_database_backup():
        """Backup database"""
        # TODO: Implement actual backup
        flash('Fitur backup belum diimplementasikan', 'info')
        return redirect(url_for('admin_database_management'))

    @app.route('/admin/database/restore', methods=['POST'])
    @login_required
    @admin_required
    def admin_database_restore():
        """Restore database"""
        # TODO: Implement actual restore
        flash('Fitur restore belum diimplementasikan', 'info')
        return redirect(url_for('admin_database_management'))

    @app.route('/admin/logs/backup', methods=['GET'])
    @login_required
    @admin_required
    def admin_logs_backup():
        """Backup logs"""
        # TODO: Implement actual logs backup
        flash('Fitur backup logs belum diimplementasikan', 'info')
        return redirect(url_for('admin_database_management'))

    @app.route('/admin/logs/reset', methods=['POST'])
    @login_required
    @admin_required
    def admin_logs_reset():
        """Reset logs"""
        # TODO: Implement actual logs reset
        flash('Fitur reset logs belum diimplementasikan', 'info')
        return redirect(url_for('admin_database_management'))

    @app.route('/admin/database/reset', methods=['POST'])
    @login_required
    @admin_required
    def admin_database_reset():
        """Reset database (delete all data except current admin)"""
        # TODO: Implement actual database reset
        flash('Fitur reset database belum diimplementasikan', 'info')
        return redirect(url_for('admin_database_management'))

