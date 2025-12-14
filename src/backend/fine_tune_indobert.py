import os
import torch
from torch.utils.data import DataLoader, Dataset
from transformers import AutoTokenizer, AutoModelForSequenceClassification, AdamW
from sklearn.model_selection import train_test_split
import pandas as pd
import numpy as np

# Konfigurasi
MODEL_NAME = 'indobenchmark/indobert-base-p1'
MAX_LEN = 128
BATCH_SIZE = 16
EPOCHS = 3
LEARNING_RATE = 2e-5

class SentimentDataset(Dataset):
    def __init__(self, texts, labels, tokenizer, max_len):
        self.texts = texts
        self.labels = labels
        self.tokenizer = tokenizer
        self.max_len = max_len

    def __len__(self):
        return len(self.texts)

    def __getitem__(self, item):
        text = str(self.texts[item])
        label = self.labels[item]

        encoding = self.tokenizer.encode_plus(
            text,
            add_special_tokens=True,
            max_length=self.max_len,
            return_token_type_ids=False,
            pad_to_max_length=True,
            return_attention_mask=True,
            return_tensors='pt',
        )

        return {
            'text': text,
            'input_ids': encoding['input_ids'].flatten(),
            'attention_mask': encoding['attention_mask'].flatten(),
            'targets': torch.tensor(label, dtype=torch.long)
        }

def fine_tune_indobert(data_path, output_dir):
    """
    Fine-tune IndoBERT model
    :param data_path: Path ke file CSV dataset (kolom: text, label)
    :param output_dir: Directory untuk menyimpan model fine-tuned
    """
    # Load dataset
    print(f"Loading dataset from {data_path}...")
    try:
        df = pd.read_csv(data_path)
    except Exception as e:
        print(f"Error reading CSV: {e}")
        return
    
    # Normalisasi nama kolom
    if 'text' not in df.columns and 'content' in df.columns:
        df['text'] = df['content']
    
    if 'text' not in df.columns or 'label' not in df.columns:
        print("Dataset must have 'text' (or 'content') and 'label' columns")
        print(f"Available columns: {df.columns}")
        return
    
    # Encode labels jika string
    if df['label'].dtype == 'object':
        from sklearn.preprocessing import LabelEncoder
        le = LabelEncoder()
        df['label'] = le.fit_transform(df['label'])
        print("Labels encoded:", dict(zip(le.classes_, le.transform(le.classes_))))

    # Split dataset
    df_train, df_val = train_test_split(df, test_size=0.1, random_state=42)
    
    print("Loading tokenizer and model...")
    tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)
    model = AutoModelForSequenceClassification.from_pretrained(MODEL_NAME, num_labels=len(df['label'].unique()))
    
    train_dataset = SentimentDataset(
        texts=df_train.text.to_numpy(),
        labels=df_train.label.to_numpy(),
        tokenizer=tokenizer,
        max_len=MAX_LEN
    )
    
    val_dataset = SentimentDataset(
        texts=df_val.text.to_numpy(),
        labels=df_val.label.to_numpy(),
        tokenizer=tokenizer,
        max_len=MAX_LEN
    )
    
    train_data_loader = DataLoader(
        train_dataset,
        batch_size=BATCH_SIZE,
        shuffle=True
    )
    
    val_data_loader = DataLoader(
        val_dataset,
        batch_size=BATCH_SIZE
    )
    
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model = model.to(device)
    
    optimizer = AdamW(model.parameters(), lr=LEARNING_RATE, correct_bias=False)
    
    loss_fn = torch.nn.CrossEntropyLoss().to(device)
    
    print(f"Starting training on {device}...")
    
    for epoch in range(EPOCHS):
        print(f"Epoch {epoch + 1}/{EPOCHS}")
        print("-" * 10)
        
        # Training
        model.train()
        losses = []
        correct_predictions = 0
        
        for d in train_data_loader:
            input_ids = d["input_ids"].to(device)
            attention_mask = d["attention_mask"].to(device)
            targets = d["targets"].to(device)
            
            outputs = model(
                input_ids=input_ids,
                attention_mask=attention_mask,
                labels=targets
            )
            
            loss = outputs.loss
            preds = torch.argmax(outputs.logits, dim=1)
            
            correct_predictions += torch.sum(preds == targets)
            losses.append(loss.item())
            
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), max_norm=1.0)
            optimizer.step()
            optimizer.zero_grad()
            
        train_acc = correct_predictions.double() / len(df_train)
        train_loss = np.mean(losses)
        print(f"Train loss {train_loss} accuracy {train_acc}")
        
        # Validation
        model.eval()
        val_losses = []
        val_correct_predictions = 0
        
        with torch.no_grad():
            for d in val_data_loader:
                input_ids = d["input_ids"].to(device)
                attention_mask = d["attention_mask"].to(device)
                targets = d["targets"].to(device)
                
                outputs = model(
                    input_ids=input_ids,
                    attention_mask=attention_mask,
                    labels=targets
                )
                
                loss = outputs.loss
                preds = torch.argmax(outputs.logits, dim=1)
                
                val_correct_predictions += torch.sum(preds == targets)
                val_losses.append(loss.item())
        
        val_acc = val_correct_predictions.double() / len(df_val)
        val_loss = np.mean(val_losses)
        print(f"Val loss {val_loss} accuracy {val_acc}")
        print()
        
    print("Saving model...")
    os.makedirs(output_dir, exist_ok=True)
    model.save_pretrained(output_dir)
    tokenizer.save_pretrained(output_dir)
    print(f"Model saved to {output_dir}")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--data', type=str, required=True, help='Path to CSV dataset')
    parser.add_argument('--output', type=str, default='models/indobert_finetuned', help='Output directory')
    args = parser.parse_args()
    
    fine_tune_indobert(args.data, args.output)
