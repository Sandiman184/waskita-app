import os
import pandas as pd
import numpy as np
import joblib
import pickle
from datetime import datetime
from flask import current_app
from sklearn.model_selection import train_test_split
from sklearn.metrics import classification_report, accuracy_score, confusion_matrix
from sklearn.naive_bayes import GaussianNB
from sklearn.svm import SVC
from sklearn.neighbors import KNeighborsClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.tree import DecisionTreeClassifier
from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier
from sklearn.calibration import CalibratedClassifierCV
from sklearn.preprocessing import LabelEncoder

from utils.utils import vectorize_text, preprocess_for_model
from models.models import db, TrainingRun, TrainingMetric

class ActiveLearningManager:
    """
    Manages active learning processes including sample selection and incremental updates.
    """
    def __init__(self, models_dict=None):
        self.models = models_dict if models_dict else {}

    def select_uncertain_samples(self, unlabeled_df, text_col, word2vec_model, n_samples=10):
        """
        Selects the most uncertain samples from unlabeled data using entropy or margin.
        Returns a DataFrame with the selected samples.
        """
        if not self.models:
            return pd.DataFrame()

        uncertainty_scores = []
        
        for idx, row in unlabeled_df.iterrows():
            text = row[text_col]
            if pd.isna(text):
                continue
                
            # Vectorize
            vector = vectorize_text(str(text), word2vec_model).reshape(1, -1)
            
            # Calculate average entropy across all models that support probability
            avg_entropy = 0
            count = 0
            
            for name, model in self.models.items():
                if hasattr(model, "predict_proba"):
                    try:
                        probs = model.predict_proba(vector)[0]
                        # Entropy = -sum(p * log(p))
                        entropy = -np.sum(probs * np.log(probs + 1e-10))
                        avg_entropy += entropy
                        count += 1
                    except:
                        pass
            
            if count > 0:
                avg_entropy /= count
                uncertainty_scores.append((idx, avg_entropy))
        
        # Sort by entropy descending (higher entropy = more uncertain)
        uncertainty_scores.sort(key=lambda x: x[1], reverse=True)
        
        selected_indices = [x[0] for x in uncertainty_scores[:n_samples]]
        return unlabeled_df.loc[selected_indices]

