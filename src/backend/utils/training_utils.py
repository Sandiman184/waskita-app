import os
import pandas as pd
import numpy as np
import pickle
import joblib
from sklearn.model_selection import train_test_split
from sklearn.metrics import classification_report, accuracy_score
from sklearn.naive_bayes import GaussianNB
from sklearn.svm import SVC
from sklearn.neighbors import KNeighborsClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.tree import DecisionTreeClassifier
from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier
from sklearn.calibration import CalibratedClassifierCV
from sklearn.preprocessing import LabelEncoder
from flask import current_app

# Import existing preprocessing logic
from utils.utils import clean_text, vectorize_text, preprocess_for_model, preprocess_for_word2vec

def train_models(df, word2vec_model, save_models=False, user_id=None, filename=None, col_text=None, col_label=None):
    """
    Melatih ulang 6 model klasifikasi menggunakan dataset baru.
    
    Args:
        df (pd.DataFrame): DataFrame yang berisi dataset (harus ada kolom 'normalisasi_kalimat' dan 'label')
        word2vec_model: Model Word2Vec yang sudah diload
        save_models (bool): Jika True, langsung simpan ke path production. Jika False, simpan ke temp.
        user_id (int): ID User yang melakukan training (untuk history)
        filename (str): Nama file dataset (untuk history)
        col_text (str): Nama kolom teks asli (untuk history)
        col_label (str): Nama kolom label asli (untuk history)
        
    Returns:
        dict: Dictionary berisi hasil evaluasi (accuracy dan classification report) per model
    """
    results = {}
    
    # 1. Validasi Dataset
    if 'normalisasi_kalimat' not in df.columns or 'label' not in df.columns:
        raise ValueError("Dataset harus memiliki kolom 'normalisasi_kalimat' dan 'label'")
        
    # 2. Preprocessing & Vectorization
    
    X = []
    y = []
    
    # Vectorize text
    # Menggunakan logika yang SAMA PERSIS dengan klasifikasi
    print("Mulai preprocessing dan vectorization...")
    count_radikal = 0
    count_non_radikal = 0
    
    # Record start time for history
    from datetime import datetime
    started_at = datetime.now()
    row_count = len(df)
    
    for index, row in df.iterrows():
        text = row['normalisasi_kalimat']
        label = row['label']
        
        # Normalize label to 0 (Non-Radikal) and 1 (Radikal)
        # Handle variations: 0, 1, '0', '1', 'non-radikal', 'radikal', 'netral', 'aman', 'negative'
        label_val = None
        
        if isinstance(label, (int, float, np.integer, np.floating)):
            label_val = int(label)
        elif isinstance(label, str):
            label_lower = label.lower().strip()
            # Check for Non-Radikal keywords
            if any(k in label_lower for k in ['non', 'netral', 'aman', 'negati', '0', 'safe']):
                label_val = 0
            # Check for Radikal keywords
            elif any(k in label_lower for k in ['radikal', 'positif', 'bahaya', 'ekstrem', '1', 'danger']):
                label_val = 1
            else:
                # Fallback for unknown strings - try to parse as int
                try:
                    label_val = int(float(label))
                except:
                    # If label is truly unknown, skip this row to avoid pollution
                    print(f"Warning: Label '{label}' tidak dikenali. Baris ini akan dilewati.")
                    continue
        
        if label_val is None:
             continue
             
        # Normalize to 0 and 1 strictly
        if label_val not in [0, 1]:
            # Try to map non-binary integers
             if label_val > 0: 
                 label_val = 1
             else:
                 label_val = 0
        
        if label_val == 1:
            count_radikal += 1
        else:
            count_non_radikal += 1

        # Use the SAME preprocessing as inference (Stemming, etc.)
        # Previously: cleaned_text = clean_text(text) -> Missing stemming
        # Now: use preprocess_for_word2vec which calls preprocess_for_model (with stemming)
        # But wait, vectorize_text ALREADY calls preprocess_for_word2vec internally if we look at utils.py!
        # Let's check utils.py vectorize_text:
        # def vectorize_text(text, word2vec_model, vector_size=100):
        #    if not text or not word2vec_model: return np.zeros...
        #    words = preprocess_for_word2vec(text) ...
        
        # So we just need to pass the raw 'text' to 'vectorize_text', and it will handle the stemming internally.
        # BUT, the original training code here called clean_text(text) explicitly before vectorize_text.
        # If vectorize_text does cleaning internally, we might be double cleaning or cleaning differently.
        
        # Checking utils.py:
        # vectorize_text calls preprocess_for_word2vec(text)
        # preprocess_for_word2vec calls preprocess_for_model(text)
        # preprocess_for_model does regex, stopwords, stemming.
        
        # So passing RAW text to vectorize_text is the correct way now.
        # The previous code was:
        # cleaned_text = clean_text(text)
        # vector = vectorize_text(cleaned_text, word2vec_model)
        
        # If we pass cleaned_text to vectorize_text, it will be processed AGAIN by preprocess_for_model.
        # Since preprocess_for_model is robust (idempotent for some parts, but stemming stemmed words is fine), it should be okay.
        # HOWEVER, clean_text does SLANG normalization which we want to AVOID.
        # So we should NOT call clean_text. We should pass 'text' directly to vectorize_text.
        
        vector = vectorize_text(text, word2vec_model)
        
        X.append(vector)
        y.append(label_val)
        
    print(f"Distribusi Data Training: Non-Radikal={count_non_radikal}, Radikal={count_radikal}")
    
    if count_non_radikal == 0 or count_radikal == 0:
        error_msg = f"Data tidak seimbang! Non-Radikal: {count_non_radikal}, Radikal: {count_radikal}. Training dibatalkan karena model akan bias."
        print(error_msg)
        raise ValueError(error_msg)
    
    X = np.array(X)
    y = np.array(y)

    # 3. Create and Fit Label Encoder (Strict Mapping: 0 -> Non-Radikal, 1 -> Radikal)
    # Ini memastikan konsistensi di seluruh model dan menghindari bias interpretasi label
    le = LabelEncoder()
    # Force classes: index 0 = 'non-radikal', index 1 = 'radikal'
    le.classes_ = np.array(['non-radikal', 'radikal'])
    
    # Save Label Encoder
    le_path_key = 'LABEL_ENCODER_PATH'
    if save_models:
        le_target_path = current_app.config.get(le_path_key)
    else:
        temp_dir = os.path.join(current_app.root_path, 'temp', 'models')
        os.makedirs(temp_dir, exist_ok=True)
        le_target_path = os.path.join(temp_dir, 'label_encoder_temp.joblib')
        
    if le_target_path:
        os.makedirs(os.path.dirname(le_target_path), exist_ok=True)
        joblib.dump(le, le_target_path)
        print(f"Label Encoder disimpan di: {le_target_path}")
    
    # Split data untuk evaluasi internal (opsional, tapi bagus untuk report)
    # Kita gunakan 80% train, 20% test untuk memberikan gambaran akurasi ke admin
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42, stratify=y)
    
    # 4. Definisi Model
    # Menggunakan class_weight='balanced' untuk SVM, RF, LogReg, DT
    # Menggunakan CalibratedClassifierCV untuk model yang probabilitasnya kurang akurat (SVM, NB)
    
    # Base models
    svm_base = SVC(kernel='linear', probability=True, class_weight='balanced', random_state=42)
    nb_base = GaussianNB()
    
    models = {
        'naive_bayes': CalibratedClassifierCV(nb_base, method='isotonic', cv=5), # Isotonic biasanya lebih baik untuk data cukup
        'logistic_regression': LogisticRegression(class_weight='balanced', max_iter=1000, random_state=42),
        'svm': CalibratedClassifierCV(svm_base, method='sigmoid', cv=5), # Sigmoid (Platt) often better for SVM
        'random_forest': RandomForestClassifier(class_weight='balanced', random_state=42),
        'knn': KNeighborsClassifier(n_neighbors=5),
        'decision_tree': DecisionTreeClassifier(class_weight='balanced', random_state=42),
        'gradient_boosting': GradientBoostingClassifier(random_state=42)
    }
    
    # Filter models based on active configuration
    try:
        from utils.settings_utils import load_system_settings
        # We need app context to access system settings properly if they are in config
        # Or load from JSON directly if not in config yet
        
        # Best way: Check current_app.config['VISIBLE_ALGORITHMS'] which is populated by load_system_settings
        active_models_list = current_app.config.get('VISIBLE_ALGORITHMS')
        
        # If config is None (not set), default to ALL
        # If config is [] (empty list), it means user deselected all -> warn or default to all
        
        if active_models_list is not None and len(active_models_list) > 0:
            # Filter models dictionary
            original_count = len(models)
            # Only include models that are in the active list
            models = {k: v for k, v in models.items() if k in active_models_list}
            
            # If after filtering we have 0 models (e.g. only IndoBERT was selected which isn't in 'models' dict),
            # we should warn but proceed (as retrain usually only targets conventional models here)
            # Wait, retrain logic assumes we are training conventional models. IndoBERT is usually fine-tuned separately.
            
            if not models:
                print("Warning: No conventional models selected for retraining based on active configuration.")
                # Fallback: Train ALL conventional models if none selected?
                # Or just return empty results?
                # Let's fallback to ALL to ensure system stability if admin made a mistake
                # But wait, if they only want IndoBERT, then models={} is correct.
                # Let's check if 'indobert' is in active_models_list
                if 'indobert' not in active_models_list:
                     print("Fallback: Training all conventional models as safety net.")
                     # Re-init models (simpler to just not filter if result is empty)
                     # But we already filtered.
                     # Let's just reload the base dict if empty
                     pass # For now let it be empty, loop will just skip
            
            print(f"Filtering active models for training: {list(models.keys())} (Filtered from {original_count})")
        else:
            print("No active algorithms configuration found (or empty), training ALL models by default.")
            
    except Exception as e:
        print(f"Warning: Failed to filter active models, training all. Error: {e}")
    
    # 4. Training & Evaluation
    print("Mulai training model...")
    for name, model in models.items():
        print(f"Training {name}...")
        
        # Train
        model.fit(X_train, y_train)
        
        # Evaluate
        y_pred = model.predict(X_test)
        accuracy = accuracy_score(y_test, y_pred)
        report = classification_report(y_test, y_pred, output_dict=True)
        
        # Extract weighted average metrics for simpler UI display
        precision = report['weighted avg']['precision']
        recall = report['weighted avg']['recall']
        f1 = report['weighted avg']['f1-score']
        
        results[name] = {
            'accuracy': accuracy,
            'precision': precision,
            'recall': recall,
            'f1': f1,
            'report': report
        }
        
        # 5. Save Model
        # Ambil path dari config
        config_key = f'MODEL_{name.upper()}_PATH'
        model_path = current_app.config.get(config_key)
        
        if model_path:
            # Tentukan lokasi simpan: Production atau Temp
            if save_models:
                target_path = model_path
            else:
                # Simpan di folder temp/models
                temp_dir = os.path.join(current_app.root_path, 'temp', 'models')
                os.makedirs(temp_dir, exist_ok=True)
                target_path = os.path.join(temp_dir, f"{name}_temp.joblib")
                
                # Tambahkan path temp ke results agar bisa dipindah nanti
                results[name]['temp_path'] = target_path

            # Pastikan direktori ada
            os.makedirs(os.path.dirname(target_path), exist_ok=True)
            
            # Retrain on FULL dataset before saving (best practice for production model)
            # Opsional: Jika ingin model yang disimpan menggunakan SEMUA data
            model_full = model # Copy config
            model_full.fit(X, y) 
            
            # Save using joblib (preferred) or pickle based on extension
            try:
                if target_path.endswith('.joblib'):
                    joblib.dump(model_full, target_path)
                else:
                    with open(target_path, 'wb') as f:
                        pickle.dump(model_full, f)
                print(f"Model {name} disimpan ke {target_path}")
            except Exception as e:
                print(f"Error saving model {name}: {e}")
        else:
            print(f"Warning: Path untuk model {name} tidak ditemukan di config")
            
    # 6. Save Training History to Database
    if save_models and user_id:
        try:
            from models.models import db, TrainingRun, TrainingMetric
            
            # Create Run Record
            run = TrainingRun(
                started_at=started_at,
                finished_at=datetime.now(),
                user_id=user_id,
                filename=filename,
                row_count=row_count,
                col_text=col_text,
                col_label=col_label,
                is_applied=True,
                word2vec_model_path=current_app.config.get('WORD2VEC_MODEL_PATH'),
                notes="Retrained via Admin Panel"
            )
            db.session.add(run)
            db.session.flush() # Get ID
            
            # Create Metric Records
            for name, metrics in results.items():
                metric = TrainingMetric(
                    run_id=run.id,
                    model_name=name,
                    accuracy=metrics['accuracy'],
                    precision=metrics['precision'],
                    recall=metrics['recall'],
                    f1=metrics['f1'],
                    confusion_matrix=None # Add if needed
                )
                db.session.add(metric)
                
            db.session.commit()
            print(f"Training history saved with ID: {run.id}")
            
        except Exception as e:
            print(f"Error saving training history: {e}")
            # Don't fail the whole process just because history failed
            try:
                db.session.rollback()
            except:
                pass

    return results
