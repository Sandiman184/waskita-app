# 🧠 Waskita ML Models

Direktori ini menyimpan model-model Machine Learning yang digunakan oleh aplikasi Waskita untuk klasifikasi konten radikal.

## 📂 Struktur Folder

*   **`classifiers/`**: Menyimpan model klasifikasi konvensional (scikit-learn).
    *   `Naive Bayes_classifier_model.joblib`: Model utama (MultinomialNB).
    *   `SVM_classifier_model.joblib`: Model pendukung (Support Vector Machine).
    *   `Random Forest_classifier_model.joblib`
    *   `Logistic Regression_classifier_model.joblib`
    *   `Decision Tree_classifier_model.joblib`
    *   `KNN_classifier_model.joblib`

*   **`embeddings/`**: Menyimpan model representasi kata.
    *   `word2vec_model.joblib`: Model Word2Vec (Gensim) yang dilatih pada korpus Bahasa Indonesia (Wiki + Social Media).

*   **`indobert/`**: Menyimpan model Transformer fine-tuned.
    *   `config.json`, `pytorch_model.bin`, `tokenizer.json`, dll.
    *   Model ini berbasis `indobenchmark/indobert-base-p1` yang telah dilatih ulang dengan dataset radikalisme.

*   **`label_encoder/`**:
    *   `label_encoder.joblib`: Encoder untuk mengubah label teks ("Radikal", "Non-Radikal") menjadi numerik.

## ⚠️ Catatan Penting

1.  **File Besar (LFS):** Beberapa model (terutama IndoBERT dan Word2Vec) memiliki ukuran file yang besar (>100MB). Pastikan Anda menggunakan **Git LFS** jika ingin mengelola versi model ini di repository.
    ```bash
    git lfs install
    git lfs track "*.bin"
    git lfs track "*.joblib"
    ```

2.  **Missing Models:** Jika folder ini kosong setelah cloning, berarti model belum dilatih atau tidak disertakan dalam repo. Anda perlu:
    *   Menjalankan script training ulang (via Admin Dashboard).
    *   Atau mendownload pre-trained models dari penyimpanan eksternal (Google Drive/S3) jika tersedia.

3.  **Disable Model Loading:** Untuk development ringan tanpa memuat model berat, set environment variable:
    ```ini
    DISABLE_MODEL_LOADING=True
    ```

## 🔄 Cara Melatih Ulang (Retraining)

1.  Upload dataset baru via dashboard aplikasi.
2.  Masuk ke menu **Admin Panel > Retrain Model**.
3.  Pilih algoritma yang ingin dilatih ulang.
4.  Tunggu proses selesai (background job via Celery/Thread).
