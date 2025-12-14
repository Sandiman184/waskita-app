import os
import sys
import numpy as np
import pandas as pd
from flask import Flask
from dotenv import load_dotenv

# Load Env
load_dotenv()

# Setup paths
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from flask import Flask
from config.config import config
from utils.utils import (
    load_classification_models, 
    load_word2vec_model, 
    preprocess_for_model, 
    vectorize_text, 
    classify_content,
    load_text_processing_resources
)

def validate_pipeline():
    print("="*80)
    print("VALIDASI PIPELINE KLASIFIKASI WASKITA APP".center(80))
    print("="*80)
    
    # 1. Setup App Context
    app = Flask(__name__)
    app.config.from_object(config['default'])
    
    with app.app_context():
        # Ensure resources loaded
        load_text_processing_resources()
        
        # 2. Load Models
        print("\n[1] Memuat Model...")
        models = load_classification_models()
        word2vec = load_word2vec_model()
        
        if not word2vec:
            print("❌ Word2Vec gagal dimuat!")
            return
            
        print(f"✅ Word2Vec dimuat (Vector Size: {word2vec.vector_size})")
        print(f"✅ Model Klasifikasi: {list(models.keys())}")
        
        # 3. Test Cases
        test_cases = [
            {
                "text": "Khilafah adalah solusi tunggal umat islam, hancurkan sistem demokrasi thogut!",
                "expected": "Radikal",
                "desc": "Konten Radikal (Khilafah & Anti-Demokrasi)"
            },
            {
                "text": "Pemerintah mengajak masyarakat menjaga persatuan dan kesatuan bangsa di tengah perbedaan.",
                "expected": "Non-Radikal",
                "desc": "Konten Non-Radikal (Nasionalisme)"
            },
            {
                "text": "ayo kita bom bunuh diri di tempat ibadah kafir itu jihad",
                "expected": "Radikal",
                "desc": "Konten Radikal (Ajakan Kekerasan/Teror)"
            },
            {
                "text": "Saya suka makan nasi goreng di pinggir jalan bersama teman-teman yg asik.",
                "expected": "Non-Radikal",
                "desc": "Konten Netral (Sehari-hari dengan slang 'yg')"
            }
        ]
        
        print("\n[2] Pengujian Pipeline...")
        
        for i, case in enumerate(test_cases):
            raw_text = case['text']
            print(f"\n🔹 KASUS {i+1}: {case['desc']}")
            print(f"   Input Asli: '{raw_text}'")
            
            # A. Preprocessing Check
            preprocessed = preprocess_for_model(raw_text)
            print(f"   Preprocessing Result: '{preprocessed}'")
            
            # B. Vectorization Check
            vector = vectorize_text(raw_text, word2vec) # Note: vectorize_text handles preprocessing internally now? 
            # Wait, our update to vectorize_text calls preprocess_for_word2vec which calls preprocess_for_model.
            # So we pass raw_text to vectorize_text.
            
            is_zero_vector = not np.any(vector)
            print(f"   Vector Status: {'⚠️ ZERO VECTOR (Semua kata OOV)' if is_zero_vector else '✅ Valid Vector'}")
            
            # C. Classification
            print(f"   {'Model':<20} | {'Prediksi':<12} | {'Probabilitas (Non/Rad)':<20} | {'Status'}")
            print("   " + "-"*65)
            
            for name, model in models.items():
                # Logic per model type
                if name == 'indobert':
                    # IndoBERT uses Raw Text
                    pred, prob = classify_content(None, model, text=raw_text)
                else:
                    # Conventional uses Vector
                    pred, prob = classify_content(vector, model, text=preprocessed)
                
                # Format Probability
                if prob is not None and len(prob) == 2:
                    prob_str = f"{prob[0]:.4f} / {prob[1]:.4f}"
                else:
                    prob_str = "N/A"
                
                # Check expectation
                # Note: This is loose check, prediction might differ from expectation depending on model quality
                status = "✅" if pred.lower() == case['expected'].lower() else "❓"
                
                print(f"   {name:<20} | {pred:<12} | {prob_str:<20} | {status}")

if __name__ == "__main__":
    validate_pipeline()
