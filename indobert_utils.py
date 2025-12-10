import torch
from transformers import AutoTokenizer, AutoModelForSequenceClassification
import os
import numpy as np

class IndoBERTClassifier:
    def __init__(self, model_path):
        self.model_path = model_path
        self.tokenizer = None
        self.model = None
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self.load_model()

    def load_model(self):
        try:
            if os.path.exists(self.model_path):
                self.tokenizer = AutoTokenizer.from_pretrained(self.model_path)
                self.model = AutoModelForSequenceClassification.from_pretrained(self.model_path)
                self.model.to(self.device)
                self.model.eval()
                print(f"IndoBERT model loaded successfully from {self.model_path}")
            else:
                print(f"IndoBERT model path not found: {self.model_path}")
        except Exception as e:
            print(f"Error loading IndoBERT model: {e}")

    def predict(self, text):
        if not self.model or not self.tokenizer:
            return None, None

        try:
            inputs = self.tokenizer(text, return_tensors="pt", truncation=True, padding=True, max_length=512)
            inputs = {k: v.to(self.device) for k, v in inputs.items()}

            with torch.no_grad():
                outputs = self.model(**inputs)
                logits = outputs.logits
                probabilities = torch.softmax(logits, dim=1).cpu().numpy()[0]
                prediction_idx = torch.argmax(logits, dim=1).cpu().item()

            # Assuming the model is binary classification: 0 -> Non-Radikal, 1 -> Radikal
            # Adjust based on actual model training. Usually 0 is negative (Non-Radikal), 1 is positive (Radikal).
            # But I should verify the label mapping if possible.
            # For now assuming standard: 0=Non-Radikal, 1=Radikal
            
            prediction_label = 'radikal' if prediction_idx == 1 else 'non-radikal'
            
            return prediction_label, probabilities

        except Exception as e:
            print(f"Error during IndoBERT prediction: {e}")
            return None, None

    def vectorize(self, text):
        """
        Get the embeddings for the text.
        """
        if not self.model or not self.tokenizer:
            return None

        try:
            inputs = self.tokenizer(text, return_tensors="pt", truncation=True, padding=True, max_length=512)
            inputs = {k: v.to(self.device) for k, v in inputs.items()}
            
            # Use the base model to get hidden states if possible, or just use the last hidden state of the classifier
            # Here we might want the output of the transformer encoder
            with torch.no_grad():
                # We need to access the base bert model. 
                # Usually AutoModelForSequenceClassification has a 'bert' or 'roberta' attribute or similar.
                # Let's try to output hidden states.
                outputs = self.model(**inputs, output_hidden_states=True)
                # Last hidden state
                last_hidden_state = outputs.hidden_states[-1]
                # Pool the embeddings (e.g., CLS token)
                cls_embedding = last_hidden_state[:, 0, :].cpu().numpy()[0]
                
            return cls_embedding
        except Exception as e:
            print(f"Error during IndoBERT vectorization: {e}")
            return None
