import json
import os
from flask import current_app

SETTINGS_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'config', 'system_settings.json')

def load_system_settings(app):
    """Load system settings from JSON file into app.config"""
    try:
        if os.path.exists(SETTINGS_FILE):
            with open(SETTINGS_FILE, 'r') as f:
                settings = json.load(f)
                
            # Update app config
            if 'CLASSIFICATION_THRESHOLD' in settings:
                app.config['CLASSIFICATION_THRESHOLD'] = settings['CLASSIFICATION_THRESHOLD']
            
            if 'VISIBLE_ALGORITHMS' in settings:
                app.config['VISIBLE_ALGORITHMS'] = settings['VISIBLE_ALGORITHMS']
                
            app.logger.info(f"Loaded system settings from {SETTINGS_FILE}")
            return True
    except Exception as e:
        app.logger.error(f"Error loading system settings: {e}")
        return False
    return False

def save_system_settings(settings):
    """Save system settings to JSON file and update current_app.config"""
    try:
        # Update current_app config first
        for key, value in settings.items():
            current_app.config[key] = value
            
        # Ensure config directory exists
        os.makedirs(os.path.dirname(SETTINGS_FILE), exist_ok=True)
        
        # Save to file
        with open(SETTINGS_FILE, 'w') as f:
            json.dump(settings, f, indent=4)
            
        current_app.logger.info(f"Saved system settings to {SETTINGS_FILE}")
        return True
    except Exception as e:
        current_app.logger.error(f"Error saving system settings: {e}")
        return False
