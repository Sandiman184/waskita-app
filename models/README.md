# Machine Learning Models Configuration

This directory contains the machine learning models required for the Waskita application.
Due to their large size, some model files are not included in the repository and must be downloaded or trained manually.

## Directory Structure

Ensure the following directory structure and files exist:

```
models/
├── embeddings/
│   └── word2vec_model.joblib             # Word2Vec Model (Required)
├── classifiers/
│   ├── Naive Bayes_classifier_model.joblib
│   ├── SVM_classifier_model.joblib
│   ├── Random Forest_classifier_model.joblib
│   ├── Logistic Regression_classifier_model.joblib
│   ├── Decision Tree_classifier_model.joblib
│   └── KNN_classifier_model.joblib
├── label_encoder/
│   └── label_encoder.joblib
└── indobert/
    ├── config.json
    ├── model.safetensors
    ├── tokenizer.json
    └── ... (HuggingFace model files)
```

## Troubleshooting Missing Models

If you see errors like `File Word2Vec model tidak ditemukan` in the logs:

1.  **Check File Existence**: Verify that `models/embeddings/wiki_word2vec_csv_updated.model` exists.
2.  **Training**: If the files are missing, you may need to run the training pipeline to generate them.
    *   Run the training script: `python src/backend/train_models.py` (if available) or check the documentation for model download links.
3.  **Environment Variables**: The model paths can be overridden in `.env` or `docker-compose.yml`.
    *   Default Word2Vec path: `/app/models/embeddings/wiki_word2vec_csv_updated.model` (in Docker).

## Docker Setup

When running with Docker, this `models/` directory is mounted to `/app/models` inside the container.
Any changes you make here (adding/removing models) will be reflected in the container after a restart.