class TrainingPipeline:
    def __init__(self, df, word2vec_model, user_id=None, filename=None, col_text='normalisasi_kalimat', col_label='label', progress_callback=None):
        self.df = df
        self.word2vec_model = word2vec_model
        self.user_id = user_id
        self.filename = filename
        self.col_text = col_text
        self.col_label = col_label
        self.models = {}
        self.results = {}
        self.logger = current_app.logger
        self.progress_callback = progress_callback

    def _update_progress(self, message, percent):
        if self.progress_callback:
            try:
                self.progress_callback(message, percent)
            except Exception as e:
                self.logger.warning(f"Progress callback failed: {e}")

    def validate_and_clean_dataset(self):
        """
        Validates input dataframe and cleans it.
        Handles duplicate columns and ambiguous truth values.
        """
        self._update_progress("Validating dataset...", 10)
        self.logger.info("Starting dataset validation...")
        
        # 1. Handle Duplicate Columns
        if len(self.df.columns) != len(set(self.df.columns)):
            self.logger.warning("Duplicate columns detected. Deduping...")
            self.df = self.df.loc[:, ~self.df.columns.duplicated()]

        # 2. Check required columns (Strict Check)
        missing_cols = []
        if self.col_text not in self.df.columns:
            missing_cols.append(self.col_text)
        if self.col_label not in self.df.columns:
            missing_cols.append(self.col_label)
            
        if missing_cols:
            error_msg = f"Dataset structure invalid. Missing required columns: {', '.join(missing_cols)}. Found: {', '.join(self.df.columns)}"
            self.logger.error(error_msg)
            raise ValueError(error_msg)

        # 3. Drop rows with missing values in critical columns
        initial_len = len(self.df)
        self.df = self.df.dropna(subset=[self.col_text, self.col_label])
        if len(self.df) < initial_len:
            self.logger.info(f"Dropped {initial_len - len(self.df)} rows with missing values.")

        # 4. Normalize Labels
        # Explicitly handle Series ambiguity by using apply
        def normalize_label(val):
            # If val is a Series (shouldn't happen after dedupe but safety first)
            if isinstance(val, pd.Series):
                val = val.iloc[0]

            if pd.isna(val):
                return None

            val_str = str(val).lower().strip()
            
            if any(k == val_str for k in ['non', 'netral', 'aman', 'negati', '0', 'safe', 'non-radikal']):
                return 0
            if any(k == val_str for k in ['radikal', 'positif', 'bahaya', 'ekstrem', '1', 'danger']):
                return 1
            
            try:
                # Try converting to float then int
                num = float(val)
                return 1 if num > 0.5 else 0
            except:
                return None

        self.df['label_normalized'] = self.df[self.col_label].apply(normalize_label)
        
        # Drop rows where label could not be normalized
        self.df = self.df.dropna(subset=['label_normalized'])
        self.df['label_normalized'] = self.df['label_normalized'].astype(int)

        count_radikal = (self.df['label_normalized'] == 1).sum()
        count_non_radikal = (self.df['label_normalized'] == 0).sum()
        
        self.logger.info(f"Data Distribution: Non-Radikal={count_non_radikal}, Radikal={count_radikal}")
        
        if count_non_radikal == 0 or count_radikal == 0:
            raise ValueError(f"Data imbalance detected! Non-Radikal: {count_non_radikal}, Radikal: {count_radikal}")

    def prepare_data(self):
        """
        Vectorizes text and prepares X, y.
        """
        self._update_progress("Vectorizing text data (this may take a moment)...", 20)
        self.logger.info("Vectorizing text data...")
        X = []
        y = self.df['label_normalized'].values
        
        total_rows = len(self.df)
        update_interval = max(1, total_rows // 20) # Update every 5%
        
        for i, text in enumerate(self.df[self.col_text]):
            # Ensure text is string
            if pd.isna(text):
                text = ""
            else:
                text = str(text)
                
            # Note: vectorize_text handles preprocessing internally
            vector = vectorize_text(text, self.word2vec_model)
            X.append(vector)
            
            # Detailed progress update for vectorization
            if i % update_interval == 0:
                percent = 20 + int((i / total_rows) * 30) # 20% to 50%
                self._update_progress(f"Vectorizing row {i+1}/{total_rows}...", percent)
            
        return np.array(X), y

    def train(self, save_models=False):
        """
        Main training loop.
        """
        self.validate_and_clean_dataset()
        X, y = self.prepare_data()
        
        self._update_progress("Preparing training data...", 50)
        
        # Label Encoder (Strict)
        le = LabelEncoder()
        le.classes_ = np.array(['non-radikal', 'radikal']) # 0=non-radikal, 1=radikal
        
        if save_models:
             le_path = current_app.config.get('LABEL_ENCODER_PATH')
             if le_path:
                 os.makedirs(os.path.dirname(le_path), exist_ok=True)
                 joblib.dump(le, le_path)
        else:
             # Even if temp, save LE for temp usage
             temp_dir = os.path.join(current_app.root_path, 'temp', 'models')
             os.makedirs(temp_dir, exist_ok=True)
             le_path = os.path.join(temp_dir, 'label_encoder_temp.joblib')
             joblib.dump(le, le_path)

        # Split Data
        X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42, stratify=y)
        
        # Define Models
        svm_base = SVC(kernel='linear', probability=True, class_weight='balanced', random_state=42)
        nb_base = GaussianNB()
        
        all_models = {
            'naive_bayes': CalibratedClassifierCV(nb_base, method='isotonic', cv=5),
            'logistic_regression': LogisticRegression(class_weight='balanced', max_iter=1000, random_state=42),
            'svm': CalibratedClassifierCV(svm_base, method='sigmoid', cv=5),
            'random_forest': RandomForestClassifier(class_weight='balanced', random_state=42),
            'knn': KNeighborsClassifier(n_neighbors=5),
            'decision_tree': DecisionTreeClassifier(class_weight='balanced', random_state=42),
            'gradient_boosting': GradientBoostingClassifier(random_state=42)
        }
        
        # Filter Active Models
        active_models_list = current_app.config.get('VISIBLE_ALGORITHMS')
        if active_models_list:
            self.models = {k: v for k, v in all_models.items() if k in active_models_list}
            if not self.models and 'indobert' not in active_models_list:
                 self.logger.warning("No models selected, falling back to all conventional models.")
                 self.models = all_models
        else:
            self.models = all_models

        # Train and Evaluate
        self.logger.info(f"Training models: {list(self.models.keys())}")
        
        total_models = len(self.models)
        
        for idx, (name, model) in enumerate(self.models.items()):
            try:
                # 50% to 90%
                percent = 50 + int((idx / total_models) * 40)
                self._update_progress(f"Training model {name} ({idx+1}/{total_models})...", percent)
                
                self.logger.info(f"Training {name}...")
                model.fit(X_train, y_train)
                
                y_pred = model.predict(X_test)
                accuracy = accuracy_score(y_test, y_pred)
                report = classification_report(y_test, y_pred, output_dict=True)
                cm = confusion_matrix(y_test, y_pred).tolist()
                
                # Fix for classification report keys (0/1 to non-radikal/radikal)
                # Ensure keys match what frontend expects
                mapped_report = {}
                for key, value in report.items():
                    if key == '0':
                        mapped_report['non-radikal'] = value
                    elif key == '1':
                        mapped_report['radikal'] = value
                    else:
                        mapped_report[key] = value
                
                self.results[name] = {
                    'accuracy': accuracy,
                    'precision': report['weighted avg']['precision'],
                    'recall': report['weighted avg']['recall'],
                    'f1': report['weighted avg']['f1-score'],
                    'report': mapped_report,
                    'confusion_matrix': cm
                }
                
                if save_models:
                    self._update_progress(f"Saving model {name}...", percent + 2)
                    self._save_model(name, model, X, y)
                    
            except Exception as e:
                self.logger.error(f"Error training {name}: {e}")
                self.results[name] = {'error': str(e)}

        if save_models and self.user_id:
            self._update_progress("Saving training history...", 95)
            self._save_history()
            
        self._update_progress("Training completed!", 100)
        return self.results

    def _save_model(self, name, model, X_full, y_full):
        """
        Retrains on full dataset and saves the model.
        """
        try:
            # Retrain on full data
            model.fit(X_full, y_full)
            
            config_key = f'MODEL_{name.upper()}_PATH'
            model_path = current_app.config.get(config_key)
            
            if model_path:
                os.makedirs(os.path.dirname(model_path), exist_ok=True)
                if model_path.endswith('.joblib'):
                    joblib.dump(model, model_path)
                else:
                    with open(model_path, 'wb') as f:
                        pickle.dump(model, f)
                self.logger.info(f"Saved {name} to {model_path}")
            else:
                # Save to temp
                temp_dir = os.path.join(current_app.root_path, 'temp', 'models')
                os.makedirs(temp_dir, exist_ok=True)
                target_path = os.path.join(temp_dir, f"{name}_temp.joblib")
                joblib.dump(model, target_path)
                self.results[name]['temp_path'] = target_path
                
        except Exception as e:
            self.logger.error(f"Failed to save model {name}: {e}")

    def _save_history(self):
        """
        Saves training history to database.
        """
        try:
            # Check if this is a temp run (filename exists but not saved to prod)
            # Actually, training history should be saved for successful runs regardless of 'save_models' flag
            # But the requirement implies permanent storage only when 'save_models' is True (production deployment)
            # However, user wants to see history of temp runs too? 
            # The current logic only calls _save_history if save_models=True (see end of train method).
            
            run = TrainingRun(
                started_at=datetime.utcnow(), # Use UTC as in models
                finished_at=datetime.utcnow(),
                user_id=self.user_id,
                filename=self.filename,
                row_count=len(self.df),
                col_text=self.col_text,
                col_label=self.col_label,
                is_applied=True, # Since this is called only when save_models=True
                word2vec_model_path=current_app.config.get('WORD2VEC_MODEL_PATH'),
                notes="Retrained via Admin Panel (Robust Pipeline)"
            )
            db.session.add(run)
            db.session.flush()
            
            for name, metrics in self.results.items():
                if 'error' in metrics:
                    continue
                    
                metric = TrainingMetric(
                    run_id=run.id,
                    model_name=name,
                    accuracy=metrics.get('accuracy'),
                    precision=metrics.get('precision'),
                    recall=metrics.get('recall'),
                    f1=metrics.get('f1'),
                    confusion_matrix=metrics.get('confusion_matrix'),
                    detail_metrics=metrics.get('report')
                )
                db.session.add(metric)
                
            db.session.commit()
            self.logger.info(f"Training history saved (Run ID: {run.id})")
        except Exception as e:
            self.logger.error(f"Failed to save training history: {e}")
            db.session.rollback()
