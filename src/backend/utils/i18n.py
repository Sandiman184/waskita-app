from flask import current_app
from flask_login import current_user

# Dictionary TRANSLATIONS removed as it is no longer used.
# The t() function is deprecated and now acts as a pass-through.

def t(text):
    """
    Deprecated: Translate text based on current user's language preference.
    Now just returns the text as-is to enforce standard language (English).
    """
    return text
