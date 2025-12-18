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

from utils.training_pipeline import TrainingPipeline

def train_models(df, word2vec_model, save_models=False, user_id=None, filename=None, col_text=None, col_label=None, progress_callback=None):
    """
    Melatih ulang model klasifikasi menggunakan TrainingPipeline yang lebih robust.
    """
    pipeline = TrainingPipeline(
        df=df,
        word2vec_model=word2vec_model,
        user_id=user_id,
        filename=filename,
        col_text=col_text if col_text else 'normalisasi_kalimat',
        col_label=col_label if col_label else 'label',
        progress_callback=progress_callback
    )
    
    return pipeline.train(save_models=save_models)
